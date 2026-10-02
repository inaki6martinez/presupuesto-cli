"""Selector de cuenta compartido, con saldo opcional."""
from __future__ import annotations
from decimal import Decimal


def seleccionar_cuenta(
    cuentas: list[tuple[str, str, str]],
    balances: dict[str, Decimal] | None = None,
) -> tuple[str, str, str] | None:
    """TUI full-screen para seleccionar una cuenta. Devuelve (cuenta, banco, tipo_cuenta) o None."""
    from prompt_toolkit import Application
    from prompt_toolkit.application import get_app
    from prompt_toolkit.formatted_text import FormattedText
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.styles import Style

    style = Style.from_dict({
        "titulo":  "bold",
        "cursor":  "reverse bold",
        "filtro":  "bold yellow",
        "dim":     "#666666",
        "neg":     "#ff5555",
        "pos":     "#55ff55",
        "footer":  "#666666",
        "fkey":    "#aaaaaa bold",
    })

    state: dict = {"cursor": 0, "filtro": "", "resultado": None}

    def _filtradas() -> list[tuple[str, str, str]]:
        f = state["filtro"].lower()
        if not f:
            return cuentas
        return [c for c in cuentas if f in c[0].lower()]

    def _clamp() -> None:
        vis = _filtradas()
        state["cursor"] = max(0, min(state["cursor"], len(vis) - 1))

    def _render() -> FormattedText:
        try:
            size = get_app().output.get_size()
            w, h = size.columns, size.rows
        except Exception:
            w, h = 120, 40

        buf: list[tuple[str, str]] = []
        def t(st: str, s: str) -> None: buf.append((st, s))
        def nl() -> None: buf.append(("", "\n"))

        t("class:titulo", "  Actualizar balance de cuenta" if balances is not None else "  Seleccionar cuenta")
        nl()
        filtro_txt = (state["filtro"] + "▌") if state["filtro"] else "▌"
        t("class:dim",    "  Filtro: ")
        t("class:filtro", filtro_txt)
        nl()
        t("class:dim", "─" * w)
        nl()

        columna = "Balance actual" if balances is not None else "Tipo de cuenta"
        t("class:dim", f"  {'Cuenta':<30}  {'Banco':<20}  {columna:>15}")
        nl()
        t("class:dim", "─" * w)
        nl()

        vis = _filtradas()
        list_h = max(3, h - 9)
        cur = state["cursor"]
        ws_start = max(0, cur - list_h // 2)
        ws_end   = min(len(vis), ws_start + list_h)
        ws_start = max(0, ws_end - list_h)

        for i in range(ws_start, ws_end):
            cuenta, banco, _ = vis[i]
            balance = (balances or {}).get(cuenta, Decimal(0))
            es_cur  = i == cur
            arrow   = "►" if es_cur else " "
            imp_st  = "class:neg" if balance < 0 else "class:pos"
            row_st  = "class:cursor" if es_cur else ""

            t("class:dim", f"  {arrow} ")
            t(row_st, f"{cuenta:<30}  {banco:<20}  ")
            if balances is not None:
                t(row_st if es_cur else imp_st, f"{balance:>+14.2f}€")
            else:
                t(row_st, vis[i][2])
            nl()

        t("class:dim", "─" * w)
        nl()
        for k, desc in [("↑↓", "Navegar"), ("Enter", "Seleccionar"),
                        ("^U", "Borrar filtro"), ("Esc", "Salir")]:
            t("class:fkey",   f" {k} ")
            t("class:footer", f"{desc}  ")

        return FormattedText(buf)

    kb = KeyBindings()

    @kb.add("up")
    def _(e):
        state["cursor"] = max(0, state["cursor"] - 1)

    @kb.add("down")
    def _(e):
        vis = _filtradas()
        state["cursor"] = min(max(0, len(vis) - 1), state["cursor"] + 1)

    @kb.add("enter")
    def _(e):
        vis = _filtradas()
        if vis:
            state["resultado"] = vis[state["cursor"]]
        e.app.exit()

    @kb.add("escape")
    @kb.add("c-c")
    def _(e): e.app.exit()  # noqa: E704

    @kb.add("backspace")
    @kb.add("c-h")
    def _(e):
        state["filtro"] = state["filtro"][:-1]
        _clamp()

    @kb.add("c-u")
    def _(e):
        state["filtro"] = ""
        _clamp()

    @kb.add("<any>")
    def _(e):
        key = e.key_sequence[0].key
        if isinstance(key, str) and len(key) == 1 and key.isprintable():
            state["filtro"] += key
            state["cursor"] = 0

    app = Application(
        layout=Layout(Window(content=FormattedTextControl(text=_render, focusable=True))),
        key_bindings=kb,
        style=style,
        full_screen=True,
    )
    app.run()
    return state["resultado"]

