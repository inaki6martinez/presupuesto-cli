"""Regresiones del flujo de revisión, con libros pequeños y temporales."""
from dataclasses import replace
from decimal import Decimal

import openpyxl
from rich.console import Console

from presupuesto.categorizar import MovimientoCategorizado
from presupuesto.escritor import leer_numero, eliminar_filas


def movimiento(**cambios):
    base = MovimientoCategorizado(2026, "Sep", "Ocio", "Compra", "", "",
                                 Decimal("-50"), "", "Fijos", "Cuenta", "Banco", "Activo")
    return replace(base, **cambios)


def libro(ruta):
    wb = openpyxl.Workbook()
    wb.active.title = "Datos"
    wb.active.append(["Cabecera"] * 13)
    wb.create_sheet("Maestro").append(["Cabecera"] * 11)
    wb.create_sheet("Claves").append(["Cuenta", "Banco", "Tipo"])
    wb["Claves"].append(["Cuenta", "Banco", "Activo"])
    wb["Datos"].append([2026, "Sep", "Ocio", "Compra", "", "", "=-50", "", "Fijos",
                        "Cuenta", '=VLOOKUP(J2,Claves!$A:$C,2,0)',
                        '=VLOOKUP(J2,Claves!$A:$C,3,0)', "Real"])
    wb.save(ruta)
    wb.close()


def test_formulas_lectura_cierre_y_borrado(tmp_path):
    from io import StringIO
    from presupuesto.duplicados import detectar_duplicados
    from presupuesto.cmd_actualizar import leer_balances
    from presupuesto.cmd_cerrar import _analizar, _plan, _ejecutar
    from presupuesto.cmd_vista import _cmd_vista_mes, _leer_datos

    ruta = tmp_path / "datos.xlsx"
    libro(ruta)
    assert detectar_duplicados([movimiento()], ruta)[0][1] == 2
    assert leer_balances(ruta)["Cuenta"] == Decimal("-50")
    salida = StringIO()
    _cmd_vista_mes(Console(file=salida, width=120), ruta, "Sep", 2026)
    assert "-50" in salida.getvalue()
    datos = _analizar(ruta)
    _ejecutar(ruta, 2026, _plan(datos, 2026, 10))
    wb = openpyxl.load_workbook(ruta)
    assert leer_numero(wb["Datos"].cell(3, 7).value) == -50
    eliminar_filas(wb["Datos"], [2])
    assert "J2," in wb["Datos"].cell(2, 11).value
    wb["Datos"].cell(2, 3, "Finanzas")
    wb["Datos"].cell(2, 4, "Balance")
    wb.save(ruta)
    wb.close()
    entradas, *_ = _leer_datos(ruta, [(2027, "Sep")], incluir_balance=True)
    assert any(f.cat2 == "Balance" for f in entradas)
