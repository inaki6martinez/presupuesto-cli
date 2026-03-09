"""Tests de GestorMarcadores y detección de duplicados."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import openpyxl
import pytest

from presupuesto.categorizar import MovimientoCategorizado
from presupuesto.duplicados import GestorMarcadores, detectar_duplicados
from presupuesto.parsers.base import MovimientoCrudo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mov_crudo(fecha: date, concepto: str = "test") -> MovimientoCrudo:
    return MovimientoCrudo(
        fecha=fecha,
        concepto=concepto,
        importe=Decimal("-10.00"),
        concepto_original=f"{fecha} | {concepto}",
    )


def _mov_cat(**kwargs) -> MovimientoCategorizado:
    defaults = dict(
        año=2026, mes="Mar",
        categoria1="Alimentación", categoria2="Supermercados", categoria3="",
        entidad="", importe=Decimal("-25.00"), proveedor="Eroski",
        tipo_gasto="Discrecionales", cuenta="Cuenta Nomina",
        banco="Openbank", tipo_cuenta="Activos liquidos", estado="Real",
    )
    defaults.update(kwargs)
    return MovimientoCategorizado(**defaults)


def _xlsx_con_datos(ruta: Path, filas: list[tuple]) -> None:
    """Crea un xlsx mínimo con filas de datos en la hoja 'Datos'."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Datos"
    ws.append(["Año", "Mes", "Categoría 1", "Categoría 2", "Categoría 3",
               "Entidad", "Importe", "Proveedor", "Tipo de Gasto",
               "Cuentas", "Banco", "Tipo de cuenta", "Estado"])
    for fila in filas:
        ws.append(list(fila))
    wb.save(str(ruta))


# ---------------------------------------------------------------------------
# GestorMarcadores — obtener / actualizar
# ---------------------------------------------------------------------------

def test_marcador_inicialmente_none(tmp_path):
    g = GestorMarcadores(tmp_path / "marcadores.json")
    assert g.obtener_marcador("Cuenta Nomina") is None


def test_actualizar_marcador_persiste(tmp_path):
    ruta = tmp_path / "marcadores.json"
    g = GestorMarcadores(ruta)
    g.actualizar_marcador("Cuenta Nomina", date(2026, 3, 15))

    g2 = GestorMarcadores(ruta)
    assert g2.obtener_marcador("Cuenta Nomina") == date(2026, 3, 15)


def test_actualizar_marcador_solo_avanza(tmp_path):
    """El marcador no retrocede si se intenta actualizar con fecha anterior."""
    g = GestorMarcadores(tmp_path / "marcadores.json")
    g.actualizar_marcador("Cuenta Nomina", date(2026, 3, 15))
    g.actualizar_marcador("Cuenta Nomina", date(2026, 2, 1))
    assert g.obtener_marcador("Cuenta Nomina") == date(2026, 3, 15)


def test_cuentas_independientes(tmp_path):
    g = GestorMarcadores(tmp_path / "marcadores.json")
    g.actualizar_marcador("Cuenta Nomina", date(2026, 3, 15))
    g.actualizar_marcador("Cuenta Ocio",   date(2026, 1, 10))
    assert g.obtener_marcador("Cuenta Nomina") == date(2026, 3, 15)
    assert g.obtener_marcador("Cuenta Ocio")   == date(2026, 1, 10)
    assert g.obtener_marcador("Kutxabank")     is None


# ---------------------------------------------------------------------------
# GestorMarcadores — filtrar_movimientos
# ---------------------------------------------------------------------------

def test_sin_marcador_pasan_todos(tmp_path):
    g = GestorMarcadores(tmp_path / "marcadores.json")
    movs = [_mov_crudo(date(2026, 1, i)) for i in range(1, 6)]
    aceptados, descartados = g.filtrar_movimientos(movs, "Cuenta Nomina")
    assert len(aceptados) == 5
    assert descartados == 0


