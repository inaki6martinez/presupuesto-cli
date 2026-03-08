"""Control de duplicados mediante marcadores de última importación.

Responsabilidades:
1. GestorMarcadores — registra la fecha del último movimiento importado por
   cuenta en ~/.config/presupuesto/marcadores.json.
2. detectar_duplicados — comprueba movimientos agrupados contra filas ya
   existentes en la hoja 'Datos' del xlsx (red de seguridad adicional).
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from presupuesto.categorizar import MovimientoCategorizado
    from presupuesto.parsers.base import MovimientoCrudo

RUTA_MARCADORES_DEFECTO = Path.home() / ".config" / "presupuesto" / "marcadores.json"

_TOLERANCIA_IMPORTE = Decimal("0.01")


class GestorMarcadores:
    """Gestiona el fichero JSON con fechas de última importación por cuenta."""

    def __init__(self, ruta: str | Path = RUTA_MARCADORES_DEFECTO):
        self._ruta = Path(ruta)
        self._datos: dict[str, str] = {}
        self._cargar()

    def _cargar(self) -> None:
        if self._ruta.exists():
            try:
                self._datos = json.loads(self._ruta.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._datos = {}

    def _guardar(self) -> None:
        self._ruta.parent.mkdir(parents=True, exist_ok=True)
        self._ruta.write_text(
            json.dumps(self._datos, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def obtener_marcador(self, cuenta: str) -> date | None:
        """Devuelve la fecha del último movimiento importado para esta cuenta."""
        valor = self._datos.get(cuenta)
        if valor is None:
            return None
        try:
            return date.fromisoformat(valor)
        except ValueError:
            return None

    def actualizar_marcador(self, cuenta: str, fecha: date) -> None:
        """Actualiza el marcador si `fecha` es posterior al marcador existente."""
        existente = self.obtener_marcador(cuenta)
        if existente is None or fecha > existente:
            self._datos[cuenta] = fecha.isoformat()
            self._guardar()

    def filtrar_movimientos(
        self,
        movimientos: list[MovimientoCrudo],
        cuenta: str,
        desde: date | None = None,
    ) -> tuple[list[MovimientoCrudo], int]:
        """Descarta movimientos con fecha ≤ al marcador (o a `desde` si se indica).

        La opción `desde` sobreescribe el marcador guardado (útil para reimportar).

        Returns:
            (movimientos_aceptados, num_descartados)
        """
        fecha_corte = desde if desde is not None else self.obtener_marcador(cuenta)
        if fecha_corte is None:
            return list(movimientos), 0

        aceptados = [m for m in movimientos if m.fecha > fecha_corte]
        descartados = len(movimientos) - len(aceptados)
        return aceptados, descartados


def detectar_duplicados(
    movimientos: list[MovimientoCategorizado],
    ruta_xlsx: str | Path,
) -> list[tuple[MovimientoCategorizado, int]]:
    """Detecta posibles duplicados contra las filas ya existentes en 'Datos'.

    Criterio de coincidencia: Año + Mes + Categoría1 + Categoría2 + Cuenta +
    Importe (tolerancia ±0.01 para absorber redondeos de agrupación).

    Returns lista de (movimiento, numero_fila) para cada posible duplicado.
    """
    import openpyxl

    ruta = Path(ruta_xlsx)
    if not ruta.exists():
        return []

    wb = openpyxl.load_workbook(str(ruta), data_only=True, read_only=True)
    try:
        ws = wb["Datos"]
    except KeyError:
        wb.close()
        return []

    existentes: list[tuple] = []
    for r_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not row or row[0] is None:
            continue
        try:
            año_ex    = int(row[0])
            mes_ex    = str(row[1] or "").strip()
            cat1_ex   = str(row[2] or "").strip()
            cat2_ex   = str(row[3] or "").strip()
            imp_ex    = Decimal(str(row[6] or 0))
            cuenta_ex = str(row[9] or "").strip()
        except (ValueError, TypeError):
            continue
        existentes.append((año_ex, mes_ex, cat1_ex, cat2_ex, imp_ex, cuenta_ex, r_idx))

    wb.close()

    duplicados: list[tuple[MovimientoCategorizado, int]] = []
    for m in movimientos:
        for (año, mes, cat1, cat2, imp, cuenta, fila) in existentes:
            if (
                m.año == año
                and m.mes == mes
                and m.categoria1 == cat1
                and m.categoria2 == cat2
                and m.cuenta == cuenta
                and abs(m.importe - imp) <= _TOLERANCIA_IMPORTE
            ):
                duplicados.append((m, fila))
                break

    return duplicados
