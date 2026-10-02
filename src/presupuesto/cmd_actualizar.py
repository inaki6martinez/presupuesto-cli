"""Comando 'actualizar': ajusta el balance de una cuenta con movimientos categorizados.

Flujo:
1. Lee los balances actuales de cada cuenta sumando la hoja 'Datos' (Estado=Real).
2. TUI para seleccionar la cuenta.
3. Prompt para introducir el valor real actual.
4. Permite categorizar o dividir la diferencia antes de escribirla en el xlsx.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    pass

_MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
          "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


# ---------------------------------------------------------------------------
# Lectura de balances desde la hoja Datos
# ---------------------------------------------------------------------------

def leer_balances(ruta_xlsx: str | Path) -> dict[str, Decimal]:
    """Calcula el balance actual de cada cuenta sumando la hoja 'Datos' (Estado=Real).

    Columnas: A=Año(0) B=Mes(1) C=Cat1(2) D=Cat2(3) E=Cat3(4) F=Entidad(5)
              G=Importe(6) H=Proveedor(7) I=TipoGasto(8) J=Cuenta(9)
              K=Banco(10) L=TipoCuenta(11) M=Estado(12)
    """
    import openpyxl

    ruta = Path(ruta_xlsx)
    balances: dict[str, Decimal] = {}

    if not ruta.exists():
        return balances

    from presupuesto.escritor import leer_numero

    wb = openpyxl.load_workbook(str(ruta), read_only=True)
    try:
        ws = wb["Datos"]
    except KeyError:
        wb.close()
        return balances

    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or row[0] is None:
            continue
        estado = str(row[12] or "").strip().lower() if len(row) > 12 else ""
        if estado != "real":
            continue
        cuenta = str(row[9] or "").strip() if len(row) > 9 else ""
        if not cuenta:
            continue
        imp = leer_numero(row[6])
        if imp is None:
            continue
        balances[cuenta] = balances.get(cuenta, Decimal(0)) + Decimal(str(imp))

    wb.close()
    return balances


from presupuesto.maestro import leer_cuentas as leer_cuentas


# ---------------------------------------------------------------------------
# TUI selección de cuenta
# ---------------------------------------------------------------------------

from presupuesto.tui_cuentas import seleccionar_cuenta as _tui_seleccionar_cuenta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

from presupuesto.interactivo import pedir_registrar_revision as _pedir_registrar_revision


# ---------------------------------------------------------------------------
# Comando click
# ---------------------------------------------------------------------------

@click.command("actualizar")
def cmd_actualizar():
    """Ajusta el balance de una cuenta a su valor real actual.

    Abre un selector de cuentas con su balance calculado (suma de entradas
    Real en la hoja Datos). Al introducir el valor real actual, calcula la
    diferencia y permite categorizarla o dividirla antes de escribir en el xlsx.

    Flujo:

    \b
      1. Selecciona la cuenta en la lista (filtrable escribiendo).
      2. Introduce el valor real actual de la cuenta.
      3. Enter para categorizar, d para dividir y categorizar cada parte.
      4. Confirma con c y Enter para escribir los movimientos.
      5. Opcionalmente registra la fecha de revisión en revisiones.json.

    El selector vuelve a la lista tras cada ajuste, permitiendo actualizar
    varias cuentas en una sola sesión. Sal con Esc.
    """
    from rich.console import Console
    from presupuesto.config import cargar_config
    from presupuesto.escritor import EscritorDatos
    from presupuesto.maestro import DatosMaestros
    from presupuesto.tui_revision import TUIRevisionFinal

    consola = Console()

    config = cargar_config()
    ruta_xlsx = config.get("archivo_presupuesto", "")
    if not ruta_xlsx:
        consola.print("[red]No hay ruta al xlsx configurada. Ejecuta 'presupuesto config'.[/red]")
        raise SystemExit(1)
    ruta_xlsx = Path(ruta_xlsx).expanduser()
    if not ruta_xlsx.exists():
        consola.print(f"[red]No se encuentra el archivo:[/red] {ruta_xlsx}")
        raise SystemExit(1)

    # --- Leer datos del xlsx ---
    consola.print("[dim]Leyendo datos del xlsx…[/dim]")
    cuentas  = leer_cuentas(ruta_xlsx)
    balances = leer_balances(ruta_xlsx)

    if not cuentas:
        consola.print("[red]No se encontraron cuentas en la hoja Claves.[/red]")
        raise SystemExit(1)

    datos_maestros = DatosMaestros(ruta_xlsx)
    from presupuesto.categorizar import MovimientoCategorizado
    from presupuesto.duplicados import GestorRevisiones
    gestor_revisiones = GestorRevisiones()

    # --- Bucle: TUI → actualizar → volver a TUI ---
    while True:
        seleccion = _tui_seleccionar_cuenta(cuentas, balances)
        if seleccion is None:
            consola.print("[dim]Saliendo.[/dim]")
            return

        cuenta, banco, tipo_cuenta = seleccion
        balance_actual = balances.get(cuenta, Decimal(0))

        consola.print(f"\n  Cuenta:         [bold]{cuenta}[/bold]")
        consola.print(f"  Balance actual: [cyan]{balance_actual:+.2f}€[/cyan]")

        # Pedir nuevo valor
        while True:
            raw = click.prompt("\n  Nuevo valor real").strip().replace(",", ".")
            try:
                nuevo_valor = Decimal(raw).quantize(Decimal("0.01"))
                if not nuevo_valor.is_finite():
                    raise InvalidOperation
                break
            except InvalidOperation:
                consola.print("  [red]Valor no válido. Usa formato numérico (ej: 1234.56)[/red]")

        diferencia = nuevo_valor - balance_actual

        consola.print(f"\n  Nuevo valor:    [bold]{nuevo_valor:+.2f}€[/bold]")
        color_dif = "green" if diferencia >= 0 else "red"
        consola.print(f"  Diferencia:     [{color_dif}]{diferencia:+.2f}€[/{color_dif}]")

        hoy = date.today()
        mes = _MESES[hoy.month - 1]

        if diferencia == 0:
            consola.print("\n  [yellow]Diferencia 0, no hay nada que ajustar.[/yellow]")
            _pedir_registrar_revision(consola, cuenta, gestor_revisiones, hoy)
            continue

        # Finanzas/Balance como propuesta editable.
        mov = MovimientoCategorizado(
            año=hoy.year,
            mes=mes,
            categoria1="Finanzas",
            categoria2="Balance",
            categoria3="",
            entidad="",
            importe=diferencia,
            proveedor="",
            tipo_gasto="",
            cuenta=cuenta,
            banco=banco or None,
            tipo_cuenta=tipo_cuenta or None,
            estado="Real",
            confianza="alta",
            fuente="actualizar",
            requiere_confirmacion=False,
            concepto_original=f"Ajuste balance {cuenta} → {nuevo_valor:+.2f}€",
        )

        revision = TUIRevisionFinal([mov], datos_maestros, permitir_volver=False)
        resultado = revision.run()
        while resultado == "volver":
            resultado = revision.run()
        if resultado is not True:
            consola.print("  [dim]Cancelado, volviendo a la lista.[/dim]")
            continue
        movimientos = revision._movs
        if sum(m.importe for m in movimientos) != diferencia:
            consola.print("  [red]Las partes no suman la diferencia. No se ha escrito nada.[/red]")
            continue

        try:
            n = EscritorDatos(ruta_xlsx).escribir(movimientos)
            consola.print(f"  [green]✓ {n} entrada(s) escritas.[/green]")
        except Exception as e:
            consola.print(f"  [red]Error al escribir:[/red] {e}")
            continue

        # Registrar revisión (interactivo) y actualizar balance local
        _pedir_registrar_revision(consola, cuenta, gestor_revisiones, hoy)
        balances[cuenta] = nuevo_valor
