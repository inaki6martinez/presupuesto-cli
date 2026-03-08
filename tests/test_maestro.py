"""Tests del módulo maestro.py usando el archivo presupuesto.xlsx real."""

import pytest

from presupuesto.maestro import DatosMaestros

RUTA_XLSX = "/mnt/c/Users/inaki.martinez/OneDrive/presupuesto/presupuesto.xlsx"


@pytest.fixture(scope="module")
def maestro():
    """Carga DatosMaestros una sola vez para todos los tests del módulo."""
    pytest.importorskip("openpyxl")
    import os
    if not os.path.exists(RUTA_XLSX):
        pytest.skip(f"presupuesto.xlsx no encontrado en {RUTA_XLSX}")
    return DatosMaestros(RUTA_XLSX)


# --- Hoja Maestro ---

def test_anos_son_enteros(maestro):
    assert all(isinstance(a, int) for a in maestro.anos)
    assert 2024 in maestro.anos

def test_meses_son_doce(maestro):
    assert len(maestro.meses) == 12
    assert maestro.meses[0] == "Ene"
    assert maestro.meses[-1] == "Dic"

def test_categorias1_no_vacias(maestro):
    assert len(maestro.categorias1) > 0
    assert "Alimentación" in maestro.categorias1
    assert "Ingresos" in maestro.categorias1

def test_categorias2_no_vacias(maestro):
    assert len(maestro.categorias2) > 0
    assert "Compra" in maestro.categorias2

def test_categorias3_no_vacias(maestro):
    assert len(maestro.categorias3) > 0

def test_proveedores_no_vacios(maestro):
    assert len(maestro.proveedores) > 0
    assert "Eroski" in maestro.proveedores
    assert "Netflix" in maestro.proveedores

def test_tipos_gasto(maestro):
    esperados = {"Fijos", "Optimizable", "Discrecionales", "Excepcionales"}
    assert esperados.issubset(set(maestro.tipos_gasto))

def test_cuentas_no_vacias(maestro):
    assert "Cuenta Nomina" in maestro.cuentas
    assert "Kutxabank" in maestro.cuentas

def test_bancos_no_vacios(maestro):
    assert "Openbank" in maestro.bancos
    assert "Kutxabank" in maestro.bancos

def test_tipos_cuenta(maestro):
    assert "Activos liquidos" in maestro.tipos_cuenta
    assert "Pasivo" in maestro.tipos_cuenta


# --- Validación ---

def test_validar_valor_correcto(maestro):
    assert maestro.validar("categorias1", "Alimentación") is True

def test_validar_valor_incorrecto(maestro):
    assert maestro.validar("categorias1", "CategoriaSinExistir") is False

def test_validar_campo_desconocido(maestro):
    with pytest.raises(ValueError, match="Campo desconocido"):
        maestro.validar("campo_inventado", "x")


# --- Hoja Claves ---

def test_autocompletar_cuenta_conocida(maestro):
    banco, tipo = maestro.autocompletar_cuenta("Cuenta Nomina")
    assert banco == "Openbank"
    assert tipo == "Activos liquidos"

def test_autocompletar_kutxabank(maestro):
    banco, tipo = maestro.autocompletar_cuenta("Kutxabank")
    assert banco == "Kutxabank"
    assert tipo == "Activos liquidos"

def test_autocompletar_hipoteca(maestro):
    banco, tipo = maestro.autocompletar_cuenta("Hipoteca Piso")
    assert banco == "BBVA"
    assert tipo == "Pasivo"

def test_autocompletar_cuenta_desconocida(maestro):
    banco, tipo = maestro.autocompletar_cuenta("Cuenta Inexistente")
    assert banco is None
    assert tipo is None

def test_claves_cuentas_completo(maestro):
    claves = maestro.claves_cuentas()
    assert "Cuenta Nomina" in claves
    assert "Ahorro colchon" in claves
    assert claves["Ahorro colchon"] == ("Trade republic", "Activos liquidos")
