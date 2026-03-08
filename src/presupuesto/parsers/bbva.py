"""Parser de extractos bancarios de BBVA.

BBVA exporta un XLSX con una hoja "Informe BBVA" y esta estructura:

- Fila 2: título "Latest transactions"
- Fila 3: fecha de generación del informe
- Fila 5: cabecera — col B: Eff. Date | col C: Date | col D: Item |
          col E: Transaction | col F: Amount | col H: Available | col J: Comments
- Datos desde fila 6, sin filas vacías intercaladas.

Particularidades:
- Fechas en formato MM/DD/YYYY (formato americano).
- Importe en col F como float (negativo = gasto).
- Col D (Item): nombre del comercio o tipo genérico de operación.
- Col E (Transaction): descripción adicional (concepto de transferencia, tipo de pago).
- Para tarjeta, Item tiene el comercio ("Netflix.com", "Bazar chinatown").
- Para transferencias, Item es genérico ("Transfer received") y Transaction tiene el detalle.
- Para domiciliaciones, Item tiene el proveedor ("Vodafone debit", "Debit digi spain telecom sa").
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import openpyxl

from presupuesto.parsers.base import MovimientoCrudo, ParserBase

# Items genéricos donde Transaction o Comments tienen la info real
_ITEMS_GENERICOS = re.compile(
    r"^(transfer (received|completed)|service company debit|"
    r"fee for |credit interest|debit interest)",
    re.IGNORECASE,
)

# Items genéricos donde Comments puede tener el proveedor real
_ITEMS_USA_COMMENTS = re.compile(
    r"^service company debit$",
    re.IGNORECASE,
)

# Patterns en Transaction que no aportan info (mejor ignorarlos)
_TRANSACTION_GENERICA = re.compile(
    r"^(card payment|debit no \d+|payment of sepa direct debit)$",
    re.IGNORECASE,
)

# Prefijo numérico en Comments: "N 2026061002269417 Aguas Municipales..."
_RE_PREFIJO_COMMENTS = re.compile(r"^[N]\s+\d+\s+", re.IGNORECASE)

# Columnas (1-based) en la hoja
_COL_FECHA_EF = 2   # Eff. Date
_COL_ITEM = 4       # Item
_COL_TRANS = 5      # Transaction
_COL_IMPORTE = 6    # Amount
_COL_COMMENTS = 10  # Comments (proveedor real en domiciliaciones)


def _limpiar_comments(texto: str) -> str:
    """Elimina el prefijo 'N 123456789 ' de los Comments de BBVA."""
    return _RE_PREFIJO_COMMENTS.sub("", texto).strip()


def _parsear_fecha(valor: str) -> date:
    """Convierte 'MM/DD/YYYY' (formato BBVA) a date."""
    valor = valor.strip()
    try:
        mes, dia, año = valor.split("/")
        return date(int(año), int(mes), int(dia))
    except ValueError as e:
        raise ValueError(f"Fecha de BBVA no reconocida: '{valor}'") from e


def _construir_concepto(item: str, transaction: str, comments: str) -> str:
    """Elige el texto más informativo como concepto.

    Prioridad:
    1. 'Service company debit' → Comments (tiene el proveedor real, p.ej. Aguas Municipales).
    2. Transfers (Item genérico) → Transaction.
    3. Transaction genérica (Card payment, Debit no...) → solo Item.
    4. Ambos con info → "{Item} - {Transaction}".
    """
    item        = " ".join(item.split())
    transaction = " ".join(transaction.split())
    comments    = " ".join(comments.split())

    if not item:
        return transaction or comments

    # Domiciliaciones de empresa: los Comments tienen el nombre real del proveedor
    if _ITEMS_USA_COMMENTS.match(item):
        comentario_limpio = _limpiar_comments(comments)
        if comentario_limpio:
            return comentario_limpio

    if not transaction or _TRANSACTION_GENERICA.match(transaction):
        return item
    if _ITEMS_GENERICOS.match(item):
        return transaction

    return f"{item} - {transaction}"


class ParserBBVA(ParserBase):
    """Parser para extractos XLSX de BBVA."""

    def puede_parsear(self, ruta_archivo: str) -> bool:
        """Detecta si el archivo es un extracto XLSX de BBVA.

        Comprueba la extensión .xlsx y que la hoja contenga la cabecera
        característica de BBVA ("Eff. Date" e "Item" en la fila 5).
        """
        ruta = Path(ruta_archivo)
        if ruta.suffix.lower() != ".xlsx":
            return False
        try:
            wb = openpyxl.load_workbook(str(ruta), read_only=True, data_only=True)
            ws = wb.active
            # Buscar la fila de cabecera en las primeras 10 filas
            for row in ws.iter_rows(min_row=1, max_row=10, values_only=True):
                valores = [str(v).strip().lower() for v in row if v is not None]
                if "eff. date" in valores and "item" in valores and "amount" in valores:
                    return True
            return False
        except Exception:
            return False

    def parsear(self, ruta_archivo: str) -> list[MovimientoCrudo]:
        """Extrae los movimientos del XLSX de BBVA."""
        ruta = Path(ruta_archivo)
        wb = openpyxl.load_workbook(str(ruta), data_only=True)
        ws = wb.active

        # Localizar fila de cabecera y mapear columnas por nombre
        col_fecha = col_item = col_trans = col_importe = None
        fila_inicio = None

        col_comments = None
        for r_idx, row in enumerate(ws.iter_rows(min_row=1, max_row=10, values_only=True), start=1):
            valores_lower = [str(v).strip().lower() if v is not None else "" for v in row]
            if "eff. date" in valores_lower and "amount" in valores_lower:
                col_fecha    = valores_lower.index("eff. date") + 1
                col_item     = valores_lower.index("item") + 1
                col_trans    = valores_lower.index("transaction") + 1
                col_importe  = valores_lower.index("amount") + 1
                col_comments = valores_lower.index("comments") + 1 if "comments" in valores_lower else None
                fila_inicio  = r_idx + 1
                break

        if fila_inicio is None:
            raise ValueError(f"No se encontró la fila de cabecera en {ruta.name}")

        movimientos: list[MovimientoCrudo] = []

        for row in ws.iter_rows(min_row=fila_inicio, values_only=True):
            fecha_val    = row[col_fecha - 1]
            item_val     = row[col_item - 1]
            trans_val    = row[col_trans - 1]
            importe_val  = row[col_importe - 1]
            comments_val = row[col_comments - 1] if col_comments else None

            if fecha_val is None or importe_val is None:
                continue

            fecha_str    = str(fecha_val).strip()
            item_raw     = str(item_val).strip() if item_val else ""
            trans_raw    = str(trans_val).strip() if trans_val else ""
            comments_raw = str(comments_val).strip() if comments_val else ""
            importe_str  = str(importe_val).strip()

            if not fecha_str:
                continue

            fecha    = _parsear_fecha(fecha_str)
            importe  = Decimal(importe_str).quantize(Decimal("0.01"))
            concepto = _construir_concepto(item_raw, trans_raw, comments_raw)

            concepto_original = f"{fecha_str} | {item_raw}"
            if trans_raw:
                concepto_original += f" | {trans_raw}"

            movimientos.append(MovimientoCrudo(
                fecha=fecha,
                concepto=concepto,
                importe=importe,
                concepto_original=concepto_original,
            ))

        return movimientos