def test_marcador_filtra_anteriores_e_iguales(tmp_path):
    g = GestorMarcadores(tmp_path / "marcadores.json")
    g.actualizar_marcador("Cuenta Nomina", date(2026, 3, 15))

    movs = [
        _mov_crudo(date(2026, 3, 10)),  # antes del marcador → descartado
        _mov_crudo(date(2026, 3, 15)),  # igual al marcador → descartado
        _mov_crudo(date(2026, 3, 16)),  # posterior → aceptado
        _mov_crudo(date(2026, 3, 20)),  # posterior → aceptado
    ]
    aceptados, descartados = g.filtrar_movimientos(movs, "Cuenta Nomina")
    assert len(aceptados) == 2
    assert descartados == 2
    assert all(m.fecha > date(2026, 3, 15) for m in aceptados)


def test_desde_ignora_marcador(tmp_path):
    g = GestorMarcadores(tmp_path / "marcadores.json")
    g.actualizar_marcador("Cuenta Nomina", date(2026, 3, 15))

    movs = [
        _mov_crudo(date(2026, 3, 5)),
        _mov_crudo(date(2026, 3, 20)),
    ]
    # Con desde=2026-03-01, el marcador (15/03) se ignora y se usa la fecha dada
    aceptados, descartados = g.filtrar_movimientos(
        movs, "Cuenta Nomina", desde=date(2026, 3, 1)
    )
    assert len(aceptados) == 2
    assert descartados == 0


def test_desde_mas_reciente_que_marcador(tmp_path):
    """'desde' más reciente que el marcador filtra más estrictamente."""
    g = GestorMarcadores(tmp_path / "marcadores.json")
    g.actualizar_marcador("Cuenta Nomina", date(2026, 3, 1))

    movs = [
        _mov_crudo(date(2026, 3, 5)),   # posterior al marcador pero no a 'desde'
        _mov_crudo(date(2026, 3, 20)),  # posterior a 'desde' → aceptado
    ]
    aceptados, descartados = g.filtrar_movimientos(
        movs, "Cuenta Nomina", desde=date(2026, 3, 10)
    )
    assert len(aceptados) == 1
    assert aceptados[0].fecha == date(2026, 3, 20)


# ---------------------------------------------------------------------------
# detectar_duplicados
# ---------------------------------------------------------------------------

def test_sin_xlsx_devuelve_vacio(tmp_path):
    movs = [_mov_cat()]
    resultado = detectar_duplicados(movs, tmp_path / "no_existe.xlsx")
    assert resultado == []


def test_detecta_duplicado_exacto(tmp_path):
    ruta = tmp_path / "pres.xlsx"
    _xlsx_con_datos(ruta, [
        (2026, "Mar", "Alimentación", "Supermercados", "", "", -25.00,
         "Eroski", "Discrecionales", "Cuenta Nomina", "Openbank", "Activos liquidos", "Real"),
    ])
    movs = [_mov_cat(importe=Decimal("-25.00"))]
    duplicados = detectar_duplicados(movs, ruta)
    assert len(duplicados) == 1
    assert duplicados[0][0] is movs[0]
    assert duplicados[0][1] == 2  # fila 2 del xlsx


def test_sin_coincidencia_devuelve_vacio(tmp_path):
    ruta = tmp_path / "pres.xlsx"
    _xlsx_con_datos(ruta, [
        (2026, "Mar", "Ocio", "Entretenimiento", "", "", -50.00,
         "Netflix", "Discrecionales", "Cuenta Ocio", "N26", "Activos liquidos", "Real"),
    ])
    movs = [_mov_cat()]  # Alimentación / Cuenta Nomina → no coincide
    assert detectar_duplicados(movs, ruta) == []


