"""UI interactiva en terminal para categorización de movimientos.

Funciones públicas:
    mostrar_movimiento          — panel con datos del movimiento y sugerencia.
    pedir_categorizacion        — flujo campo a campo con búsqueda por texto.
    preguntar_guardar_regla     — ofrece guardar la categorización como regla.
    mostrar_resumen             — tabla resumen antes de escribir.
    pedir_confirmacion_escritura — confirmación final.
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

# Campos a completar: (clave_resultado, campo_maestro, etiqueta_display)
_CAMPOS = [
    ("categoria1", "categorias1", "Categoría 1"),
    ("categoria2", "categorias2", "Categoría 2"),
    ("categoria3", "categorias3", "Categoría 3"),
    ("entidad",    "entidades",   "Entidad"),
    ("proveedor",  "proveedores", "Proveedor"),
    ("tipo_gasto", "tipos_gasto", "Tipo de gasto"),
]

_PALABRAS_COMUNES = {
    "de", "en", "la", "el", "los", "las", "del", "al", "y", "a",
    "por", "para", "con", "se", "un", "una", "lo", "es", "que",
    "no", "si", "mas", "su", "sus", "mi", "me", "te", "le", "pago",
}

_MAX_OPCIONES = 15  # máximo de opciones a mostrar antes de pedir filtro

# ---------------------------------------------------------------------------
# Señales internas para propagación desde _seleccionar_valor
# ---------------------------------------------------------------------------

class _Saltar(Exception):
    pass

class _Salir(Exception):
    pass

class _Volver(Exception):
    pass

# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _formato_importe(importe: Decimal) -> Text:
    texto = f"{importe:+.2f} €"
    return Text(texto, style="red" if importe < 0 else "green")


def _campos_de_sugerencia(s: MovimientoCategorizado) -> dict:
    return {
        "categoria1": s.categoria1,
        "categoria2": s.categoria2,
        "categoria3": s.categoria3,
        "entidad":    s.entidad,
        "proveedor":  s.proveedor,
        "tipo_gasto": s.tipo_gasto,
    }


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


def _seleccionar_valor(etiqueta: str, opciones: list[str], sugerencia: str = "") -> str:
    """Picker interactivo con búsqueda por texto.

    El usuario puede:
    - Escribir un número para seleccionar la opción correspondiente.
    - Escribir texto para filtrar las opciones.
    - Pulsar Enter para aceptar la sugerencia (o dejar vacío).
    - Escribir 's' para saltar el movimiento.
    - Escribir 'q' para guardar y salir.

    Lanza _Saltar o _Salir según corresponda.
    """
    filtro = ""

    while True:
        # Calcular opciones filtradas
        filtradas = (
            [o for o in opciones if filtro.lower() in o.lower()]
            if filtro else opciones
        )
        mostradas = filtradas[:_MAX_OPCIONES]

        # Cabecera del campo
        header = Text(f"\n  {etiqueta}", style="bold cyan")
        if sugerencia:
            header.append(f"  [{sugerencia}]", style="dim")
        consola.print(header)

        if not opciones:
            consola.print("    [dim](sin opciones en el Maestro — escribe el valor o Enter para vacío)[/dim]")
        else:
            for i, op in enumerate(mostradas, 1):
                marcado = op == sugerencia
                fila = f"    [dim]{i:2d}.[/dim] "
                fila += f"[bold]{op}[/bold]" if marcado else op
                consola.print(fila)

            if len(filtradas) > _MAX_OPCIONES:
                consola.print(
                    f"    [dim]... {len(filtradas) - _MAX_OPCIONES} más. "
                    "Escribe para filtrar.[/dim]"
                )
            if filtro:
                consola.print(f"    [dim]Filtro: '{filtro}'[/dim]")

        consola.print(
            "    [dim]Nº[/dim] seleccionar · "
            "[dim]texto[/dim] filtrar · "
            "[dim]Enter[/dim] aceptar sugerencia · "
            "[dim]s[/dim] saltar · "
            "[dim]v[/dim] volver · "
            "[dim]q[/dim] salir",
            highlight=False,
        )

        try:
            entrada = consola.input("  > ").strip()
        except (EOFError, KeyboardInterrupt):
            raise _Salir()

        if entrada.lower() == "s":
            raise _Saltar()
        if entrada.lower() == "q":
            raise _Salir()
        if entrada.lower() == "v":
            raise _Volver()

        # Enter vacío → aceptar sugerencia (o cadena vacía)
        if entrada == "":
            return sugerencia

        # Intentar número
        try:
            n = int(entrada)
            if 1 <= n <= len(mostradas):
                return mostradas[n - 1]
            consola.print(f"  [red]Número fuera de rango (1-{len(mostradas)}).[/red]")
            continue
        except ValueError:
            pass

        # Usar como filtro o valor libre
        coincidencias = [o for o in opciones if entrada.lower() in o.lower()]
        if len(coincidencias) == 0:
            # Sin coincidencias en el Maestro → aceptar como valor libre
            return entrada
        elif len(coincidencias) == 1:
            return coincidencias[0]
        else:
            filtro = entrada


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
    """Flujo interactivo para completar la categorización de un movimiento.

    Returns:
        dict     — campos completados (categoria1..tipo_gasto).
        "saltar" — el usuario quiere saltar este movimiento.
        "salir"  — el usuario quiere guardar progreso y salir.
    """
    if sugerencia:
        color, icono = _CONFIANZA_ESTILO.get(sugerencia.confianza, ("dim", "·"))
        consola.print(
            f"\n  [{color}]{icono}[/{color}] Confianza [{color}]{sugerencia.confianza}[/{color}].  "
            "[dim]Enter[/dim] aceptar · "
            "[dim]e[/dim] editar · "
            "[dim]s[/dim] saltar · "
            "[dim]v[/dim] volver · "
            "[dim]q[/dim] salir"
        )
        try:
            resp = consola.input("\n  > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return "salir"

        if resp == "":
            return _campos_de_sugerencia(sugerencia)
        if resp == "s":
            return "saltar"
        if resp == "v":
            return "volver"
        if resp == "q":
            return "salir"
        # 'e' u otro → editar campo a campo con valores de la sugerencia como default
        valores_iniciales = _campos_de_sugerencia(sugerencia)
    else:
        consola.print("\n  [dim]Sin sugerencia. Completa los campos manualmente.[/dim]")
        consola.print("  [dim]s[/dim] saltar · [dim]v[/dim] volver · [dim]q[/dim] salir\n")
        valores_iniciales = {k: "" for k, _, _ in _CAMPOS}

    # Edición campo a campo
    resultado: dict[str, str] = {}
    try:
        for campo_key, campo_maestro, etiqueta in _CAMPOS:
            inicial = valores_iniciales.get(campo_key, "")
            opciones = datos_maestros.valores_validos(campo_maestro)
            resultado[campo_key] = _seleccionar_valor(etiqueta, opciones, inicial)
    except _Saltar:
        return "saltar"
    except _Volver:
        return "volver"
    except _Salir:
        return "salir"

    return resultado


def preguntar_guardar_regla(concepto: str, campos: dict) -> dict | None:
    """Pregunta al usuario si guardar la categorización como regla nueva.

    Returns:
        dict — {patron, tipo, campos} listo para GestorReglas.añadir().
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
        type=click.Choice(["contains", "startswith", "regex"]),
        default="contains",
        show_choices=True,
    )
    return {"patron": patron, "tipo": tipo, "campos": campos}


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


def pedir_confirmacion_escritura(num_movimientos: int) -> bool:
    """Pide confirmación final antes de escribir en el xlsx.

    Returns True si el usuario confirma, False si cancela.
    """
    consola.print(
        f"\n  Se van a escribir [bold cyan]{num_movimientos}[/bold cyan] "
        "movimiento(s) en [bold]presupuesto.xlsx[/bold]."
    )
    return click.confirm("  ¿Continuar?", default=True)
