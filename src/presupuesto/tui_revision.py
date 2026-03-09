"""TUIs de revisión de duplicados y confirmación final antes de escribir."""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

from prompt_toolkit import Application
from prompt_toolkit.application import get_app
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style

if TYPE_CHECKING:
    from presupuesto.categorizar import MovimientoCategorizado
    from presupuesto.maestro import DatosMaestros

_CONFIANZA_ICONO = {
    "alta":    ("class:conf.alta",   "✓"),
    "media":   ("class:conf.media",  "~"),
    "baja":    ("class:conf.baja",   "?"),
    "ninguna": ("class:conf.ninguna","·"),
}

_STYLE = Style.from_dict({
    "titulo":        "bold",
    "cursor":        "reverse bold",
    "excluido":      "bold #ff5555",
    "excluido.chk":  "#ff5555",
    "selec":         "bold #00cc44",
    "dim":           "#666666",
    "neg":           "#ff5555",
    "pos":           "#55ff55",
    "warn":          "bold yellow",
    "footer":        "#666666",
    "fkey":          "#aaaaaa bold",
    "confirm.box":   "bold",
    "conf.alta":     "#00cc44",
    "conf.media":    "#cccc00",
    "conf.baja":     "#ff5555",
    "conf.ninguna":  "#666666",
})


# ---------------------------------------------------------------------------
# TUI Revisión de Duplicados
# ---------------------------------------------------------------------------

