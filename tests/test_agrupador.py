"""Tests del módulo agrupador."""

from decimal import Decimal

import pytest

from presupuesto.agrupador import agrupar_movimientos
from presupuesto.categorizar import MovimientoCategorizado


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _mov(**kwargs) -> MovimientoCategorizado:
    defaults = dict(
        año=2026, mes="Mar",
        categoria1="Alimentación", categoria2="Supermercados", categoria3="",
        entidad="", importe=Decimal("-25.00"), proveedor="Eroski",
        tipo_gasto="Discrecionales", cuenta="Cuenta Nomina",
        banco="Openbank", tipo_cuenta="Activos liquidos", estado="Real",
    )
    defaults.update(kwargs)
    return MovimientoCategorizado(**defaults)


# ---------------------------------------------------------------------------
# Agrupación correcta
# ---------------------------------------------------------------------------

def test_cinco_iguales_se_agrupan_en_uno():
    movs = [_mov() for _ in range(5)]
    resultado = agrupar_movimientos(movs)
    assert len(resultado) == 1


def test_importe_se_suma():
    movs = [_mov(importe=Decimal("-25.00")) for _ in range(5)]
    resultado = agrupar_movimientos(movs)
    assert resultado[0].importe == Decimal("-125.00")


def test_n_originales_refleja_el_grupo():
    movs = [_mov() for _ in range(5)]
    resultado = agrupar_movimientos(movs)
    assert resultado[0].n_originales == 5


def test_movimiento_unico_n_originales_es_1():
    resultado = agrupar_movimientos([_mov()])
    assert resultado[0].n_originales == 1


def test_importes_distintos_se_suman_correctamente():
    movs = [
        _mov(importe=Decimal("-10.00")),
        _mov(importe=Decimal("-15.50")),
        _mov(importe=Decimal("-4.50")),
    ]
    resultado = agrupar_movimientos(movs)
    assert len(resultado) == 1
    assert resultado[0].importe == Decimal("-30.00")


# ---------------------------------------------------------------------------
# Campos que impiden la agrupación
# ---------------------------------------------------------------------------

def test_distinta_categoria2_no_agrupa():
    movs = [
        _mov(categoria2="Supermercados"),
        _mov(categoria2="Restaurantes"),
    ]
    assert len(agrupar_movimientos(movs)) == 2


def test_distinto_mes_no_agrupa():
    movs = [_mov(mes="Ene"), _mov(mes="Feb")]
    assert len(agrupar_movimientos(movs)) == 2


def test_distinto_año_no_agrupa():
    movs = [_mov(año=2025), _mov(año=2026)]
    assert len(agrupar_movimientos(movs)) == 2


def test_distinta_categoria1_no_agrupa():
    movs = [_mov(categoria1="Alimentación"), _mov(categoria1="Ocio")]
    assert len(agrupar_movimientos(movs)) == 2


def test_distinta_cuenta_no_agrupa():
    movs = [_mov(cuenta="Cuenta Nomina"), _mov(cuenta="Cuenta Ocio")]
    assert len(agrupar_movimientos(movs)) == 2


def test_distinto_proveedor_no_agrupa():
    movs = [_mov(proveedor="Eroski"), _mov(proveedor="Mercadona")]
    assert len(agrupar_movimientos(movs)) == 2


def test_distinto_tipo_gasto_no_agrupa():
    movs = [_mov(tipo_gasto="Discrecionales"), _mov(tipo_gasto="Fijos")]
    assert len(agrupar_movimientos(movs)) == 2


# ---------------------------------------------------------------------------
# Mezcla de grupos
# ---------------------------------------------------------------------------

def test_dos_grupos_distintos_genera_dos_filas():
    movs = [
        _mov(categoria2="Supermercados", importe=Decimal("-10.00")),
        _mov(categoria2="Supermercados", importe=Decimal("-20.00")),
        _mov(categoria2="Restaurantes",  importe=Decimal("-15.00")),
        _mov(categoria2="Restaurantes",  importe=Decimal("-25.00")),
    ]
    resultado = agrupar_movimientos(movs)
    assert len(resultado) == 2
    importes = {r.importe for r in resultado}
    assert Decimal("-30.00") in importes
    assert Decimal("-40.00") in importes


def test_preserva_orden_primera_aparicion():
    movs = [
        _mov(categoria2="Restaurantes"),
        _mov(categoria2="Supermercados"),
        _mov(categoria2="Restaurantes"),
    ]
    resultado = agrupar_movimientos(movs)
    assert resultado[0].categoria2 == "Restaurantes"
    assert resultado[1].categoria2 == "Supermercados"


def test_lista_vacia_devuelve_lista_vacia():
    assert agrupar_movimientos([]) == []


def test_campos_no_agrupacion_se_copian_del_representante():
    """banco, tipo_cuenta, confianza, etc. se copian del primer movimiento del grupo."""
    movs = [
        _mov(banco="Openbank", tipo_cuenta="Activos liquidos", confianza="alta"),
        _mov(banco="Openbank", tipo_cuenta="Activos liquidos", confianza="media"),
    ]
    resultado = agrupar_movimientos(movs)
    assert resultado[0].banco == "Openbank"
    assert resultado[0].tipo_cuenta == "Activos liquidos"
    # Se toma del primero
    assert resultado[0].confianza == "alta"
