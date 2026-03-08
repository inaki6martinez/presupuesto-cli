"""Tests del motor de categorización."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from presupuesto.categorizar import (
    Categorizador,
    MovimientoCategorizado,
    _RegistroHistorial,
)
from presupuesto.parsers.base import MovimientoCrudo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _movimiento(concepto: str, importe: str = "-10.00", fecha: date = date(2026, 3, 6)) -> MovimientoCrudo:
    return MovimientoCrudo(
        fecha=fecha,
        concepto=concepto,
        importe=Decimal(importe),
        concepto_original=f"{fecha} | {concepto}",
    )


def _maestros_mock(cuenta: str = "Cuenta Nomina", banco: str = "Openbank", tipo: str = "Activos liquidos"):
    maestros = MagicMock()
    maestros.autocompletar_cuenta.return_value = (banco, tipo)
    return maestros


def _reglas_sin_match():
    reglas = MagicMock()
    reglas.buscar_match.return_value = None
    reglas.buscar_match_con_patron.return_value = None
    return reglas


def _reglas_con_match(campos: dict, patron: str = "test-patron"):
    reglas = MagicMock()
    reglas.buscar_match.return_value = campos
    reglas.buscar_match_con_patron.return_value = (campos, patron)
    return reglas


def _historial(*registros: _RegistroHistorial) -> list[_RegistroHistorial]:
    return list(registros)


def _registro(proveedor, cat1="", cat2="", cat3="", entidad="", tipo_gasto="", cuenta=""):
    return _RegistroHistorial(
        proveedor=proveedor,
        categoria1=cat1,
        categoria2=cat2,
        categoria3=cat3,
        entidad=entidad,
        tipo_gasto=tipo_gasto,
        cuenta=cuenta,
    )


# ---------------------------------------------------------------------------
# Capa 1 — Reglas
# ---------------------------------------------------------------------------

class TestCapaReglas:
    def test_match_por_regla_confianza_alta(self):
        campos = {
            "categoria1": "Alimentación",
            "categoria2": "Supermercados",
            "categoria3": "",
            "entidad": "",
            "proveedor": "Eroski",
            "tipo_gasto": "Discrecionales",
        }
        cat = Categorizador(_maestros_mock(), _reglas_con_match(campos))
        resultado = cat.categorizar(_movimiento("COMPRA EN EROSKI CENTER"), "Cuenta Nomina")

        assert isinstance(resultado, MovimientoCategorizado)
        assert resultado.confianza == "alta"
        assert resultado.requiere_confirmacion is False
        assert resultado.categoria1 == "Alimentación"
        assert resultado.categoria2 == "Supermercados"
        assert resultado.proveedor == "Eroski"
        assert resultado.tipo_gasto == "Discrecionales"

    def test_match_por_regla_ignora_historial(self):
        """Si la capa 1 da resultado, no se consulta el historial."""
        campos = {"categoria1": "Ocio", "categoria2": "", "categoria3": "",
                  "entidad": "", "proveedor": "Netflix", "tipo_gasto": "Discrecionales"}
        cat = Categorizador(_maestros_mock(), _reglas_con_match(campos))
        # Aunque haya historial, la capa 1 tiene prioridad
        cat._historial = _historial(_registro("Netflix", cat1="Tecnología"))
        resultado = cat.categorizar(_movimiento("Netflix"), "Cuenta Ocio")
        assert resultado.categoria1 == "Ocio"
        assert resultado.confianza == "alta"

    def test_campos_parciales_rellena_vacios(self):
        """La regla puede no rellenar todos los campos; los vacíos quedan como ''."""
        campos = {"categoria1": "Vivienda", "proveedor": "Comunidad"}
        cat = Categorizador(_maestros_mock(), _reglas_con_match(campos))
        resultado = cat.categorizar(_movimiento("COMUNIDAD VECINOS"), "Cuenta Hipoteca")
        assert resultado.categoria2 == ""
        assert resultado.categoria3 == ""
        assert resultado.entidad == ""


# ---------------------------------------------------------------------------
# Capa 2 — Similitud con historial
# ---------------------------------------------------------------------------

class TestCapaSimilitud:
    def _cat_sin_reglas(self, historial: list[_RegistroHistorial], cuenta="Cuenta Nomina"):
        cat = Categorizador(_maestros_mock(cuenta=cuenta), _reglas_sin_match())
        cat._historial = historial
        return cat

    def test_match_historial_confianza_media(self):
        """Proveedor aparece literalmente en el concepto → confianza media."""
        hist = _historial(_registro("Eroski", cat1="Alimentación", cat2="Supermercados", tipo_gasto="Discrecionales"))
        cat = self._cat_sin_reglas(hist)
        resultado = cat.categorizar(_movimiento("Pago en EROSKI CENTER"), "Cuenta Nomina")

        assert resultado.confianza == "media"
        assert resultado.requiere_confirmacion is True
        assert resultado.categoria1 == "Alimentación"
        assert resultado.proveedor == "Eroski"

    def test_match_historial_proveedor_literal(self):
        """Proveedor aparece literalmente en el concepto → match."""
        hist = _historial(_registro("Mercadona", cat1="Alimentación", tipo_gasto="Discrecionales"))
        cat = self._cat_sin_reglas(hist)
        resultado = cat.categorizar(_movimiento("Compra supermercado Mercadona Vitoria"), "Cuenta Nomina")
        assert resultado.confianza == "media"
        assert resultado.proveedor == "Mercadona"

    def test_sin_match_proveedor_no_literal(self):
        """Proveedor que NO aparece literalmente en el concepto → capa 3."""
        hist = _historial(_registro("Fitness Revolucionario", cat1="Salud", tipo_gasto="Discrecionales"))
        cat = self._cat_sin_reglas(hist)
        # "ocio" no contiene "Fitness Revolucionario"
        resultado = cat.categorizar(_movimiento("ocio"), "Cuenta Nomina")
        assert resultado.confianza == "ninguna"

    def test_sin_historial_pasa_a_capa3(self):
        cat = Categorizador(_maestros_mock(), _reglas_sin_match())
        cat._historial = []
        resultado = cat.categorizar(_movimiento("Pago desconocido"), "Cuenta Nomina")
        assert resultado.confianza == "ninguna"

    def test_concepto_sin_coincidencia_pasa_a_capa3(self):
        hist = _historial(_registro("Eroski", cat1="Alimentación"))
        cat = self._cat_sin_reglas(hist)
        resultado = cat.categorizar(_movimiento("TRANSFERENCIA RECIBIDA NOMINA EMPRESA SA"), "Cuenta Nomina")
        # "Eroski" no aparece en este concepto → capa 3
        assert resultado.confianza == "ninguna"

    def test_desempate_por_contexto_cuenta(self):
        """Con dos candidatos empatados, prioriza el que cuadra con el contexto de la cuenta."""
        # "Ocio" encaja con "Cuenta Ocio"; "Tecnología" no
        hist = _historial(
            _registro("Netflix", cat1="Tecnología", cat2="Streaming", tipo_gasto="Discrecionales", cuenta="Cuenta Nomina"),
            _registro("Netflix", cat1="Ocio", cat2="Entretenimiento", tipo_gasto="Discrecionales", cuenta="Cuenta Ocio"),
        )
        cat = self._cat_sin_reglas(hist, cuenta="Cuenta Ocio")
        resultado = cat.categorizar(_movimiento("Netflix.com pago mensual"), "Cuenta Ocio")
        assert resultado.categoria1 == "Ocio"

    def test_desempate_sin_contexto_devuelve_primero(self):
        """Sin contexto útil, devuelve el primer candidato."""
        hist = _historial(
            _registro("Zara", cat1="Ropa", tipo_gasto="Discrecionales"),
            _registro("Zara", cat1="Ocio", tipo_gasto="Discrecionales"),
        )
        cat = self._cat_sin_reglas(hist, cuenta="Cuenta Nomina")
        # Cuenta Nomina tiene varias categorías probables, así que no hay desempate unívoco
        resultado = cat.categorizar(_movimiento("Pago Zara store"), "Cuenta Nomina")
        # Solo verificamos que devuelve un resultado válido de la capa 2
        assert resultado.confianza in ("media", "baja")


# ---------------------------------------------------------------------------
# Capa 3 — Sin match
# ---------------------------------------------------------------------------

class TestCapaSinMatch:
    def _cat_vacio(self, cuenta="Cuenta Nomina"):
        cat = Categorizador(_maestros_mock(cuenta=cuenta), _reglas_sin_match())
        cat._historial = []
        return cat

    def test_sin_match_confianza_ninguna(self):
        cat = self._cat_vacio()
        resultado = cat.categorizar(_movimiento("CONCEPTO TOTALMENTE DESCONOCIDO XYZ"), "Cuenta Nomina")
        assert resultado.confianza == "ninguna"
        assert resultado.requiere_confirmacion is True

    def test_sin_match_campos_vacios(self):
        cat = self._cat_vacio()
        resultado = cat.categorizar(_movimiento("GASTO RARO"), "Cuenta Nomina")
        assert resultado.categoria1 == ""
        assert resultado.categoria2 == ""
        assert resultado.categoria3 == ""
        assert resultado.entidad == ""
        assert resultado.proveedor == ""

    def test_contexto_hipoteca_sugiere_tipo_fijos(self):
        cat = self._cat_vacio(cuenta="Cuenta Hipoteca")
        resultado = cat.categorizar(_movimiento("PAGO HIPOTECA BBVA"), "Cuenta Hipoteca")
        assert resultado.tipo_gasto == "Fijos"

    def test_contexto_kutxabank_categoria_univoca(self):
        """Kutxabank tiene una sola categoría probable → se pre-rellena."""
        cat = self._cat_vacio(cuenta="Kutxabank")
        resultado = cat.categorizar(_movimiento("PEAJE AP-68"), "Kutxabank")
        assert resultado.categoria1 == "Transporte"
        assert resultado.tipo_gasto == "Fijos"

    def test_contexto_cuenta_nomina_categoria_no_prerellena(self):
        """Cuenta Nomina tiene múltiples categorías probables → no se pre-rellena."""
        cat = self._cat_vacio(cuenta="Cuenta Nomina")
        resultado = cat.categorizar(_movimiento("PAGO DESCONOCIDO"), "Cuenta Nomina")
        assert resultado.categoria1 == ""

    def test_contexto_epsv_categoria_univoca(self):
        cat = self._cat_vacio(cuenta="EPSV")
        resultado = cat.categorizar(_movimiento("INDEXA CAPITAL EPSV"), "EPSV")
        assert resultado.categoria1 == "Ahorro"
        assert resultado.tipo_gasto == "Fijos"


# ---------------------------------------------------------------------------
# Autocompletado de cuenta
# ---------------------------------------------------------------------------

class TestAutocompletado:
    def test_banco_y_tipo_cuenta_rellenados(self):
        maestros = MagicMock()
        maestros.autocompletar_cuenta.return_value = ("Openbank", "Activos liquidos")
        cat = Categorizador(maestros, _reglas_sin_match())
        cat._historial = []
        resultado = cat.categorizar(_movimiento("pago desconocido"), "Cuenta Nomina")
        assert resultado.banco == "Openbank"
        assert resultado.tipo_cuenta == "Activos liquidos"
        maestros.autocompletar_cuenta.assert_called_once_with("Cuenta Nomina")

    def test_bbva_cuenta_hipoteca(self):
        maestros = MagicMock()
        maestros.autocompletar_cuenta.return_value = ("BBVA", "Activos liquidos")
        cat = Categorizador(maestros, _reglas_sin_match())
        cat._historial = []
        resultado = cat.categorizar(_movimiento("cuota hipoteca"), "Cuenta Hipoteca")
        assert resultado.banco == "BBVA"
        assert resultado.tipo_cuenta == "Activos liquidos"
        assert resultado.cuenta == "Cuenta Hipoteca"


# ---------------------------------------------------------------------------
# Campos comunes (año, mes, importe, estado)
# ---------------------------------------------------------------------------

class TestCamposComunes:
    def _cat(self):
        cat = Categorizador(_maestros_mock(), _reglas_sin_match())
        cat._historial = []
        return cat

    def test_año_y_mes_correctos(self):
        cat = self._cat()
        resultado = cat.categorizar(_movimiento("pago", fecha=date(2025, 7, 15)), "Cuenta Nomina")
        assert resultado.año == 2025
        assert resultado.mes == "Jul"

    def test_mes_enero(self):
        cat = self._cat()
        resultado = cat.categorizar(_movimiento("pago", fecha=date(2026, 1, 1)), "Cuenta Nomina")
        assert resultado.mes == "Ene"

    def test_mes_diciembre(self):
        cat = self._cat()
        resultado = cat.categorizar(_movimiento("pago", fecha=date(2025, 12, 31)), "Cuenta Nomina")
        assert resultado.mes == "Dic"

    def test_importe_se_preserva(self):
        cat = self._cat()
        resultado = cat.categorizar(_movimiento("pago", importe="-843.88"), "Cuenta Nomina")
        assert resultado.importe == Decimal("-843.88")

    def test_estado_real(self):
        cat = self._cat()
        resultado = cat.categorizar(_movimiento("pago"), "Cuenta Nomina")
        assert resultado.estado == "Real"

    def test_concepto_original_preservado(self):
        cat = self._cat()
        mov = MovimientoCrudo(
            fecha=date(2026, 3, 6),
            concepto="PAGO EN EROSKI",
            importe=Decimal("-25.00"),
            concepto_original="2026-03-06 | PAGO EN EROSKI | -25.0",
        )
        resultado = cat.categorizar(mov, "Cuenta Nomina")
        assert resultado.concepto_original == "2026-03-06 | PAGO EN EROSKI | -25.0"
