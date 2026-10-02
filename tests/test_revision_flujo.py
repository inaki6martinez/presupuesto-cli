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


def test_exportacion_y_origen(tmp_path):
    import csv
    from presupuesto.cli import _exportar_csv
    from presupuesto.agrupador import agrupar_movimientos

    origen = [{"fecha": "2026-09-10", "cuenta": "Cuenta", "concepto": "Compra"}]
    original = movimiento(importe=Decimal("-30"), originales=origen, fuente="manual")
    agrupado = agrupar_movimientos([original])[0]
    assert agrupado.originales == origen and agrupado.fuente == "manual"
    partes = [replace(agrupado, importe=Decimal("-10"), categoria1="Salud"),
              replace(agrupado, importe=Decimal("-20"))]
    ruta = tmp_path / "exportado.csv"
    _exportar_csv(partes, str(ruta))
    with ruta.open(encoding="utf-8-sig") as f:
        filas = list(csv.DictReader(f, delimiter=";"))
    assert sum(Decimal(r["importe"]) for r in filas) == -30
    assert filas[0]["categoria1"] == "Salud"


def test_volver_a_duplicados_conserva_edicion(tmp_path, monkeypatch):
    from datetime import date
    from importlib import import_module
    from unittest.mock import Mock
    from click.testing import CliRunner
    from presupuesto.parsers.base import MovimientoCrudo
    from presupuesto.duplicados import GestorMarcadores, GestorRevisiones
    from presupuesto.tui_revision import TUIRevisionFinal, TUIRevisionDuplicados

    cli = import_module("presupuesto.cli")
    ruta = tmp_path / "datos.xlsx"
    libro(ruta)
    crudos = [MovimientoCrudo(date(2026, 9, 30), "Duplicado", Decimal("-50"), "Duplicado"),
              MovimientoCrudo(date(2026, 9, 10), "Nuevo", Decimal("-5"), "Nuevo")]
    parser = Mock()
    parser.parsear.return_value = crudos
    categorizador = Mock()
    categorizador.categorizar.side_effect = lambda m, c: movimiento(
        importe=m.importe, confianza="alta", requiere_confirmacion=False, concepto_original=m.concepto,
        categoria2="Salidas" if m.concepto == "Nuevo" else "Compra",
        originales=[{"fecha": m.fecha.isoformat(), "cuenta": c, "concepto": m.concepto}])
    visitas, escritos = [], []

    def revisar(self):
        visitas.append(self._movs[0].categoria1)
        if len(visitas) == 1:
            self._movs[0] = replace(self._movs[0], categoria1="Salud")
            return "volver"
        return True

    escritor = Mock()
    escritor.escribir.side_effect = lambda ms: escritos.extend(ms) or len(ms)
    monkeypatch.setattr(cli, "_obtener_ruta_xlsx", lambda: ruta)
    monkeypatch.setattr(cli, "_crear_gestor_reglas", Mock)
    monkeypatch.setattr(cli, "_obtener_parser_y_banco", lambda *args: (parser, "n26"))
    monkeypatch.setattr("presupuesto.config.cargar_config", lambda: {"cuentas_defecto": {"n26": "Cuenta"}})
    monkeypatch.setattr("presupuesto.categorizar.Categorizador", lambda *args: categorizador)
    marcadores = GestorMarcadores(tmp_path / "marcadores.json")
    monkeypatch.setattr("presupuesto.duplicados.GestorMarcadores", lambda: marcadores)
    monkeypatch.setattr("presupuesto.duplicados.GestorRevisiones", lambda: GestorRevisiones(tmp_path / "revisiones.json"))
    monkeypatch.setattr("presupuesto.escritor.EscritorDatos", lambda *args: escritor)
    monkeypatch.setattr(TUIRevisionDuplicados, "run", lambda self: {0})
    monkeypatch.setattr(TUIRevisionFinal, "run", revisar)
    recovery = tmp_path / "recovery.json"
    recovery.write_text('{"otra_importacion": true}')
    monkeypatch.setattr(cli, "_RUTA_RECOVERY", recovery)
    resultado = CliRunner().invoke(cli.cmd_importar, [str(ruta), "--no-interactivo"])
    assert resultado.exit_code == 0, resultado.exception
    assert visitas == ["Ocio", "Salud"]
    assert escritos[0].categoria1 == "Salud"
    assert marcadores.obtener_marcador("Cuenta") == date(2026, 9, 10)
    assert recovery.exists()


