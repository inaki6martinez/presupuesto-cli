"""Tests del módulo de contrapartida de aportaciones a fondos."""

from __future__ import annotations

import dataclasses
from decimal import Decimal
from unittest.mock import MagicMock

from presupuesto.categorizar import MovimientoCategorizado
from presupuesto.fondos import (
    es_aportacion_fondos,
    expandir_fondos,
    generar_contrapartida,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _maestros_mock():
    m = MagicMock()
    m.autocompletar_cuenta.return_value = ("Indexa Capital", "Activos medio liquidos")
    return m


def _mov_fondos(**kwargs) -> MovimientoCategorizado:
    defaults = dict(
        año=2026, mes="Ago",
        categoria1="Ahorro", categoria2="Fondos", categoria3="",
        entidad="Iñaki", importe=Decimal("-250.00"), proveedor="",
        tipo_gasto="Discrecionales", cuenta="Cuenta Nomina Abanca",
        banco="Abanca", tipo_cuenta="Activos liquidos", estado="Real",
        confianza="alta", fuente="regla: FONDOS",
        requiere_confirmacion=False,
        concepto_original="18-08-2026 | FONDOS",
    )
    defaults.update(kwargs)
    return MovimientoCategorizado(**defaults)


# ---------------------------------------------------------------------------
# es_aportacion_fondos
# ---------------------------------------------------------------------------

def test_es_aportacion_fondos_detecta_correctamente():
    assert es_aportacion_fondos(_mov_fondos()) is True

def test_no_es_aportacion_si_categoria_diferente():
    assert es_aportacion_fondos(_mov_fondos(categoria1="Ahorro", categoria2="Colchon")) is False

def test_no_es_aportacion_si_ya_es_la_cuenta_fondos():
    """La propia cuenta Fondos no debe generarse contrapartida a sí misma."""
    assert es_aportacion_fondos(_mov_fondos(cuenta="Fondos")) is False


# ---------------------------------------------------------------------------
# generar_contrapartida
# ---------------------------------------------------------------------------

def test_contrapartida_importe_signo_opuesto():
    mov_balance = generar_contrapartida(_mov_fondos(), _maestros_mock())
    assert mov_balance.importe == Decimal("250.00")

def test_contrapartida_categorias():
    mov_balance = generar_contrapartida(_mov_fondos(), _maestros_mock())
    assert mov_balance.categoria1 == "Finanzas"
    assert mov_balance.categoria2 == "Balance"
    assert mov_balance.categoria3 == ""
    assert mov_balance.entidad == ""
    assert mov_balance.tipo_gasto == ""

def test_contrapartida_cuenta_y_banco():
    mov_balance = generar_contrapartida(_mov_fondos(), _maestros_mock())
    assert mov_balance.cuenta == "Fondos"
    assert mov_balance.banco == "Indexa Capital"
    assert mov_balance.tipo_cuenta == "Activos medio liquidos"

def test_contrapartida_confianza_alta_sin_confirmacion():
    mov_balance = generar_contrapartida(_mov_fondos(), _maestros_mock())
    assert mov_balance.confianza == "alta"
    assert mov_balance.requiere_confirmacion is False
    assert mov_balance.fuente == "fondos:balance"

def test_contrapartida_concepto_original_lleva_sufijo():
    mov_balance = generar_contrapartida(_mov_fondos(), _maestros_mock())
    assert mov_balance.concepto_original.endswith("[balance]")

def test_contrapartida_conserva_año_y_mes():
    mov_balance = generar_contrapartida(_mov_fondos(año=2026, mes="Jul"), _maestros_mock())
    assert mov_balance.año == 2026
    assert mov_balance.mes == "Jul"


# ---------------------------------------------------------------------------
# expandir_fondos (lista completa)
# ---------------------------------------------------------------------------

def test_expandir_fondos_añade_contrapartida_tras_el_original():
    mov = _mov_fondos()
    resultado = expandir_fondos([mov], _maestros_mock())
    assert len(resultado) == 2
    assert resultado[0] is mov
    assert resultado[1].cuenta == "Fondos"
    assert resultado[1].importe == -mov.importe

def test_expandir_fondos_no_afecta_otros_movimientos():
    mov_otro = dataclasses.replace(
        _mov_fondos(), categoria1="Alimentación", categoria2="Compra", entidad="",
    )
    resultado = expandir_fondos([mov_otro, mov_otro], _maestros_mock())
    assert resultado == [mov_otro, mov_otro]

def test_expandir_fondos_mezcla_movimientos():
    mov_otro = dataclasses.replace(
        _mov_fondos(), categoria1="Alimentación", categoria2="Compra", entidad="",
    )
    mov_fondos = _mov_fondos()
    resultado = expandir_fondos([mov_otro, mov_fondos, mov_otro], _maestros_mock())
    # mov_otro x2 + (mov_fondos + su contrapartida) = 4
    assert len(resultado) == 4
    assert resultado[0] is mov_otro
    assert resultado[1] is mov_fondos
    assert resultado[2].fuente == "fondos:balance"
    assert resultado[3] is mov_otro