def test_tolerancia_importe_001(tmp_path):
    """Diferencia de 0.01 en importe se considera duplicado."""
    ruta = tmp_path / "pres.xlsx"
    _xlsx_con_datos(ruta, [
        (2026, "Mar", "Alimentación", "Supermercados", "", "", -25.01,
         "Eroski", "Discrecionales", "Cuenta Nomina", "Openbank", "Activos liquidos", "Real"),
    ])
    movs = [_mov_cat(importe=Decimal("-25.00"))]
    duplicados = detectar_duplicados(movs, ruta)
    assert len(duplicados) == 1


def test_fuera_de_tolerancia_no_es_duplicado(tmp_path):
    """Diferencia de 0.02 en importe NO se considera duplicado."""
    ruta = tmp_path / "pres.xlsx"
    _xlsx_con_datos(ruta, [
        (2026, "Mar", "Alimentación", "Supermercados", "", "", -25.02,
         "Eroski", "Discrecionales", "Cuenta Nomina", "Openbank", "Activos liquidos", "Real"),
    ])
    movs = [_mov_cat(importe=Decimal("-25.00"))]
    assert detectar_duplicados(movs, ruta) == []


def test_distinto_mes_no_es_duplicado(tmp_path):
    ruta = tmp_path / "pres.xlsx"
    _xlsx_con_datos(ruta, [
        (2026, "Feb", "Alimentación", "Supermercados", "", "", -25.00,
         "Eroski", "Discrecionales", "Cuenta Nomina", "Openbank", "Activos liquidos", "Real"),
    ])
    movs = [_mov_cat(mes="Mar")]
    assert detectar_duplicados(movs, ruta) == []


def test_distinta_cuenta_no_es_duplicado(tmp_path):
    ruta = tmp_path / "pres.xlsx"
    _xlsx_con_datos(ruta, [
        (2026, "Mar", "Alimentación", "Supermercados", "", "", -25.00,
         "Eroski", "Discrecionales", "Cuenta Ocio", "N26", "Activos liquidos", "Real"),
    ])
    movs = [_mov_cat(cuenta="Cuenta Nomina")]
    assert detectar_duplicados(movs, ruta) == []


def test_multiples_movimientos_detecta_solo_los_duplicados(tmp_path):
    ruta = tmp_path / "pres.xlsx"
    _xlsx_con_datos(ruta, [
        (2026, "Mar", "Alimentación", "Supermercados", "", "", -25.00,
         "Eroski", "Discrecionales", "Cuenta Nomina", "Openbank", "Activos liquidos", "Real"),
    ])
    movs = [
        _mov_cat(importe=Decimal("-25.00")),    # duplicado
        _mov_cat(categoria1="Ocio", importe=Decimal("-15.00")),  # no duplicado
    ]
    duplicados = detectar_duplicados(movs, ruta)
    assert len(duplicados) == 1
    assert duplicados[0][0].categoria1 == "Alimentación"


def test_filas_presupuesto_no_se_consideran_duplicados(tmp_path):
    """Filas con Estado='Presupuesto' no deben considerarse duplicados."""
    ruta = tmp_path / "pres.xlsx"
    _xlsx_con_datos(ruta, [
        (2026, "Mar", "Alimentación", "Supermercados", "", "", -25.00,
         "Eroski", "Discrecionales", "Cuenta Nomina", "Openbank", "Activos liquidos", "Presupuesto"),
    ])
    movs = [_mov_cat(importe=Decimal("-25.00"))]
    assert detectar_duplicados(movs, ruta) == []


def test_filas_real_si_se_consideran_duplicados(tmp_path):
    """Filas con Estado='Real' sí deben considerarse duplicados."""
    ruta = tmp_path / "pres.xlsx"
    _xlsx_con_datos(ruta, [
        (2026, "Mar", "Alimentación", "Supermercados", "", "", -25.00,
         "Eroski", "Discrecionales", "Cuenta Nomina", "Openbank", "Activos liquidos", "Real"),
    ])
    movs = [_mov_cat(importe=Decimal("-25.00"))]
    assert len(detectar_duplicados(movs, ruta)) == 1
