"""Tests del módulo reglas.py."""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from presupuesto.reglas import GestorReglas

REGLAS_INICIALES = Path(__file__).parent.parent / "datos" / "reglas_iniciales.json"


@pytest.fixture
def gestor(tmp_path):
    """GestorReglas inicializado en un directorio temporal con las reglas iniciales."""
    ruta = tmp_path / "reglas.json"
    shutil.copy2(REGLAS_INICIALES, ruta)
    return GestorReglas(ruta)


@pytest.fixture
def gestor_vacio(tmp_path):
    """GestorReglas inicializado sin reglas previas (directorio vacío)."""
    ruta = tmp_path / "subdir" / "reglas.json"
    # No copiamos nada: debe inicializarse desde reglas_iniciales.json automáticamente
    return GestorReglas(ruta)


# --- Carga ---

def test_carga_65_reglas(gestor):
    assert gestor.total() == 130

def test_inicializa_desde_reglas_iniciales_si_no_existe(gestor_vacio):
    """Si el fichero no existe, debe copiarse de reglas_iniciales.json."""
    assert gestor_vacio.total() == 130

def test_listar_devuelve_lista(gestor):
    reglas = gestor.listar()
    assert isinstance(reglas, list)
    assert len(reglas) == 130
    # Verificar estructura mínima de cada regla
    for r in reglas:
        assert "patron" in r
        assert "tipo" in r
        assert "campos" in r


# --- Match contains ---

def test_match_eroski_case_insensitive(gestor):
    """'compra eroski vitoria' debe hacer match con el patrón 'eroski'."""
    resultado = gestor.buscar_match("compra eroski vitoria")
    assert resultado is not None
    assert resultado["categoria1"] == "Alimentación"
    assert resultado["categoria2"] == "Compra"
    assert resultado["proveedor"] == "Eroski"

def test_match_eroski_mayusculas(gestor):
    """El matching debe ser case-insensitive."""
    resultado = gestor.buscar_match("COMPRA EN EROSKI CENTER")
    assert resultado is not None
    assert resultado["categoria1"] == "Alimentación"

def test_match_netflix_contains(gestor):
    """'pago netflix.com mensual' debe hacer match con 'netflix.com'."""
    resultado = gestor.buscar_match("pago netflix.com mensual")
    assert resultado is not None
    assert resultado["categoria1"] == "Gastos Personales"
    assert resultado["categoria2"] == "Subscripciones y Apps"
    assert resultado["proveedor"] == "Netflix"

def test_match_dreamfit(gestor):
    """'RECIBO DREAMFIT VITORIA' debe hacer match con 'dreamfit vitoria'."""
    resultado = gestor.buscar_match("RECIBO DREAMFIT VITORIA")
    assert resultado is not None
    assert resultado["categoria1"] == "Salud"
    assert resultado["categoria2"] == "Gym"


# --- Match startswith ---

def test_match_startswith(tmp_path):
    """Una regla startswith con patrón 'ziv' debe hacer match solo si el concepto empieza por 'ziv'."""
    ruta = tmp_path / "reglas.json"
    gestor = GestorReglas(ruta)
    gestor.importar_reemplazar(REGLAS_INICIALES)
    gestor.añadir(
        patron="ziv",
        tipo="startswith",
        campos={"categoria1": "Trabajo", "categoria2": "Software", "categoria3": "",
                "entidad": "", "proveedor": "ZIV", "tipo_gasto": "Fijos"},
    )
    # Debe hacer match: empieza por "ziv"
    assert gestor.buscar_match("ZIV APLICACIONES SL") is not None
    # No debe hacer match: "ziv" no está al principio
    assert gestor.buscar_match("PAGO ZIV MENSUAL") is None


# --- Match contains_all ---

def test_match_contains_all_todas_las_palabras(tmp_path):
    """contains_all hace match solo si todas las palabras del patrón están en el concepto."""
    ruta = tmp_path / "reglas.json"
    gestor = GestorReglas(ruta)
    gestor.añadir(
        patron="gas natural",
        tipo="contains_all",
        campos={"categoria1": "Vivienda", "categoria2": "Energia", "categoria3": "Gas natural",
                "entidad": "", "proveedor": "", "tipo_gasto": "Optimizable"},
    )
    # Ambas palabras presentes → match
    assert gestor.buscar_match("ENDESA GAS NATURAL VITORIA") is not None
    # Orden inverso → también match
    assert gestor.buscar_match("NATURAL GAS FACTURA") is not None
    # Solo una palabra → no match
    assert gestor.buscar_match("PAGO GAS CIUDAD") is None
    # Ninguna → no match
    assert gestor.buscar_match("RECIBO LUZ ENERO") is None

def test_match_contains_all_no_aplica_a_gastos(tmp_path):
    """'gas natural' no debe coincidir con 'GASTOS NATURALES' (límite de palabra)."""
    ruta = tmp_path / "reglas.json"
    gestor = GestorReglas(ruta)
    gestor.añadir(
        patron="gas natural",
        tipo="contains_all",
        campos={"categoria1": "Vivienda", "categoria2": "Energia", "categoria3": "",
                "entidad": "", "proveedor": "", "tipo_gasto": "Optimizable"},
    )
    # "gastos" no es la palabra "gas" → no match
    assert gestor.buscar_match("GASTOS NATURALES") is None
    # "gas" exacto sí activa
    assert gestor.buscar_match("PAGO GAS NATURAL") is not None


