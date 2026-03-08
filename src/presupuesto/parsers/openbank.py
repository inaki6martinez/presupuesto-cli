"""Parser de extractos bancarios de Openbank.

Openbank exporta sus movimientos como un fichero HTML disfrazado de .xls
(extensión .xls, pero contenido XHTML). Sus características:

- Encoding: iso-8859-1 (declarado en el meta charset del propio HTML).
- Una única tabla HTML con cabeceras intercaladas de celdas vacías:
    col 1: Fecha Operación | col 3: Fecha Valor | col 5: Concepto
    col 7: Importe          | col 9: Saldo
- Importes en formato europeo: punto como separador de miles, coma como decimal
  (ej. '2.308,10', '-1.200,00').
- Fechas en formato DD/MM/YYYY.
- Las filas de cabecera y metadatos de la cuenta se ignoran automáticamente.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from bs4 import BeautifulSoup

from presupuesto.parsers.base import MovimientoCrudo, ParserBase

# Texto que identifica inequívocamente el fichero como extracto de Openbank.
# Sin acento en "Operación" para ser robusto ante diferencias de encoding.
_MARCADOR_DETECCION = "fecha operaci"

# Cabeceras de la fila de datos (en minúsculas, sin tildes para comparación robusta)
_CABECERA_FECHA = "fecha operación"
_CABECERA_CONCEPTO = "concepto"
_CABECERA_IMPORTE = "importe"


def _normalizar(texto: str) -> str:
    """Minúsculas, sin tildes, sin espacios extra."""
    tabla = str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")
    return texto.translate(tabla).lower().strip()


def _parsear_fecha_openbank(valor: str) -> date:
    """Convierte 'DD/MM/YYYY' a date."""
    valor = valor.strip()
    try:
        dia, mes, año = valor.split("/")
        return date(int(año), int(mes), int(dia))
    except ValueError as e:
        raise ValueError(f"Fecha de Openbank no reconocida: '{valor}'") from e


def _parsear_importe_openbank(valor: str) -> Decimal:
    """Convierte formato europeo ('2.308,10', '-1.200,00') a Decimal."""
    valor = valor.strip()
    # Eliminar el separador de miles (punto) y convertir la coma decimal a punto
    valor = valor.replace(".", "").replace(",", ".")
    try:
        return Decimal(valor)
    except InvalidOperation as e:
        raise ValueError(f"Importe de Openbank no reconocido: '{valor}'") from e


def _es_fila_de_datos(celdas: list[str]) -> bool:
    """Devuelve True si la fila tiene el aspecto de un movimiento (fecha DD/MM/YYYY en col 1)."""
    if len(celdas) < 8:
        return False
    return bool(re.match(r"^\d{2}/\d{2}/\d{4}$", celdas[1].strip()))


class ParserOpenbank(ParserBase):
    """Parser para extractos XLS (HTML) de Openbank."""

    def puede_parsear(self, ruta_archivo: str) -> bool:
        """Detecta si el archivo es un extracto de Openbank.

        Comprueba que tenga extensión .xls y que el contenido HTML
        incluya la cabecera característica 'Fecha Operaci' (sin acento
        para ser robusto ante variaciones de encoding del fichero).
        """
        ruta = Path(ruta_archivo)
        if ruta.suffix.lower() != ".xls":
            return False
        try:
            # Leer los primeros 8 KB; probar UTF-8 y latin-1
            raw = ruta.read_bytes()[:8192]
            for enc in ("utf-8", "iso-8859-1"):
                try:
                    fragmento = raw.decode(enc, errors="strict").lower()
                    if _marcador_deteccion in fragmento:
                        return True
                except UnicodeDecodeError:
                    continue
            return False
        except Exception:
            return False

    def parsear(self, ruta_archivo: str) -> list[MovimientoCrudo]:
        """Extrae los movimientos del HTML de Openbank."""
        ruta = Path(ruta_archivo)
        contenido = ruta.read_text(encoding="iso-8859-1")
        soup = BeautifulSoup(contenido, "html.parser")

        table = soup.find("table")
        if not table:
            raise ValueError(f"No se encontró ninguna tabla en {ruta.name}")

        movimientos: list[MovimientoCrudo] = []

        for fila in table.find_all("tr"):
            celdas = [td.get_text(strip=True) for td in fila.find_all(["td", "th"])]

            if not _es_fila_de_datos(celdas):
                continue

            # Columnas reales están en posiciones impares (0, 2, 4… son separadores vacíos)
            fecha_str = celdas[1]
            concepto_raw = celdas[5]
            importe_str = celdas[7]

            if not importe_str:
                continue

            fecha = _parsear_fecha_openbank(fecha_str)
            importe = _parsear_importe_openbank(importe_str)
            concepto = " ".join(concepto_raw.split())  # normalizar espacios internos

            concepto_original = f"{fecha_str} | {concepto_raw} | {importe_str}"

            movimientos.append(MovimientoCrudo(
                fecha=fecha,
                concepto=concepto,
                importe=importe,
                concepto_original=concepto_original,
            ))

        return movimientos


# Constante usada tanto en puede_parsear como en la lógica interna
_marcador_deteccion = _MARCADOR_DETECCION
