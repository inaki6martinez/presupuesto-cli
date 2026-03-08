"""Parser de extractos bancarios de Abanca.

Abanca exporta CSV con separador punto y coma y estas columnas::

  Fecha ctble ; Fecha valor ; Concepto ; Importe ; Moneda ; Saldo ; Moneda ; Concepto ampliado

Características del formato:
- Encoding: UTF-8 (con posibles caracteres corruptos en algunos exports antiguos).
- Separador: punto y coma (;). Sin comillas en los valores.
- Fecha: DD-MM-YYYY.
- Importe: formato europeo con coma decimal, sin separador de miles (ej. '2308,10', '-260,00').
- Columna "Concepto ampliado": más descriptiva que "Concepto" en transferencias.
  Para tarjeta suele estar vacía; para nóminas/transferencias tiene el detalle real.
- Pagos con tarjeta: "Concepto" empieza por el terminal "767003185863 NOMBRE_COMERCIO \CIUDAD\REF".
- Pagos Bizum: "Concepto" tiene "INGRESO BIZUM - descripcion" o "PAGO BIZUM - descripcion".
"""

from __future__ import annotations

import csv
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from presupuesto.parsers.base import MovimientoCrudo, ParserBase

# Prefijo numérico de terminal de tarjeta (12 dígitos)
_RE_PREFIJO_TARJETA = re.compile(r"^\d{12}\s+")
# Sufijo de ubicación en compras con tarjeta: "\CIUDAD\ES..." o "\CIUDAD\" al final
_RE_SUFIJO_UBICACION = re.compile(r"\s*\\[^\\]*\\[^\s]*$")
# Referencia Bizum al final del Concepto ampliado
_RE_REFERENCIA_BIZUM = re.compile(r"\s*#BIZUM_BC2[CE]:\S+$", re.IGNORECASE)

# Cabeceras que identifican el CSV de Abanca (en minúsculas)
_CABECERA_FECHA = "fecha ctble"
_CABECERA_CONCEPTO_AMPLIADO = "concepto ampliado"


def _detectar_encoding(ruta: Path) -> str:
    """Prueba UTF-8-sig, UTF-8 y latin-1 en orden."""
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            ruta.read_text(encoding=enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin-1"


def _parsear_fecha(valor: str) -> date:
    """Convierte 'DD-MM-YYYY' a date."""
    valor = valor.strip()
    try:
        dia, mes, año = valor.split("-")
        return date(int(año), int(mes), int(dia))
    except ValueError as e:
        raise ValueError(f"Fecha de Abanca no reconocida: '{valor}'") from e


def _parsear_importe(valor: str) -> Decimal:
    """Convierte formato europeo con coma decimal a Decimal.

    Abanca no usa punto de miles en este export, pero se elimina por si acaso.
    """
    valor = valor.strip().replace(".", "").replace(",", ".")
    try:
        return Decimal(valor)
    except InvalidOperation as e:
        raise ValueError(f"Importe de Abanca no reconocido: '{valor}'") from e


def _limpiar_concepto_tarjeta(texto: str) -> str:
    """Elimina el prefijo numérico de terminal y el sufijo de ubicación.

    '767003185863 EROSKI BOULEVARD   \\VITORIA\\ES25...' → 'EROSKI BOULEVARD'
    '767003185863 PAYPAL *LEROYMERLIN 917496000 ...'   → 'PAYPAL *LEROYMERLIN'
    """
    texto = _RE_PREFIJO_TARJETA.sub("", texto)
    texto = _RE_SUFIJO_UBICACION.sub("", texto)
    return " ".join(texto.split())


def _construir_concepto(concepto: str, ampliado: str) -> str:
    """Elige el texto más informativo como concepto del movimiento.

    Lógica:
    - Bizum (Concepto contiene "BIZUM"): usar Concepto directamente,
      ya que tiene el contexto "INGRESO/PAGO BIZUM - descripción" que
      es útil para categorizar. El ampliado solo repite la descripción
      con una referencia opaca.
    - Compra con tarjeta (prefijo "767003185863"): limpiar prefijo y
      sufijo de ubicación del Concepto.
    - Resto: si Concepto ampliado tiene contenido real (no vacío tras
      quitar la referencia Bizum), usarlo. Si no, usar Concepto tal cual.
    """
    ampliado = ampliado.strip()
    concepto = concepto.strip()

    # Bizum: mantener el Concepto porque tiene el tipo y la descripción
    if "BIZUM" in concepto.upper():
        return concepto

    # Compra con tarjeta: limpiar
    if _RE_PREFIJO_TARJETA.match(concepto):
        return _limpiar_concepto_tarjeta(concepto)

    # Para transferencias y conceptos manuales: preferir el ampliado si es descriptivo
    ampliado_limpio = _RE_REFERENCIA_BIZUM.sub("", ampliado).strip()
    if ampliado_limpio:
        return ampliado_limpio

    return concepto


class ParserAbanca(ParserBase):
    """Parser para extractos CSV de Abanca."""

    def puede_parsear(self, ruta_archivo: str) -> bool:
        """Detecta si el archivo es un CSV de Abanca comprobando sus cabeceras."""
        ruta = Path(ruta_archivo)
        if ruta.suffix.lower() != ".csv":
            return False
        try:
            enc = _detectar_encoding(ruta)
            primera_linea = ruta.open(encoding=enc, errors="replace").readline()
            partes = [p.strip().lower() for p in primera_linea.split(";")]
            return _CABECERA_FECHA in partes and _CABECERA_CONCEPTO_AMPLIADO in partes
        except Exception:
            return False

    def parsear(self, ruta_archivo: str) -> list[MovimientoCrudo]:
        """Extrae los movimientos del CSV de Abanca."""
        ruta = Path(ruta_archivo)
        enc = _detectar_encoding(ruta)

        movimientos: list[MovimientoCrudo] = []

        with open(ruta, encoding=enc, errors="replace", newline="") as f:
            lector = csv.DictReader(f, delimiter=";")

            # Normalizar nombres de columna a minúsculas
            primera_fila = next(lector, None)
            if primera_fila is None:
                return []

            # Reconstruir mapa de columnas con claves en minúsculas
            mapa = {k.strip().lower(): k for k in primera_fila.keys()}

            col_fecha = mapa.get("fecha ctble")
            col_concepto = mapa.get("concepto")
            col_ampliado = mapa.get("concepto ampliado")
            col_importe = mapa.get("importe")

            if not all([col_fecha, col_concepto, col_importe]):
                raise ValueError(
                    f"El CSV no tiene las columnas esperadas de Abanca. "
                    f"Columnas encontradas: {list(primera_fila.keys())}"
                )

            # Procesar la primera fila (que ya leímos con next()) y el resto
            filas = [primera_fila] + list(lector)
            for fila in filas:
                fecha_str = (fila.get(col_fecha) or "").strip()
                concepto_raw = (fila.get(col_concepto) or "").strip()
                ampliado_raw = (fila.get(col_ampliado) or "").strip() if col_ampliado else ""
                importe_str = (fila.get(col_importe) or "").strip()

                if not fecha_str or not importe_str:
                    continue

                fecha = _parsear_fecha(fecha_str)
                importe = _parsear_importe(importe_str)
                concepto = _construir_concepto(concepto_raw, ampliado_raw)

                concepto_original = f"{fecha_str} | {concepto_raw}"
                if ampliado_raw:
                    concepto_original += f" | {ampliado_raw}"

                movimientos.append(MovimientoCrudo(
                    fecha=fecha,
                    concepto=concepto,
                    importe=importe,
                    concepto_original=concepto_original,
                ))

        return movimientos
