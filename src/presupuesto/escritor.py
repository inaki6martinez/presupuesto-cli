"""Escritura de movimientos categorizados en presupuesto.xlsx.

Abre el xlsx sin `data_only` para preservar fórmulas. Nunca crea un workbook
nuevo: siempre abre el existente y añade filas al final de la hoja 'Datos'.
Crea un backup automático antes de cualquier escritura.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import openpyxl

if TYPE_CHECKING:
    from presupuesto.categorizar import MovimientoCategorizado


class EscritorDatos:
    """Escribe filas en la hoja 'Datos' de presupuesto.xlsx."""

    def __init__(self, ruta_xlsx: str | Path):
        self._ruta = Path(ruta_xlsx)
        if not self._ruta.exists():
            raise FileNotFoundError(f"No se encontró el archivo: {self._ruta}")

    def crear_backup(self) -> Path:
        """Crea una copia del xlsx con timestamp en el mismo directorio.

        Nombre del backup: presupuesto_backup_YYYYMMDD_HHMMSS.xlsx
        """
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        nombre = f"{self._ruta.stem}_backup_{ts}{self._ruta.suffix}"
        ruta_backup = self._ruta.parent / nombre
        shutil.copy2(str(self._ruta), str(ruta_backup))
        return ruta_backup

    def escribir(
        self,
        movimientos: list[MovimientoCategorizado],
        crear_backup: bool = True,
    ) -> int:
        """Añade los movimientos como nuevas filas en la hoja 'Datos'.

        Columnas escritas (A→M, 13 campos):
        Año | Mes | Cat1 | Cat2 | Cat3 | Entidad | Importe | Proveedor |
        Tipo gasto | Cuenta | Banco | Tipo cuenta | Estado

        Args:
            movimientos:   lista de movimientos ya agrupados.
            crear_backup:  si True (defecto), hace copia antes de escribir.

        Returns el número de filas escritas.
        """
        if not movimientos:
            return 0

        if crear_backup:
            self.crear_backup()

        # Sin data_only para preservar fórmulas existentes
        wb = openpyxl.load_workbook(str(self._ruta))
        ws = wb["Datos"]

        # Localizar primera fila libre: buscar la última fila con datos reales
        primera_libre = 2  # mínimo: fila 2 (tras la cabecera)
        for r in range(ws.max_row, 1, -1):
            if any(ws.cell(r, c).value is not None for c in range(1, 14)):
                primera_libre = r + 1
                break

        for i, m in enumerate(movimientos):
            fila = primera_libre + i
            ws.cell(fila,  1).value = m.año
            ws.cell(fila,  2).value = m.mes
            ws.cell(fila,  3).value = m.categoria1
            ws.cell(fila,  4).value = m.categoria2
            ws.cell(fila,  5).value = m.categoria3
            ws.cell(fila,  6).value = m.entidad
            ws.cell(fila,  7).value = float(m.importe)
            ws.cell(fila,  8).value = m.proveedor
            ws.cell(fila,  9).value = m.tipo_gasto
            ws.cell(fila, 10).value = m.cuenta
            ws.cell(fila, 11).value = m.banco
            ws.cell(fila, 12).value = m.tipo_cuenta
            ws.cell(fila, 13).value = m.estado

        wb.save(str(self._ruta))
        wb.close()

        return len(movimientos)