def test_recuperar_metadatos_sin_repetir_filas(tmp_path, monkeypatch):
    import json
    from datetime import date
    from importlib import import_module
    from click.testing import CliRunner
    from presupuesto.duplicados import GestorMarcadores, GestorRevisiones

    cli = import_module("presupuesto.cli")
    ruta = tmp_path / "datos.xlsx"
    libro(ruta)
    recovery, pendientes = tmp_path / "recovery.json", tmp_path / "pendientes.json"
    monkeypatch.setattr(cli, "_RUTA_RECOVERY", recovery)
    monkeypatch.setattr(cli, "_RUTA_PENDIENTES", pendientes)
    marcador = GestorMarcadores(tmp_path / "marcadores.json")
    revision = GestorRevisiones(tmp_path / "revisiones.json")
    monkeypatch.setattr("presupuesto.duplicados.GestorMarcadores", lambda: marcador)
    monkeypatch.setattr("presupuesto.duplicados.GestorRevisiones", lambda: revision)
    original = movimiento(originales=[{"fecha": "2026-09-10", "cuenta": "Cuenta", "concepto": "Compra"}])
    finalizar = cli._finalizar_importacion
    monkeypatch.setattr(cli, "_finalizar_importacion", lambda *args: (_ for _ in ()).throw(OSError("Fallo JSON")))
    assert not cli._escribir_importacion([original], ruta, [{"concepto": "Pendiente"}])
    assert json.loads(recovery.read_text())["escrito"]
    monkeypatch.setattr(cli, "_finalizar_importacion", finalizar)
    resultado = CliRunner().invoke(cli.cmd_recuperar, input="s\n")
    assert resultado.exit_code == 0, resultado.exception
    assert not recovery.exists()
    assert marcador.obtener_marcador("Cuenta") == date(2026, 9, 10)
    assert revision.obtener_revision("Cuenta") == date.today()
    assert json.loads(pendientes.read_text()) == [{"concepto": "Pendiente"}]
    wb = openpyxl.load_workbook(ruta)
    assert wb["Datos"].max_row == 3
    wb.close()


def test_fallo_guardado_conserva_original_y_copia_local(tmp_path, monkeypatch):
    import pytest
    from presupuesto.escritor import guardar_libro
    from presupuesto.cmd_vista import _guardar_sesion

    ruta, local = tmp_path / "datos.xlsx", tmp_path / "local.xlsx"
    libro(ruta)
    anterior = ruta.read_bytes()
    wb = openpyxl.load_workbook(ruta)
    wb["Datos"].cell(2, 7, -99)
    guardar = wb.save

    def fallo(archivo):
        Path = type(ruta)
        Path(archivo).write_bytes(b"incompleto")
        raise OSError("Disco lleno")

    monkeypatch.setattr(wb, "save", fallo)
    with pytest.raises(OSError):
        guardar_libro(wb, ruta)
    assert ruta.read_bytes() == anterior
    monkeypatch.setattr(wb, "save", guardar)
    guardar_atomico = guardar_libro

    def fallo_origen(libro_, destino):
        if destino == ruta:
            raise PermissionError("Archivo abierto")
        guardar_atomico(libro_, destino)

    monkeypatch.setattr("presupuesto.escritor.guardar_libro", fallo_origen)
    with pytest.raises(PermissionError):
        _guardar_sesion(wb, local, ruta)
    assert ruta.read_bytes() == anterior
    copia = openpyxl.load_workbook(local)
    assert copia["Datos"].cell(2, 7).value == -99
    copia.close()
    wb.close()