def test_match_contains_word_boundary(tmp_path):
    """contains con patrón 'gas' no debe activarse con 'GASTOS'."""
    ruta = tmp_path / "reglas.json"
    ruta.write_text('{"reglas": []}', encoding="utf-8")
    gestor = GestorReglas(ruta)
    gestor.añadir(
        patron="gas",
        tipo="contains",
        campos={"categoria1": "Vivienda", "categoria2": "Energia", "categoria3": "",
                "entidad": "", "proveedor": "", "tipo_gasto": "Optimizable"},
    )
    assert gestor.buscar_match("GASTOS PISO") is None
    assert gestor.buscar_match("ONA LOW COST GAMARRA VITORIA-GASTE") is None
    assert gestor.buscar_match("PAGO GAS NATURAL") is not None


# --- Sin match ---

def test_sin_match_concepto_desconocido(gestor):
    resultado = gestor.buscar_match("concepto inventado xyz 12345")
    assert resultado is None


# --- Prioridad ---

def test_prioridad_primera_regla_gana(tmp_path):
    """Si dos reglas hacen match, gana la primera de la lista."""
    ruta = tmp_path / "reglas.json"
    datos = {
        "reglas": [
            {"patron": "test", "tipo": "contains",
             "campos": {"categoria1": "Primero", "categoria2": "", "categoria3": "",
                        "entidad": "", "proveedor": "", "tipo_gasto": ""}},
            {"patron": "test pago", "tipo": "contains",
             "campos": {"categoria1": "Segundo", "categoria2": "", "categoria3": "",
                        "entidad": "", "proveedor": "", "tipo_gasto": ""}},
        ]
    }
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    gestor = GestorReglas(ruta)
    resultado = gestor.buscar_match("test pago mensual")
    assert resultado["categoria1"] == "Primero"


# --- Añadir y eliminar ---

def test_añadir_regla(gestor):
    total_antes = gestor.total()
    gestor.añadir(
        patron="nueva tienda",
        tipo="contains",
        campos={"categoria1": "Alimentación", "categoria2": "Compra", "categoria3": "",
                "entidad": "", "proveedor": "Nueva Tienda", "tipo_gasto": "Optimizable"},
    )
    assert gestor.total() == total_antes + 1
    assert gestor.buscar_match("pago nueva tienda online") is not None

def test_añadir_tipo_invalido(gestor):
    with pytest.raises(ValueError, match="Tipo de regla inválido"):
        gestor.añadir("x", "exactmatch", {"categoria1": "", "categoria2": "", "categoria3": "",
                                           "entidad": "", "proveedor": "", "tipo_gasto": ""})

def test_eliminar_regla(gestor):
    total_antes = gestor.total()
    eliminadas = gestor.eliminar("eroski")
    assert eliminadas == 1
    assert gestor.total() == total_antes - 1
    assert gestor.buscar_match("compra eroski vitoria") is None

def test_eliminar_patron_inexistente(gestor):
    eliminadas = gestor.eliminar("patron_que_no_existe")
    assert eliminadas == 0

def test_añadir_persiste_en_disco(tmp_path):
    """La regla añadida debe persistir al recargar el gestor."""
    ruta = tmp_path / "reglas.json"
    shutil.copy2(REGLAS_INICIALES, ruta)
    gestor1 = GestorReglas(ruta)
    gestor1.añadir("tienda nueva", "contains",
                   {"categoria1": "Ocio", "categoria2": "Salidas", "categoria3": "",
                    "entidad": "", "proveedor": "", "tipo_gasto": "Discrecionales"})

    gestor2 = GestorReglas(ruta)
    assert gestor2.buscar_match("pago tienda nueva") is not None


# --- Exportar / importar ---

def test_exportar_e_importar_fusionar(gestor, tmp_path):
    export_path = tmp_path / "export.json"
    gestor.exportar(export_path)

    ruta2 = tmp_path / "reglas2.json"
    datos_vacios = {"reglas": []}
    ruta2.write_text(json.dumps(datos_vacios), encoding="utf-8")
    gestor2 = GestorReglas(ruta2)

    añadidas = gestor2.importar_fusionar(export_path)
    assert añadidas == 130
    assert gestor2.total() == 130

def test_importar_fusionar_no_duplica(gestor, tmp_path):
    export_path = tmp_path / "export.json"
    gestor.exportar(export_path)
    # Importar sobre sí mismo: no debe añadir nada
    añadidas = gestor.importar_fusionar(export_path)
    assert añadidas == 0
    assert gestor.total() == 130

def test_resetear(tmp_path):
    ruta = tmp_path / "reglas.json"
    datos_custom = {"reglas": [{"patron": "solo-esta", "tipo": "contains",
                                 "campos": {"categoria1": "", "categoria2": "", "categoria3": "",
                                            "entidad": "", "proveedor": "", "tipo_gasto": ""}}]}
    ruta.write_text(json.dumps(datos_custom), encoding="utf-8")
    gestor = GestorReglas(ruta)
    assert gestor.total() == 1

    total = gestor.resetear()
    assert total == 130
    assert gestor.total() == 130
