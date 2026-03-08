"""Parser de extractos bancarios de Kutxabank.

Kutxabank exporta un XLS binario real (formato OLE2 / BIFF8) con esta estructura:

- Una única hoja llamada "Listado".
- Filas iniciales de metadatos y vacías.
- Fila de cabecera: fecha | concepto | fecha valor | importe | saldo
- Filas de datos a partir de la fila siguiente a la cabecera (algunas vacías intercaladas).
- Fechas almacenadas como cadena "DD/MM/YYYY".
- Importes almacenados como float (positivo = ingreso, negativo = gasto).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import xlrd

from presupuesto.parsers.base import MovimientoCrudo, ParserBase

# Magic bytes de OLE2 (XLS binario real), distintos del HTML disfrazado de XLS
_MAGIC_OLE2 = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

# Cabeceras esperadas en la fila de encabezado (en minúsculas)
_CABECERAS_ESPERADAS = {"fecha", "concepto", "importe"}


def _parsear_fecha(valor: str) -> date:
    """Convierte 'DD/MM/YYYY' a date."""
    valor = valor.strip()
    try:
        dia, mes, año = valor.split("/")
        return date(int(año), int(mes), int(dia))
    except ValueError as e:
        raise ValueError(f"Fecha de Kutxabank no reconocida: '{valor}'") from e


def _fila_a_strings(hoja, fila: int) -> list[str]:
    """Devuelve los valores de una fila como strings limpios."""
    return [str(hoja.cell(fila, c).value).strip() for c in range(hoja.ncols)]


def _es_fila_cabecera(valores: list[str]) -> bool:
    """Devuelve True si la fila contiene las cabeceras de Kutxabank."""
    valores_lower = {v.lower() for v in valores if v}
    return _CABECERAS_ESPERADAS.issubset(valores_lower)


class ParserKutxabank(ParserBase):
    """Parser para extractos XLS binarios de Kutxabank."""

    def puede_parsear(self, ruta_archivo: str) -> bool:
        """Detecta si el archivo es un XLS binario de Kutxabank.

        Comprueba los magic bytes OLE2 y que la hoja contenga las
        cabeceras características de Kutxabank.
        """
        ruta = Path(ruta_archivo)
        if ruta.suffix.lower() != ".xls":
            return False
        try:
            if ruta.read_bytes()[:8] != _MAGIC_OLE2:
                return False
            wb = xlrd.open_workbook(str(ruta), logfile=open("/dev/null", "w"))
            ws = wb.sheet_by_index(0)
            for r in range(min(10, ws.nrows)):
                if _es_fila_cabecera(_fila_a_strings(ws, r)):
                    return True
            return False
        except Exception:
            return False

    def parsear(self, ruta_archivo: str) -> list[MovimientoCrudo]:
        """Extrae los movimientos del XLS de Kutxabank."""
        ruta = Path(ruta_archivo)
        wb = xlrd.open_workbook(str(ruta), logfile=open("/dev/null", "w"))
        ws = wb.sheet_by_index(0)

        # Localizar la fila de cabecera y mapear columnas
        col_fecha = col_concepto = col_importe = None
        fila_inicio = None

        for r in range(ws.nrows):
            valores = _fila_a_strings(ws, r)
            if _es_fila_cabecera(valores):
                valores_lower = [v.lower() for v in valores]
                col_fecha = valores_lower.index("fecha")
                col_concepto = valores_lower.index("concepto")
                col_importe = valores_lower.index("importe")
                fila_inicio = r + 1
                break

        if fila_inicio is None:
            raise ValueError(f"No se encontró la fila de cabecera en {ruta.name}")

        movimientos: list[MovimientoCrudo] = []

        for r in range(fila_inicio, ws.nrows):
            fecha_val = ws.cell(r, col_fecha).value
            concepto_val = ws.cell(r, col_concepto).value
            importe_val = ws.cell(r, col_importe).value

            fecha_str = str(fecha_val).strip()
            concepto_raw = str(concepto_val).strip()
            importe_str = str(importe_val).strip()

            # Saltar filas vacías o sin fecha
            if not fecha_str or not concepto_raw or not importe_str:
                continue

            fecha = _parsear_fecha(fecha_str)
            # xlrd devuelve floats; convertir via string para evitar imprecisión
            importe = Decimal(importe_str).quantize(Decimal("0.01"))
            concepto = " ".join(concepto_raw.split())  # normalizar espacios

            concepto_original = f"{fecha_str} | {concepto_raw} | {importe_str}"

            movimientos.append(MovimientoCrudo(
                fecha=fecha,
                concepto=concepto,
                importe=importe,
                concepto_original=concepto_original,
            ))

        return movimientos
