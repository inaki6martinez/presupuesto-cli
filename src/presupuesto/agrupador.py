"""Agrupación de movimientos categorizados para reducir el número de filas xlsx.

Dos movimientos se agrupan si comparten: año, mes, categoría1-3, entidad,
proveedor, tipo_gasto, cuenta y estado. Los importes se suman.
"""

from __future__ import annotations

from decimal import Decimal
from dataclasses import replace

from presupuesto.categorizar import MovimientoCategorizado

_CAMPOS_AGRUPACION = (
    "año", "mes", "categoria1", "categoria2", "categoria3",
    "entidad", "proveedor", "tipo_gasto", "cuenta", "estado",
)


def agrupar_movimientos(
    movimientos: list[MovimientoCategorizado],
) -> list[MovimientoCategorizado]:
    """Agrupa movimientos por campos comunes, sumando sus importes.

    Preserva el orden de primera aparición de cada grupo.
    El campo `n_originales` del resultado indica cuántos movimientos
    originales componen cada fila agrupada.
    """
    grupos: dict[tuple, list[MovimientoCategorizado]] = {}
    orden: list[tuple] = []

    for m in movimientos:
        clave = tuple(getattr(m, campo) for campo in _CAMPOS_AGRUPACION)
        if clave not in grupos:
            grupos[clave] = []
            orden.append(clave)
        grupos[clave].append(m)

    resultado: list[MovimientoCategorizado] = []
    for clave in orden:
        grupo = grupos[clave]
        rep = grupo[0]
        importe_total = sum((m.importe for m in grupo), Decimal("0"))
        resultado.append(replace(
            rep,
            importe=importe_total,
            n_originales=sum(m.n_originales for m in grupo),
            originales=[o for m in grupo for o in m.originales],
        ))

    return resultado
