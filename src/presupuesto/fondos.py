"""Generación automática de la contrapartida de aportaciones a Fondos.

Cuando se detecta un movimiento de aportación a fondos de inversión
(Ahorro/Fondos), se añade automáticamente su contrapartida en la cuenta
"Fondos": el mismo importe en positivo, categorizado como Finanzas/Balance.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from presupuesto.categorizar import MovimientoCategorizado
    from presupuesto.maestro import DatosMaestros

_CATEGORIA1_FONDOS = "Ahorro"
_CATEGORIA2_FONDOS = "Fondos"

_CUENTA_FONDOS = "Fondos"


def es_aportacion_fondos(mov: MovimientoCategorizado) -> bool:
    """True si el movimiento es una aportación a fondos a la que generar contrapartida."""
    return (
        mov.categoria1 == _CATEGORIA1_FONDOS
        and mov.categoria2 == _CATEGORIA2_FONDOS
        and mov.cuenta != _CUENTA_FONDOS
    )


def generar_contrapartida(
    mov: MovimientoCategorizado,
    maestros: DatosMaestros,
) -> MovimientoCategorizado:
    """Genera el movimiento de contrapartida en la cuenta Fondos.

    Mismo importe en signo opuesto (positivo si la aportación es una
    salida), categorizado como Finanzas/Balance.
    """
    banco, tipo_cuenta = maestros.autocompletar_cuenta(_CUENTA_FONDOS)
    concepto_base = mov.concepto_original or ""

    return dataclasses.replace(
        mov,
        importe      = -mov.importe,
        categoria1   = "Finanzas",
        categoria2   = "Balance",
        categoria3   = "",
        entidad      = "",
        proveedor    = "",
        tipo_gasto   = "",
        cuenta       = _CUENTA_FONDOS,
        banco        = banco,
        tipo_cuenta  = tipo_cuenta,
        confianza    = "alta",
        fuente       = "fondos:balance",
        requiere_confirmacion = False,
        concepto_original = f"{concepto_base} [balance]",
    )


def expandir_fondos(
    movimientos: list[MovimientoCategorizado],
    maestros: DatosMaestros,
) -> list[MovimientoCategorizado]:
    """Añade la contrapartida a los movimientos de aportación a fondos de la lista.

    A diferencia de la hipoteca, la aportación original no se sustituye:
    se conserva y se añade la fila de contrapartida a continuación.
    """
    resultado: list[MovimientoCategorizado] = []
    for mov in movimientos:
        resultado.append(mov)
        if es_aportacion_fondos(mov):
            resultado.append(generar_contrapartida(mov, maestros))
    return resultado
