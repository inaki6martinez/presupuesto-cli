"""Parser de extractos bancarios de ING.

ING exporta un XLS binario real (OLE2/BIFF8) con esta estructura:

- Una única hoja llamada 'Movimientos'.
- Filas 0-2: metadatos (número de cuenta, titular, fecha de exportación).
- Fila 3: cabecera — F. VALOR | CATEGORÍA | SUBCATEGORÍA | DESCRIPCIÓN | COMENTARIO | IMPORTE (€) | SALDO (€)
- Datos desde fila 4.

Particularidades:
- La fecha (F. VALOR) se almacena como número serial de Excel (float).
  Se convierte a date con xlrd.xldate_as_datetime().
- El importe está en IMPORTE (€) como float (negativo = gasto).
- La DESCRIPCIÓN ya es legible: "Pago en EROSKI CENTER...",
  "Transferencia recibida de...", "Recibo ...", etc.
- CATEGORÍA y SUBCATEGORÍA son categorías propias de ING; se ignoran
  (el sistema usa sus propias reglas de categorización).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import xlrd

from presupuesto.parsers.base import MovimientoCrudo, ParserBase

_MAGIC_OLE2 = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

# Cabeceras identificativas de ING (en minúsculas)
_CABECERAS_ING = {"f. valor", "descripción", "importe (€)"}


def _fila_valores(hoja, fila: int) -> list:
    return [hoja.cell(fila, c).value for c in range(hoja.ncols)]


def _es_cabecera_ing(valores: list) -> bool:
    lower = {str(v).strip().lower() for v in valores if v != ""}
    return _CABECERAS_ING.issubset(lower)


class ParserING(ParserBase):
    """Parser para extractos XLS de ING."""

    def puede_parsear(self, ruta_archivo: str) -> bool:
        """Detecta si el archivo es un XLS de ING.

        Comprueba los magic bytes OLE2 y que la hoja contenga las
        cabeceras 'F. VALOR', 'DESCRIPCIÓN' e 'IMPORTE (€)'.
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
                if _es_cabecera_ing(_fila_valores(ws, r)):
                    return True
            return False
        except Exception:
            return False

    def parsear(self, ruta_archivo: str) -> list[MovimientoCrudo]:
        """Extrae los movimientos del XLS de ING."""
        ruta = Path(ruta_archivo)
        wb = xlrd.open_workbook(str(ruta), logfile=open("/dev/null", "w"))
        ws = wb.sheet_by_index(0)

        # Localizar cabecera y mapear columnas
        col_fecha = col_desc = col_importe = None
        fila_inicio = None

        for r in range(min(10, ws.nrows)):
            vals = _fila_valores(ws, r)
            if _es_cabecera_ing(vals):
                lower = [str(v).strip().lower() for v in vals]
                col_fecha   = lower.index("f. valor")
                col_desc    = lower.index("descripción")
                col_importe = lower.index("importe (€)")
                fila_inicio = r + 1
                break

        if fila_inicio is None:
            raise ValueError(f"No se encontró la fila de cabecera en {ruta.name}")

        movimientos: list[MovimientoCrudo] = []

        for r in range(fila_inicio, ws.nrows):
            fecha_val   = ws.cell(r, col_fecha).value
            desc_val    = ws.cell(r, col_desc).value
            importe_val = ws.cell(r, col_importe).value

            if fecha_val == "" or fecha_val is None:
                continue
            if importe_val == "" or importe_val is None:
                continue

            # Fecha: serial Excel → date
            fecha = xlrd.xldate_as_datetime(float(fecha_val), wb.datemode).date()

            concepto_raw = str(desc_val).strip() if desc_val else ""
            if not concepto_raw:
                continue

            concepto = " ".join(concepto_raw.split())
            importe  = Decimal(str(importe_val)).quantize(Decimal("0.01"))

            concepto_original = f"{fecha} | {concepto_raw} | {importe_val}"

            movimientos.append(MovimientoCrudo(
                fecha=fecha,
                concepto=concepto,
                importe=importe,
                concepto_original=concepto_original,
            ))

        return movimientos
