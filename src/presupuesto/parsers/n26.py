"""Parser de extractos bancarios de N26 (formato CSV).

N26 exporta un CSV con estas cabeceras (pueden variar ligeramente entre versiones):
  Booking Date, Value Date, Partner Name, Partner Iban, Type,
  Payment Reference, Account Name, Amount (EUR), ...

Notas sobre el formato real:
- Encoding: UTF-8 (a veces con BOM).
- El campo "Partner Name" puede contener saltos de línea dentro de las comillas
  (p. ej. la cuota de N26 Metal aparece como "N26\n").
- El importe está en "Amount (EUR)" (o similar si la cuenta es en otra moneda).
- Cuando Partner Name es poco descriptivo (transferencias propias, cuotas),
  "Payment Reference" aporta mejor contexto.
"""

from __future__ import annotations

import csv
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from presupuesto.parsers.base import MovimientoCrudo, ParserBase

# Cabeceras identificativas de N26 — basta con que estén todas en la primera fila
_CABECERAS_REQUERIDAS = {"booking date", "partner name", "amount"}

# Columnas que pueden contener el importe según la versión del CSV
_POSIBLES_COLUMNAS_IMPORTE = ("amount (eur)", "amount")

# Partner Names que aportan poca información por sí solos; en ese caso
# se usa Payment Reference como concepto principal.
_NOMBRES_POCO_DESCRIPTIVOS = re.compile(
    r"^(n26|cuenta\s+de\s+ahorro|cuenta\s+principal)$",
    re.IGNORECASE,
)


def _detectar_encoding(ruta: Path) -> str:
    """Prueba UTF-8-sig (con BOM) y UTF-8; cae a latin-1 si falla."""
    for enc in ("utf-8-sig", "utf-8"):
        try:
            ruta.read_text(encoding=enc)
            return enc
        except UnicodeDecodeError:
            pass
    return "latin-1"


def _limpiar_texto(texto: str) -> str:
    """Elimina saltos de línea internos y espacios sobrantes."""
    return " ".join(texto.split())


def _parsear_importe(valor: str) -> Decimal:
    """Convierte una cadena de importe a Decimal.

    Acepta formatos: '-4.3', '50.00', '9262,42' (coma decimal europea).
    """
    valor = valor.strip().replace(",", ".")
    try:
        return Decimal(valor)
    except InvalidOperation as e:
        raise ValueError(f"Importe no reconocido: '{valor}'") from e


def _parsear_fecha(valor: str) -> date:
    """Convierte 'YYYY-MM-DD' a date."""
    try:
        return date.fromisoformat(valor.strip())
    except ValueError as e:
        raise ValueError(f"Fecha no reconocida: '{valor}'") from e


def _construir_concepto(nombre: str, referencia: str) -> str:
    """Elige el texto más descriptivo como concepto del movimiento."""
    nombre = _limpiar_texto(nombre)
    referencia = _limpiar_texto(referencia)

    if not nombre or _NOMBRES_POCO_DESCRIPTIVOS.match(nombre):
        return referencia or nombre
    return nombre


class ParserN26(ParserBase):
    """Parser para extractos CSV de N26."""

    def puede_parsear(self, ruta_archivo: str) -> bool:
        """Detecta si el archivo es un CSV de N26 comprobando sus cabeceras."""
        ruta = Path(ruta_archivo)
        if ruta.suffix.lower() != ".csv":
            return False
        try:
            enc = _detectar_encoding(ruta)
            with open(ruta, encoding=enc, newline="") as f:
                lector = csv.reader(f)
                cabeceras = next(lector, None)
            if cabeceras is None:
                return False
            cabeceras_lower = {c.strip().lower() for c in cabeceras}
            return _CABECERAS_REQUERIDAS.issubset(cabeceras_lower) or all(
                any(req in h for h in cabeceras_lower)
                for req in _CABECERAS_REQUERIDAS
            )
        except Exception:
            return False

    def parsear(self, ruta_archivo: str) -> list[MovimientoCrudo]:
        """Extrae los movimientos del CSV de N26."""
        ruta = Path(ruta_archivo)
        enc = _detectar_encoding(ruta)

        movimientos: list[MovimientoCrudo] = []

        with open(ruta, encoding=enc, newline="") as f:
            lector = csv.DictReader(f)

            # Normalizar nombres de cabecera a minúsculas para ser tolerantes
            # ante mayúsculas y variaciones de formato
            cabeceras_originales = lector.fieldnames or []
            mapa = {c.strip().lower(): c for c in cabeceras_originales}

            col_fecha = mapa.get("booking date")
            col_nombre = mapa.get("partner name")
            col_referencia = mapa.get("payment reference")

            # Columna de importe: buscar la primera que exista
            col_importe = None
            for candidato in _POSIBLES_COLUMNAS_IMPORTE:
                if candidato in mapa:
                    col_importe = mapa[candidato]
                    break

            if not all([col_fecha, col_nombre, col_importe]):
                raise ValueError(
                    f"El CSV no tiene las columnas esperadas de N26. "
                    f"Columnas encontradas: {cabeceras_originales}"
                )

            for fila in lector:
                # Construir la línea original antes de procesar
                concepto_original = " | ".join(
                    f"{k}: {v}" for k, v in fila.items() if v and v.strip()
                )

                fecha_str = (fila.get(col_fecha) or "").strip()
                nombre = fila.get(col_nombre) or ""
                referencia = fila.get(col_referencia) or "" if col_referencia else ""
                importe_str = (fila.get(col_importe) or "").strip()

                # Saltar filas sin fecha o importe (pueden ser líneas vacías al final)
                if not fecha_str or not importe_str:
                    continue

                fecha = _parsear_fecha(fecha_str)
                importe = _parsear_importe(importe_str)
                concepto = _construir_concepto(nombre, referencia)

                movimientos.append(MovimientoCrudo(
                    fecha=fecha,
                    concepto=concepto,
                    importe=importe,
                    concepto_original=concepto_original,
                ))

        return movimientos
