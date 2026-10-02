"""UI interactiva en terminal para categorización de movimientos.

Funciones públicas:
    mostrar_movimiento          — panel con datos del movimiento y sugerencia.
    pedir_categorizacion        — flujo campo a campo con búsqueda por texto.
    preguntar_guardar_regla     — ofrece guardar la categorización como regla.
    mostrar_resumen             — tabla resumen antes de escribir.
    pedir_registrar_revision    — fecha de revisión compartida.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import click
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from presupuesto.categorizar import MovimientoCategorizado
    from presupuesto.maestro import DatosMaestros
    from presupuesto.parsers.base import MovimientoCrudo

consola = Console()

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_CONFIANZA_ESTILO: dict[str, tuple[str, str]] = {
    "alta":    ("green",  "✓"),
    "media":   ("yellow", "~"),
    "baja":    ("red",    "?"),
    "ninguna": ("dim",    "·"),
}

_PALABRAS_COMUNES = {
    "de", "en", "la", "el", "los", "las", "del", "al", "y", "a",
    "por", "para", "con", "se", "un", "una", "lo", "es", "que",
    "no", "si", "mas", "su", "sus", "mi", "me", "te", "le", "pago",
}

def _formato_importe(importe: Decimal) -> Text:
    texto = f"{importe:+.2f} €"
    return Text(texto, style="red" if importe < 0 else "green")


def _sugerir_patron(concepto: str) -> str:
    """Devuelve la palabra más significativa del concepto como patrón sugerido."""
    palabras = concepto.split()
    candidatas = [
        p.lower() for p in palabras
        if p.lower() not in _PALABRAS_COMUNES and len(p) >= 4 and p.isalpha()
    ]
    if not candidatas:
        return (concepto[:20] if len(concepto) > 20 else concepto).lower()
    return max(candidatas, key=len)


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def mostrar_movimiento(
    movimiento: MovimientoCrudo,
    sugerencia: MovimientoCategorizado | None,
) -> None:
    """Muestra un panel con los datos del movimiento y la sugerencia (si existe)."""
    # Panel del movimiento
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="dim", no_wrap=True)
    grid.add_column()
    grid.add_row("Fecha",    str(movimiento.fecha))
    grid.add_row("Concepto", movimiento.concepto)
    grid.add_row("Importe",  _formato_importe(movimiento.importe))

    concepto_original = movimiento.concepto_original
    if concepto_original and concepto_original != movimiento.concepto:
        trunc = concepto_original[:70] + "…" if len(concepto_original) > 70 else concepto_original
        grid.add_row("Original", Text(trunc, style="dim"))

    consola.print(Panel(grid, title="Movimiento", border_style="blue", padding=(0, 1)))

    # Panel de sugerencia
    if sugerencia:
        color, icono = _CONFIANZA_ESTILO.get(sugerencia.confianza, ("dim", "·"))

        sugg = Table.grid(padding=(0, 2))
        sugg.add_column(style="dim", no_wrap=True)
        sugg.add_column()
        if sugerencia.categoria1:
            sugg.add_row("Categoría 1", sugerencia.categoria1)
        if sugerencia.categoria2:
            sugg.add_row("Categoría 2", sugerencia.categoria2)
        if sugerencia.categoria3:
            sugg.add_row("Categoría 3", sugerencia.categoria3)
        if sugerencia.entidad:
            sugg.add_row("Entidad",     sugerencia.entidad)
        if sugerencia.proveedor:
            sugg.add_row("Proveedor",   sugerencia.proveedor)
        if sugerencia.tipo_gasto:
            sugg.add_row("Tipo gasto",  sugerencia.tipo_gasto)

        titulo_sugg = f"Sugerencia  [{color}]{icono} confianza {sugerencia.confianza}[/{color}]"
        consola.print(Panel(sugg, title=titulo_sugg, border_style=color, padding=(0, 1)))


def pedir_categorizacion(
    datos_maestros: DatosMaestros,
    sugerencia: MovimientoCategorizado | None,
) -> dict | str:
    """Abre el TUI multi-columna para categorizar el movimiento.

    Returns:
        dict     — campos completados (categoria1..tipo_gasto).
        "saltar" — el usuario quiere saltar este movimiento.
        "volver" — el usuario quiere volver al movimiento anterior.
        "salir"  — el usuario quiere guardar progreso y salir.
    """
    from presupuesto.tui_categorizar import TUICategorizacion

    if sugerencia is None:
        # Crear una sugerencia vacía para que el TUI tenga los campos base
        from presupuesto.categorizar import MovimientoCategorizado
        from decimal import Decimal
        sugerencia = MovimientoCategorizado(
            año=0, mes="", categoria1="", categoria2="", categoria3="",
            entidad="", importe=Decimal("0"), proveedor="", tipo_gasto="",
            cuenta="", banco=None, tipo_cuenta=None,
        )

    tui = TUICategorizacion(sugerencia, datos_maestros)
    resultado = tui.run()

    if resultado is None:
        return "salir"
    return resultado


def preguntar_guardar_regla(concepto: str, campos: dict, cuenta: str = "") -> dict | None:
    """Pregunta al usuario si guardar la categorización como regla nueva.

    Returns:
        dict — {patron, tipo, campos, cuenta} listo para GestorReglas.añadir().
        None — el usuario no quiere guardar.
    """
    if not click.confirm("\n  ¿Guardar como regla de categorización?", default=False):
        return None

    patron_sugerido = _sugerir_patron(concepto)
    consola.print(
        f"\n  Sugerencia: [cyan]{patron_sugerido}[/cyan]  "
        "[dim](palabra más significativa del concepto)[/dim]"
    )
    patron = click.prompt("  Patrón", default=patron_sugerido)
    tipo = click.prompt(
        "  Tipo de match",
        type=click.Choice(["contains", "contains_all", "startswith", "regex"]),
        default="contains",
        show_choices=True,
    )
    cuenta_regla = ""
    if cuenta:
        consola.print(
            f"\n  [dim]La regla se aplicará a [bold]todas las cuentas[/bold] (Enter = todas).[/dim]"
        )
        if click.confirm(f"  ¿Limitar solo a [{cuenta}]?", default=False):
            cuenta_regla = cuenta
    return {"patron": patron, "tipo": tipo, "campos": campos, "cuenta": cuenta_regla}


def mostrar_resumen(movimientos: list[MovimientoCategorizado]) -> None:
    """Muestra una tabla resumen de todos los movimientos procesados."""
    if not movimientos:
        consola.print("[yellow]No hay movimientos para mostrar.[/yellow]")
        return

    tabla = Table(
        title=f"Resumen — {len(movimientos)} movimiento(s)",
        show_lines=False,
        box=box.SIMPLE_HEAD,
    )
    tabla.add_column("Mes",        style="dim",  no_wrap=True)
    tabla.add_column("Concepto",                 no_wrap=True, max_width=35)
    tabla.add_column("Importe",    justify="right", no_wrap=True)
    tabla.add_column("Categoría 1")
    tabla.add_column("Categoría 2")
    tabla.add_column("Categoría 3", style="dim")
    tabla.add_column("Proveedor")
    tabla.add_column("Tipo gasto", style="dim")
    tabla.add_column("",           no_wrap=True)   # confianza (icono)

    for m in movimientos:
        color_imp = "red" if m.importe < 0 else "green"
        imp_str   = f"[{color_imp}]{m.importe:+.2f}[/{color_imp}]"

        color_c, icono = _CONFIANZA_ESTILO.get(m.confianza, ("dim", "·"))
        conf_str = f"[{color_c}]{icono}[/{color_c}]"

        concepto_raw = m.concepto_original or ""
        concepto_corto = concepto_raw[:32] + "…" if len(concepto_raw) > 32 else concepto_raw

        tabla.add_row(
            f"{m.mes} {m.año}",
            concepto_corto,
            imp_str,
            m.categoria1,
            m.categoria2,
            m.categoria3,
            m.proveedor,
            m.tipo_gasto,
            conf_str,
        )

    consola.print()
    consola.print(tabla)
    consola.print(
        "  [dim]Confianza:[/dim]  "
        "[green]✓[/green] regla  "
        "[yellow]~[/yellow] historial  "
        "[red]?[/red] baja  "
        "[dim]·[/dim] sin sugerencia"
    )
    consola.print()


def pedir_registrar_revision(consola, cuenta: str, gestor, hoy: date) -> None:
    """Ofrece al usuario confirmar y/o cambiar la fecha de revisión de la cuenta."""
    from datetime import date
    revision_actual = gestor.obtener_revision(cuenta)

    consola.print()
    if revision_actual:
        consola.print(
            f"  Última revisión de [bold]{cuenta}[/bold]: "
            f"[cyan]{revision_actual.isoformat()}[/cyan]"
        )
    else:
        consola.print(
            f"  [dim]Sin revisión registrada para [bold]{cuenta}[/bold][/dim]"
        )

    if not click.confirm(f"  ¿Registrar revisión de '{cuenta}'?", default=True):
        return

    while True:
        raw = click.prompt(
            "  Fecha de la revisión",
            default=hoy.isoformat(),
        ).strip()
        try:
            fecha = date.fromisoformat(raw)
            break
        except ValueError:
            consola.print("  [red]Formato inválido. Usa YYYY-MM-DD (ej: 2026-03-31)[/red]")

    gestor.registrar_revision(cuenta, fecha)
    consola.print(
        f"  [green]✓ Revisión de '{cuenta}' registrada: {fecha.isoformat()}[/green]"
    )

