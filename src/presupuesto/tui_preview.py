"""TUI de previsualización de movimientos antes de importar.

Muestra todos los movimientos parseados con su categorización automática
(regla aplicada, confianza, cat1/cat2/cat3) y permite:
- Seleccionar/deseleccionar movimientos individualmente
- Recargar el fichero de reglas sin salir ('r')
- Confirmar qué movimientos se procesarán (Enter)
- Cancelar la importación del archivo (Esc)
"""
from __future__ import annotations

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
    from presupuesto.categorizar import Categorizador, MovimientoCategorizado
    from presupuesto.parsers.base import MovimientoCrudo
    from presupuesto.reglas import GestorReglas


_STYLE = Style.from_dict({
    "titulo":       "bold",
    "cursor":       "reverse bold",
    "dim":          "#666666",
    "neg":          "#ff5555",
    "pos":          "#55ff55",
    "warn":         "bold yellow",
    "footer":       "#666666",
    "fkey":         "#aaaaaa bold",
    "selec":        "#55ff55",
    "noselec":      "#666666",
    "conf-alta":    "#00cc44",
    "conf-media":   "#cccc00",
    "conf-baja":    "#ff5555",
    "conf-ninguna": "#666666",
    "msg":          "bold cyan",
})

_CONF_ICONO: dict[str, tuple[str, str]] = {
    "alta":    ("class:conf-alta",    "✓"),
    "media":   ("class:conf-media",   "~"),
    "baja":    ("class:conf-baja",    "?"),
    "ninguna": ("class:conf-ninguna", "·"),
}