class TUIRevisionDuplicados:
    """Muestra duplicados detectados y permite marcarlos para excluir."""

    def __init__(self, duplicados: list[tuple[MovimientoCategorizado, int]]) -> None:
        self._dups    = duplicados
        self._excl: set[int] = set()   # índices en self._dups a excluir
        self._cursor  = 0
        self._accion  = "cancelar"

    def run(self) -> set[int]:
        """Devuelve los índices de self._dups que el usuario quiere excluir.

        Si el usuario cancela (Esc), devuelve set vacío (mantener todos).
        """
        if not self._dups:
            return set()
        app = Application(
            layout=Layout(Window(content=FormattedTextControl(
                text=self._render, focusable=True,
            ))),
            key_bindings=self._kb(),
            style=_STYLE,
            full_screen=True,
        )
        app.run()
        return self._excl if self._accion == "confirmar" else set()

    def _kb(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("up")
        def _(e): self._cursor = max(0, self._cursor - 1)  # noqa: E704

        @kb.add("down")
        def _(e): self._cursor = min(len(self._dups) - 1, self._cursor + 1)  # noqa: E704

        @kb.add("space")
        def _(e):
            if self._cursor in self._excl:
                self._excl.discard(self._cursor)
            else:
                self._excl.add(self._cursor)

        @kb.add("enter")
        def _(e):
            self._accion = "confirmar"
            e.app.exit()

        @kb.add("escape")
        @kb.add("c-c")
        def _(e):
            self._accion = "cancelar"
            e.app.exit()

        return kb

    def _render(self) -> FormattedText:
        try:
            size = get_app().output.get_size()
            w, h = size.columns, size.rows
        except Exception:
            w, h = 120, 40

        buf: list[tuple[str, str]] = []

        def t(st: str, s: str) -> None: buf.append((st, s))
        def nl() -> None: buf.append(("", "\n"))

        n_excl = len(self._excl)
        t("class:warn", f"  ⚠  {len(self._dups)} posible(s) duplicado(s) detectado(s)")
        if n_excl:
            t("class:excluido", f"    {n_excl} marcado(s) para excluir")
        nl()
        t("class:dim", "─" * w)
        nl()

        col_w = max(20, (w - 10) // 2)
        t("class:titulo", f"  {'':3}  {'Movimiento a importar':<{col_w}}")
        t("class:dim",   "  ↔  ")
        t("class:titulo", f"{'Ya existe en xlsx':<{col_w}}")
        nl()
        t("class:dim", "─" * w)
        nl()

        list_h = max(3, h - 9)
        ws = max(0, self._cursor - list_h // 2)
        we = min(len(self._dups), ws + list_h)
        ws = max(0, we - list_h)

        for i in range(ws, we):
            mov, fila = self._dups[i]
            es_cur  = i == self._cursor
            es_excl = i in self._excl

            chk    = "[✕]" if es_excl else "[ ]"
            arrow  = "►" if es_cur else " "
            chk_st = "class:excluido.chk" if es_excl else "class:dim"
            row_st = "class:cursor" if es_cur else ("class:excluido" if es_excl else "")

            nuevo = (
                f"{mov.mes} {mov.año}  {mov.importe:+.2f}€  "
                f"{mov.categoria1} / {(mov.proveedor or mov.categoria2 or '')}"
            )[:col_w]
            exist = (
                f"fila {fila}: {mov.categoria1} / "
                f"{(mov.proveedor or mov.categoria2 or '')}  {mov.importe:+.2f}€"
            )[:col_w]

            t("class:dim",  f" {arrow} ")
            t(chk_st,       f"{chk} ")
            t(row_st,       f"{nuevo:<{col_w}}")
            t("class:dim",  "  ↔  ")
            t("class:dim",  exist)
            nl()

        t("class:dim", "─" * w)
        nl()
        for k, desc in [("↑↓", "Navegar"), ("Spc", "Excluir/incluir"),
                         ("Enter", "Confirmar"), ("Esc", "Mantener todos")]:
            t("class:fkey",   f" {k} ")
            t("class:footer", f"{desc}  ")

        return FormattedText(buf)


# ---------------------------------------------------------------------------
# TUI Revisión Final
# ---------------------------------------------------------------------------

class TUIRevisionFinal:
    """Lista todos los movimientos listos para escribir con opción de editar y confirmar."""

    def __init__(
        self,
        movimientos: list[MovimientoCategorizado],
        maestros: DatosMaestros,
    ) -> None:
        self._movs    = movimientos    # mutable; se edita in-place
        self._maestros = maestros
        self._cursor   = 0
        self._accion   = "loop"
        self._confirm_visible = False
        self._editar_idx = -1

    def run(self) -> bool:
        """Ejecuta el TUI. Devuelve True si el usuario confirma la escritura."""
        while True:
            self._accion = "loop"
            self._confirm_visible = False

            app = Application(
                layout=Layout(Window(content=FormattedTextControl(
                    text=self._render, focusable=True,
                ))),
                key_bindings=self._kb(),
                style=_STYLE,
                full_screen=True,
            )
            app.run()

            if self._accion == "editar":
                self._editar_movimiento(self._editar_idx)
            elif self._accion == "confirmar":
                return True
            else:
                return False

    def _editar_movimiento(self, idx: int) -> None:
        from presupuesto.tui_categorizar import TUICategorizacion
        mov = self._movs[idx]
        tui = TUICategorizacion(mov, self._maestros)
        resultado = tui.run()
        if isinstance(resultado, dict):
            self._movs[idx] = dataclasses.replace(
                mov, **resultado,
                confianza="alta", fuente="manual", requiere_confirmacion=False,
            )

    def _kb(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("up")
        def _(e): self._cursor = max(0, self._cursor - 1)  # noqa: E704

        @kb.add("down")
        def _(e): self._cursor = min(len(self._movs) - 1, self._cursor + 1)  # noqa: E704

        @kb.add("enter")
        def _(e):
            if self._confirm_visible:
                self._accion = "confirmar"
                e.app.exit()
            else:
                self._editar_idx = self._cursor
                self._accion = "editar"
                e.app.exit()

        @kb.add("c")
        def _(e):
            self._confirm_visible = True

        @kb.add("escape")
        def _(e):
            if self._confirm_visible:
                self._confirm_visible = False
            else:
                self._accion = "cancelar"
                e.app.exit()

        @kb.add("c-c")
        def _(e):
            self._accion = "cancelar"
            e.app.exit()

        return kb

    def _render(self) -> FormattedText:
        try:
            size = get_app().output.get_size()
            w, h = size.columns, size.rows
        except Exception:
            w, h = 120, 40

        buf: list[tuple[str, str]] = []

        def t(st: str, s: str) -> None: buf.append((st, s))
        def nl() -> None: buf.append(("", "\n"))

        t("class:titulo", f"  {len(self._movs)} movimiento(s) listos para añadir")
        nl()
        t("class:dim", "─" * w)
        nl()

        # Cabecera de columnas
        t("class:dim", "    ")
        t("class:titulo", f"{'Fecha':<10}  {'Concepto':<35}  {'Importe':>10}  "
          f"{'Cat. 1':<15}  {'Cat. 2':<15}  {'Proveedor':<15}  ")
        nl()
        t("class:dim", "─" * w)
        nl()

        list_h = max(3, h - (11 if self._confirm_visible else 8))
        ws = max(0, self._cursor - list_h // 2)
        we = min(len(self._movs), ws + list_h)
        ws = max(0, we - list_h)

        for i in range(ws, we):
            m      = self._movs[i]
            es_cur = i == self._cursor
            conf_st, icono = _CONFIANZA_ICONO.get(m.confianza, ("class:dim", "·"))
            arrow  = "►" if es_cur else " "

            concepto = (m.concepto_original or "")[:35]
            imp_str  = f"{m.importe:+.2f}€"
            imp_st   = "class:neg" if m.importe < 0 else "class:pos"
            grp_str  = f"×{m.n_originales}" if m.n_originales > 1 else "  "
            grp_st   = "class:warn" if m.n_originales > 1 else "class:dim"

            row_st = "class:cursor" if es_cur else ""

            t("class:dim", f" {arrow} ")
            t(row_st if es_cur else grp_st, f"{grp_str} ")
            t(row_st, f"{m.mes:<3} {m.año}  {concepto:<35}  ")
            t(row_st if es_cur else imp_st, f"{imp_str:>10}  ")
            t(row_st, f"{m.categoria1:<15}  {m.categoria2:<15}  {(m.proveedor or ''):<15}  ")
            t(row_st if es_cur else conf_st, icono)
            nl()

        t("class:dim", "─" * w)
        nl()

        if self._confirm_visible:
            t("class:confirm.box",
              f"  ¿Escribir {len(self._movs)} movimiento(s) en presupuesto.xlsx?")
            nl()
            for k, desc in [("Enter", "Confirmar"), ("Esc", "Volver a la lista")]:
                t("class:fkey",   f" {k} ")
                t("class:footer", f"{desc}  ")
        else:
            for k, desc in [("↑↓", "Navegar"), ("Enter", "Editar seleccionado"),
                             ("c", "Confirmar escritura"), ("Esc", "Cancelar")]:
                t("class:fkey",   f" {k} ")
                t("class:footer", f"{desc}  ")

        return FormattedText(buf)
