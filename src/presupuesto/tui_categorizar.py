"""TUI de categorización multi-columna estilo lazygit.

Muestra 6 columnas (2 filas × 3 columnas) con las opciones de cada campo.
Navegación con ←→, filtrado escribiendo texto, selección con Espacio y
confirmación con Enter.
"""

from __future__ import annotations

from dataclasses import dataclass
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


# (clave en MovimientoCategorizado, propiedad en DatosMaestros, etiqueta)
_COLS_DEF = [
    ("categoria1", "categorias1", "Categoría 1"),
    ("categoria2", "categorias2", "Categoría 2"),
    ("categoria3", "categorias3", "Categoría 3"),
    ("entidad",    "entidades",   "Entidad"),
    ("proveedor",  "proveedores", "Proveedor"),
    ("tipo_gasto", "tipos_gasto", "Tipo Gasto"),
]

# Índices de columna organizados en 2 filas de 3
_FILAS = [[0, 1, 2], [3, 4, 5]]

_SEP = " │ "  # separador entre columnas (3 chars)

_STYLE = Style.from_dict({
    "a.borde":  "bold cyan",
    "a.titulo": "bold cyan",
    "a.filtro": "bold yellow",
    "titulo":   "bold",
    "selec":    "bold #00cc44",
    "cursor":        "reverse bold",
    "cursor_selec":  "reverse bold #00cc44",
    "dim":      "#666666",
    "neg":      "#ff5555",
    "pos":      "#55ff55",
    "footer":   "#666666",
    "fkey":     "#aaaaaa bold",
})


@dataclass
class _Col:
    clave: str
    opciones: list[str]
    valor: str
    filtro: str = ""
    cursor: int = 0

    def filtradas(self) -> list[str]:
        if not self.filtro:
            return self.opciones
        f = self.filtro.lower()
        return [o for o in self.opciones if f in o.lower()]

    def clamp(self) -> None:
        maxc = max(0, len(self.filtradas()) - 1)
        self.cursor = max(0, min(self.cursor, maxc))