class TUIPreviewImport:
    """TUI de previsualización: lista movimientos con su categorización automática.

    Permite seleccionar cuáles se procesarán y recargar las reglas en caliente.
    """

    def __init__(
        self,
        movimientos_crudos: list[MovimientoCrudo],
        cuenta: str,
        categorizador: Categorizador,
        gestor_reglas: GestorReglas,
        nombre_archivo: str = "",
    ) -> None:
        self._movs = movimientos_crudos
        self._cuenta = cuenta
        self._categorizador = categorizador
        self._gestor_reglas = gestor_reglas
        self._nombre_archivo = nombre_archivo
        self._resultados: list[tuple[MovimientoCrudo, MovimientoCategorizado]] = []
        self._seleccionados: set[int] = set()
        self._cursor = 0
        self._accion = "cancelar"
        self._msg = ""
        self._recategorizar()

    def _recategorizar(self) -> None:
        """Re-categoriza todos los movimientos (se llama al inicio y al recargar reglas)."""
        self._resultados = [
            (mov, self._categorizador.categorizar(mov, self._cuenta))
            for mov in self._movs
        ]
        # Por defecto se marcan los que no tienen confianza alta para revisión manual.
        self._seleccionados = {
            i for i, (_, cat) in enumerate(self._resultados)
            if cat.confianza != "alta"
        }

    def run(self) -> tuple[list[tuple], set[int]] | None:
        """Ejecuta el TUI.

        Returns:
            (resultados, seleccionados): todos los (mov_crudo, mov_cat) y el conjunto
            de índices marcados para revisión interactiva.
            None: el usuario canceló (Esc).
        """
        if not self._movs:
            return ([], set())

        app = Application(
            layout=Layout(Window(content=FormattedTextControl(
                text=self._render, focusable=True,
            ))),
            key_bindings=self._kb(),
            style=_STYLE,
            full_screen=True,
        )
        app.run()

        if self._accion == "confirmar":
            return (list(self._resultados), set(self._seleccionados))
        return None

    def _kb(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("up")
        def _(e):
            self._cursor = max(0, self._cursor - 1)
            self._msg = ""

        @kb.add("down")
        def _(e):
            self._cursor = min(len(self._resultados) - 1, self._cursor + 1)
            self._msg = ""

        @kb.add("space")
        def _(e):
            if self._cursor in self._seleccionados:
                self._seleccionados.discard(self._cursor)
            else:
                self._seleccionados.add(self._cursor)
            self._msg = ""

        @kb.add("a")
        def _(e):
            if len(self._seleccionados) == len(self._resultados):
                self._seleccionados.clear()
                self._msg = "Todos deseleccionados"
            else:
                self._seleccionados = set(range(len(self._resultados)))
                self._msg = "Todos seleccionados"

        @kb.add("r")
        def _(e):
            n = self._gestor_reglas.recargar()
            self._recategorizar()
            self._msg = f"Reglas recargadas ({n} reglas)"

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

        n_rev = len(self._seleccionados)
        n_tot = len(self._resultados)

        titulo = f"  {self._nombre_archivo or self._cuenta}"
        t("class:titulo", titulo)
        rev_txt = (
            f"  ({n_rev} marcado(s) para revisión)"
            if n_rev
            else "  (ninguno marcado — Enter importa todo)"
        )
        t("class:dim",    rev_txt)
        nl()

        t(
            "class:warn",
            "  Este menú sirve para marcar los movimientos que quieres revisar a mano. "
            "Por defecto se marcan los que no tienen confianza alta; los demás se importan automáticamente.",
        )
        nl()

        if self._msg:
            t("class:msg", f"  {self._msg}")
            nl()

        t("class:dim", "─" * w)
        nl()

        # Cabecera de columnas
        t("class:dim",    "  ")
        t("class:titulo", f"{'':5}  {'Fecha':<10}  {'Concepto':<28}  {'Importe':>10}  "
                          f"{'Fuente':<22}  {'Cat1':<14}  {'Cat2':<14}  {'Cat3':<12}  C")
        nl()
        t("class:dim", "─" * w)
        nl()

        extra_lineas = 2 if self._msg else 1
        list_h = max(3, h - 8 - extra_lineas)
        cur = self._cursor
        ws = max(0, cur - list_h // 2)
        we = min(n_tot, ws + list_h)
        ws = max(0, we - list_h)

        for i in range(ws, we):
            mov, cat = self._resultados[i]
            es_cur = i == cur
            es_sel = i in self._seleccionados

            chk    = "[✓]" if es_sel else "[ ]"
            arrow  = "►" if es_cur else " "
            chk_st = "class:selec" if es_sel else "class:noselec"
            row_st = "class:cursor" if es_cur else ""

            fecha_str  = str(mov.fecha)
            conc_str   = (mov.concepto or "")[:28]
            imp_str    = f"{mov.importe:+.2f}€"
            imp_st     = "class:neg" if mov.importe < 0 else "class:pos"
            fuente_str = (cat.fuente or "—")[:22]
            cat1_str   = (cat.categoria1 or "—")[:14]
            cat2_str   = (cat.categoria2 or "—")[:14]
            cat3_str   = (cat.categoria3 or "")[:12]
            conf_st, icono = _CONF_ICONO.get(cat.confianza, ("class:dim", "·"))

            t("class:dim", f"  {arrow} ")
            t(chk_st,      f"{chk}  ")
            t(row_st,      f"{fecha_str:<10}  {conc_str:<28}  ")
            t(row_st if es_cur else imp_st, f"{imp_str:>10}  ")
            t(row_st,      f"{fuente_str:<22}  {cat1_str:<14}  {cat2_str:<14}  {cat3_str:<12}  ")
            t(row_st if es_cur else conf_st, icono)
            nl()

        t("class:dim", "─" * w)
        nl()
        for k, desc in [
            ("↑↓",   "Navegar"),
            ("Spc",  "Marcar p/revisar"),
            ("a",    "Marcar todos"),
            ("r",    "Recargar reglas"),
            ("Enter","Importar"),
            ("Esc",  "Cancelar"),
        ]:
            t("class:fkey",   f" {k} ")
            t("class:footer", f"{desc}  ")

        return FormattedText(buf)
