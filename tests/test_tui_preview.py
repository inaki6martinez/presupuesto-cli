from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from presupuesto.categorizar import MovimientoCategorizado
from presupuesto.tui_preview import TUIPreviewImport


@dataclass
class _Mov:
    fecha: date
    concepto: str
    importe: Decimal
    concepto_original: str = ""


class _CategorizadorDummy:
    def categorizar(self, mov, cuenta):  # noqa: ARG002
        confianza = {
            "alta": "alta",
            "media": "media",
            "baja": "baja",
        }[mov.concepto]
        requiere_confirmacion = confianza != "alta"
        return MovimientoCategorizado(
            año=2025,
            mes="Ene",
            categoria1="Cat1",
            categoria2="Cat2",
            categoria3="Cat3",
            entidad="Entidad",
            importe=mov.importe,
            proveedor="Proveedor",
            tipo_gasto="Fijos",
            cuenta=cuenta,
            banco="Banco",
            tipo_cuenta="Activos liquidos",
            confianza=confianza,
            fuente="dummy",
            requiere_confirmacion=requiere_confirmacion,
            concepto_original=mov.concepto_original,
        )


class _GestorReglasDummy:
    def recargar(self):
        return 0


def test_preview_marca_por_defecto_los_no_alta_confianza():
    movs = [
        _Mov(date(2025, 1, 1), "alta", Decimal("10")),
        _Mov(date(2025, 1, 2), "media", Decimal("11")),
        _Mov(date(2025, 1, 3), "baja", Decimal("12")),
    ]

    tui = TUIPreviewImport(
        movs,
        "Cuenta Prueba",
        _CategorizadorDummy(),
        _GestorReglasDummy(),
        nombre_archivo="test.csv",
    )

    assert tui._seleccionados == {1, 2}


def test_preview_muestra_texto_informativo():
    movs = [_Mov(date(2025, 1, 1), "alta", Decimal("10"))]

    tui = TUIPreviewImport(
        movs,
        "Cuenta Prueba",
        _CategorizadorDummy(),
        _GestorReglasDummy(),
        nombre_archivo="test.csv",
    )

    rendered = "".join(text for _, text in tui._render())
    assert "Este menú sirve para marcar" in rendered
    assert "Por defecto se marcan los que no tienen confianza alta" in rendered
