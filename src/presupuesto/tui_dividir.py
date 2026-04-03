"""TUI para dividir un movimiento en varias partes antes de categorizar.

Uso:
    partes = TUIDividir(mov_crudo).run()
    # partes == None  → el usuario canceló (no dividir)
    # partes == [(Decimal, str), ...]  → lista de (importe, descripcion)

Navegación:
    ↑↓      Seleccionar parte
    Enter   Editar importe de la parte seleccionada
    Tab     Editar descripción de la parte seleccionada
    +       Añadir parte nueva (con el restante como importe por defecto)
    -       Eliminar parte seleccionada
    f       Confirmar división (solo si restante == 0)
    Esc     Cancelar (no dividir)
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
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
    from presupuesto.parsers.base import MovimientoCrudo

_STYLE = Style.from_dict({
    "titulo":    "bold",
    "concepto":  "bold",
    "neg":       "#ff5555",
    "pos":       "#55ff55",
    "dim":       "#666666",
    "cursor":    "reverse bold",
    "edit":      "bold yellow",
    "ok":        "bold green",
    "warn":      "bold yellow",
    "err":       "bold red",
    "footer":    "#666666",
    "fkey":      "#aaaaaa bold",
})


class TUIDividir:
    """TUI full-screen para dividir un movimiento en partes."""

    def __init__(self, mov_crudo) -> None:
        self._mov = mov_crudo
        self._total = mov_crudo.importe
        # Empezamos con una sola parte = total
        self._partes: list[dict] = [
            {"importe": self._total, "desc": ""},
        ]
        self._cursor = 0
        # modo: "nav" | "imp" (editando importe) | "desc" (editando descripcion)
        self._modo = "nav"
        self._buf = ""          # buffer de texto en modo edición
        self._resultado: list | None = None   # None = sin resultado todavía

    # -------------------------------------------------------------------------
    # API pública
    # -------------------------------------------------------------------------

    def run(self) -> list[tuple[Decimal, str]] | None:
        """Ejecuta el TUI. Devuelve [(importe, desc), ...] o None si se cancela."""
        app = Application(
            layout=Layout(Window(
                content=FormattedTextControl(text=self._render, focusable=True),
            )),
            key_bindings=self._keybindings(),
            style=_STYLE,
            full_screen=True,
            mouse_support=False,
        )
        app.run()
        return self._resultado

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _restante(self) -> Decimal:
        return self._total - sum(p["importe"] for p in self._partes)

    def _clamp(self) -> None:
        n = len(self._partes)
        if n == 0:
            self._cursor = 0
        else:
            self._cursor = max(0, min(self._cursor, n - 1))

    def _parte_actual(self) -> dict:
        return self._partes[self._cursor]

    def _confirmar(self, app) -> None:
        if self._restante() != Decimal("0"):
            return
        if len(self._partes) < 2:
            return
        self._resultado = [
            (p["importe"], p["desc"]) for p in self._partes
        ]
        app.exit()

    # -------------------------------------------------------------------------
    # Keybindings
    # -------------------------------------------------------------------------

    def _keybindings(self) -> KeyBindings:
        kb = KeyBindings()

        # ── Escape: salir de edición o cancelar ──────────────────────────────
        @kb.add("escape")
        def _(e):
            if self._modo != "nav":
                # Descartar edición
                self._modo = "nav"
                self._buf = ""
            else:
                e.app.exit()  # resultado = None → no dividir

        @kb.add("c-c")
        def _(e):
            e.app.exit()

        # ── Navegación (solo en modo nav) ─────────────────────────────────────
        @kb.add("up")
        def _(e):
            if self._modo == "nav":
                self._cursor = max(0, self._cursor - 1)

        @kb.add("down")
        def _(e):
            if self._modo == "nav":
                self._cursor = min(len(self._partes) - 1, self._cursor + 1)

        # ── Enter: editar importe / confirmar edición ─────────────────────────
        @kb.add("enter")
        def _(e):
            if self._modo == "nav":
                self._modo = "imp"
                self._buf = str(self._parte_actual()["importe"])
            elif self._modo in ("imp", "desc"):
                self._commit_edicion()
                self._modo = "nav"
                self._buf = ""

        # ── Tab: editar descripción ───────────────────────────────────────────
        @kb.add("tab")
        def _(e):
            if self._modo == "nav":
                self._modo = "desc"
                self._buf = self._parte_actual()["desc"]
            elif self._modo == "imp":
                self._commit_edicion()
                self._modo = "desc"
                self._buf = self._parte_actual()["desc"]
            elif self._modo == "desc":
                self._commit_edicion()
                self._modo = "nav"
                self._buf = ""

        # ── + Añadir parte ────────────────────────────────────────────────────
        @kb.add("+")
        def _(e):
            if self._modo != "nav":
                return
            restante = self._restante()
            self._partes.append({"importe": restante, "desc": ""})
            self._cursor = len(self._partes) - 1

        # ── - Eliminar parte ──────────────────────────────────────────────────
        @kb.add("-")
        def _(e):
            if self._modo != "nav":
                return
            if len(self._partes) <= 1:
                return
            del self._partes[self._cursor]
            self._clamp()

        # ── f: confirmar división ─────────────────────────────────────────────
        @kb.add("f")
        def _(e):
            if self._modo != "nav":
                return
            self._confirmar(e.app)

        # ── Backspace en edición ──────────────────────────────────────────────
        @kb.add("backspace")
        @kb.add("c-h")
        def _(e):
            if self._modo in ("imp", "desc"):
                self._buf = self._buf[:-1]

        # ── Caracteres en modo edición ────────────────────────────────────────
        @kb.add("<any>")
        def _(e):
            key = e.key_sequence[0].key
            if not (isinstance(key, str) and len(key) == 1 and key.isprintable()):
                return
            if self._modo == "imp":
                if key in "0123456789.,-":
                    self._buf += key
            elif self._modo == "desc":
                self._buf += key

        return kb

    def _commit_edicion(self) -> None:
        """Aplica el buffer al campo en edición."""
        if self._modo == "imp":
            raw = self._buf.strip().replace(",", ".")
            try:
                valor = Decimal(raw).quantize(Decimal("0.01"))
                self._parte_actual()["importe"] = valor
            except InvalidOperation:
                pass  # descartamos valor inválido
        elif self._modo == "desc":
            self._parte_actual()["desc"] = self._buf.strip()

    # -------------------------------------------------------------------------
    # Render
    # -------------------------------------------------------------------------

    def _render(self) -> FormattedText:
        try:
            size = get_app().output.get_size()
            w, h = size.columns, size.rows
        except Exception:
            w, h = 80, 30

        buf: list[tuple[str, str]] = []
        def t(st, s): buf.append((st, s))
        def nl():     buf.append(("", "\n"))

        # ── Cabecera ──────────────────────────────────────────────────────────
        concepto = (
            getattr(self._mov, "concepto_original", None)
            or getattr(self._mov, "concepto", None)
            or ""
        )[:w - 2]
        t("class:concepto", f" {concepto}")
        nl()
        imp_total = self._total
        color_tot = "class:neg" if imp_total < 0 else "class:pos"
        t(color_tot, f" Total: {imp_total:+.2f}€")
        fecha_str = str(getattr(self._mov, "fecha", None) or
                        f"{getattr(self._mov, 'mes', '')} {getattr(self._mov, 'año', '')}")
        t("class:dim", f"   {fecha_str}")
        nl()
        t("class:dim", "─" * w)
        nl()

        # ── Lista de partes ───────────────────────────────────────────────────
        for i, parte in enumerate(self._partes):
            es_cur = i == self._cursor
            arrow = "►" if es_cur else " "

            if es_cur and self._modo == "imp":
                imp_txt = self._buf + "▌"
                imp_st = "class:edit"
            else:
                imp_txt = f"{parte['importe']:+.2f}€"
                imp_st = ("class:neg" if parte["importe"] < 0 else "class:pos")

            if es_cur and self._modo == "desc":
                desc_txt = self._buf + "▌"
                desc_st = "class:edit"
            else:
                desc_txt = parte["desc"] or "—"
                desc_st = "class:dim"

            row_st = "class:cursor" if (es_cur and self._modo == "nav") else ""

            t("class:dim", f"  {arrow} [{i + 1}]  ")
            t(imp_st,  f"{imp_txt:<14}")
            t(desc_st, f"  {desc_txt}")
            nl()

        nl()

        # ── Restante ─────────────────────────────────────────────────────────
        restante = self._restante()
        if restante == Decimal("0"):
            rest_st, rest_txt = "class:ok",   f"Restante: {restante:+.2f}€  ✓"
        elif restante != self._total:
            rest_st, rest_txt = "class:warn",  f"Restante: {restante:+.2f}€"
        else:
            rest_st, rest_txt = "class:dim",   f"Restante: {restante:+.2f}€"
        t(rest_st, f"  {rest_txt}")
        nl()

        t("class:dim", "─" * w)
        nl()

        # ── Footer ────────────────────────────────────────────────────────────
        puede_confirmar = restante == Decimal("0") and len(self._partes) >= 2
        if self._modo == "nav":
            atajos = [
                ("↑↓", "Navegar"),
                ("Enter", "Editar importe"),
                ("Tab",   "Editar desc"),
                ("+",     "Añadir"),
                ("-",     "Eliminar"),
            ]
            if puede_confirmar:
                atajos.append(("f", "Confirmar"))
            atajos.append(("Esc", "Cancelar"))
        else:
            atajos = [
                ("Enter", "Aplicar"),
                ("Tab",   "Siguiente campo"),
                ("Esc",   "Descartar"),
            ]

        for k, desc in atajos:
            t("class:fkey",   f" {k} ")
            t("class:footer", f"{desc}  ")

        return FormattedText(buf)