class TUICategorizacion:
    """TUI full-screen para categorizar un movimiento."""

    def __init__(
        self,
        sugerencia: MovimientoCategorizado,
        maestros: DatosMaestros,
    ) -> None:
        self._sug = sugerencia
        self._cols: list[_Col] = []
        for clave, prop, _ in _COLS_DEF:
            opciones = list(getattr(maestros, prop))
            valor = getattr(sugerencia, clave, "") or ""
            col = _Col(clave=clave, opciones=opciones, valor=valor)
            if valor and valor in opciones:
                col.cursor = opciones.index(valor)
            self._cols.append(col)
        self._activa = 0
        self._resultado: dict | str | None = None
        self._menu: bool = False   # True cuando el menú Esc está abierto

    def run(self) -> dict | str | None:
        """Ejecuta el TUI. Devuelve dict de campos, 'saltar', 'salir', 'volver' o None."""
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
    # Teclas
    # -------------------------------------------------------------------------

    def _keybindings(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("left")
        def _(e): self._activa = (self._activa - 1) % len(_COLS_DEF)  # noqa: E704

        @kb.add("right")
        def _(e): self._activa = (self._activa + 1) % len(_COLS_DEF)  # noqa: E704

        @kb.add("up")
        def _(e):
            c = self._cols[self._activa]
            c.cursor = max(0, c.cursor - 1)

        @kb.add("down")
        def _(e):
            c = self._cols[self._activa]
            c.cursor = min(max(0, len(c.filtradas()) - 1), c.cursor + 1)

        @kb.add("space")
        def _(e):
            c = self._cols[self._activa]
            f = c.filtradas()
            if f and c.cursor < len(f):
                c.valor = f[c.cursor]
            elif c.filtro:
                c.valor = c.filtro   # texto libre (ej. proveedor)
            c.filtro = ""
            c.clamp()
            # Avanzar automáticamente a la siguiente columna
            self._activa = (self._activa + 1) % len(_COLS_DEF)

        @kb.add("enter")
        def _(e):
            self._resultado = {c.clave: c.valor for c in self._cols}
            e.app.exit()

        @kb.add("escape")
        def _(e):
            if self._menu:
                self._menu = False   # cerrar menú sin hacer nada
            else:
                self._menu = True    # abrir menú

        @kb.add("c-c")
        def _(e):
            self._resultado = None
            e.app.exit()

        @kb.add("backspace")
        @kb.add("c-h")
        def _(e):
            if self._menu:
                self._menu = False
                return
            c = self._cols[self._activa]
            c.filtro = c.filtro[:-1]
            c.clamp()

        @kb.add("c-u")   # borrar filtro completo
        def _(e):
            c = self._cols[self._activa]
            c.filtro = ""
            c.clamp()

        @kb.add("delete")
        @kb.add("c-d")   # limpiar valor seleccionado de la columna activa
        def _(e):
            c = self._cols[self._activa]
            c.valor = ""
            c.filtro = ""

        @kb.add("<any>")
        def _(e):
            key = e.key_sequence[0].key
            if not (isinstance(key, str) and len(key) == 1 and key.isprintable()):
                return
            # ── Menú abierto: s/v/q ejecutan; cualquier otra tecla lo cierra ──
            if self._menu:
                self._menu = False
                if key == "s":
                    self._resultado = "saltar"; e.app.exit(); return
                if key == "q":
                    self._resultado = "salir";  e.app.exit(); return
                if key == "v":
                    self._resultado = "volver"; e.app.exit(); return
                return   # cualquier otra tecla: cerrar menú sin acción
            # ── Normal: todo al filtro ────────────────────────────────────────
            c = self._cols[self._activa]
            c.filtro += key
            c.cursor = 0

        return kb

    # -------------------------------------------------------------------------
    # Render
    # -------------------------------------------------------------------------

    def _render(self) -> FormattedText:
        try:
            size = get_app().output.get_size()
            w, h = size.columns, size.rows
        except Exception:
            w, h = 120, 40

        # Anchura de cada columna: 3 columnas con 2 separadores (_SEP = 3 chars)
        col_w   = max(12, (w - len(_SEP) * 2) // 3)
        # Líneas de lista por fila de columnas (descontando header, 2 filas, footer)
        list_h  = max(3, (h - 10) // 2)

        buf: list[tuple[str, str]] = []

        def t(st: str, s: str) -> None:
            buf.append((st, s))

        def nl() -> None:
            buf.append(("", "\n"))

        # ── Cabecera ─────────────────────────────────────────────────────────
        s = self._sug
        concepto = (s.concepto_original or "")[:w - 2]
        t("bold", f" {concepto}")
        nl()

        imp = f"{s.importe:+.2f}€"
        t("class:neg" if s.importe < 0 else "class:pos", f" {imp}")
        t("class:dim", f"   {s.mes} {s.año}   {s.cuenta}")
        if s.fuente:
            fuente_t = s.fuente[:max(0, w - len(imp) - len(s.cuenta) - 20)]
            t("class:dim", f"   [{fuente_t}]")
        nl()

        t("class:dim", "─" * w)
        nl()

        # ── Filas de columnas ─────────────────────────────────────────────────
        for fila in _FILAS:
            bloques = [self._render_col(ci, col_w, list_h) for ci in fila]
            n_lines = max(len(b) for b in bloques)

            for li in range(n_lines):
                for bi, ci in enumerate(fila):
                    linea = bloques[bi][li] if li < len(bloques[bi]) else [("", " " * col_w)]
                    buf.extend(linea)
                    if bi < len(fila) - 1:
                        t("class:dim", _SEP)
                nl()

            t("class:dim", "─" * w)
            nl()

        # ── Footer ────────────────────────────────────────────────────────────
        if self._menu:
            t("bold cyan", "  Acción:  ")
            menu = [("s", "Saltar"), ("v", "Volver"), ("q", "Salir"), ("Esc", "Cancelar")]
            for k, desc in menu:
                t("class:fkey", f" {k} ")
                t("class:footer", f"{desc}  ")
        else:
            acciones = [
                ("←→", "Columna"), ("↑↓", "Navegar"), ("Spc", "Selec"),
                ("Enter", "Confirmar"), ("Del", "Limpiar"), ("^U", "Borrar filtro"), ("Esc", "Menú"),
            ]
            for k, desc in acciones:
                t("class:fkey", f" {k} ")
                t("class:footer", f"{desc} ")

        return FormattedText(buf)

    def _render_col(
        self, ci: int, col_w: int, list_h: int
    ) -> list[list[tuple[str, str]]]:
        """Líneas de una columna. Cada elemento es una lista de (style, text)."""
        col = self._cols[ci]
        _, _, titulo = _COLS_DEF[ci]
        activa = ci == self._activa
        filtradas = col.filtradas()

        b_st = "class:a.borde"  if activa else "class:dim"
        t_st = "class:a.titulo" if activa else "class:titulo"
        f_st = "class:a.filtro" if activa else "class:dim"

        lines: list[list[tuple[str, str]]] = []

        def ln(*parts: tuple[str, str]) -> None:
            lines.append(list(parts))

        # ── Título ────────────────────────────────────────────────────────────
        titulo_t = titulo[:col_w - 4]
        dash_r   = "─" * max(0, col_w - len(titulo_t) - 3)
        ln((b_st, "──"), (t_st, f" {titulo_t} "), (b_st, dash_r))

        # ── Filtro / valor actual ──────────────────────────────────────────────
        if activa:
            txt_f = (col.filtro + "▌")[:col_w - 2]
            ln((f_st, f" {txt_f:<{col_w - 2}}"))
        else:
            if col.valor:
                val_t = col.valor[:col_w - 4]
                ln((b_st, " "), ("class:selec", f"✓ {val_t:<{col_w - 4}}"), (b_st, " "))
            else:
                ln(("class:dim", " " + "·" * (col_w - 2) + " "))

        # ── Lista con ventana deslizante ──────────────────────────────────────
        win_start = max(0, col.cursor - list_h // 2)
        win_end   = min(len(filtradas), win_start + list_h)
        win_start = max(0, win_end - list_h)
        visible   = filtradas[win_start:win_end]

        for i, opcion in enumerate(visible):
            real_i    = win_start + i
            es_cursor = real_i == col.cursor
            es_valor  = opcion == col.valor
            cur_m     = "►" if es_cursor else " "
            val_m     = "✓" if es_valor  else " "
            op_t      = opcion[:col_w - 5]
            pad       = " " * (col_w - 5 - len(op_t))

            if es_cursor and es_valor:
                st = "class:cursor_selec"
            elif es_cursor:
                st = "class:cursor"
            elif es_valor:
                st = "class:selec"
            else:
                st = ""

            ln(
                (b_st if activa else "class:dim", f" {cur_m}"),
                ("class:selec" if es_valor else "class:dim", val_m),
                ("", " "),
                (st, f"{op_t}{pad}"),
                ("", " "),
            )

        # Relleno hasta list_h
        for _ in range(list_h - len(visible)):
            ln(("", " " * col_w))

        return lines
