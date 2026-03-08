"""Tests del parser ING."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from presupuesto.parsers.ing import ParserING

FIXTURE  = Path(__file__).parent / "fixtures" / "ing_ejemplo.xls"
XLS_REAL = Path(__file__).parent.parent / "movimientos_bancos" / "ing.xls"


@pytest.fixture(scope="module")
def parser():
    return ParserING()


@pytest.fixture(scope="module")
def movimientos(parser):
    return parser.parsear(str(FIXTURE))


# --- Detección ---

def test_detecta_xls_ing(parser):
    assert parser.puede_parsear(str(FIXTURE)) is True

def test_no_detecta_csv(parser, tmp_path):
    f = tmp_path / "datos.csv"
    f.write_text("F. VALOR;DESCRIPCIÓN;IMPORTE (€)\n", encoding="utf-8")
    assert parser.puede_parsear(str(f)) is False

def test_no_detecta_html_xls(parser, tmp_path):
    f = tmp_path / "openbank.xls"
    f.write_text("<html><body>fecha operacion</body></html>", encoding="iso-8859-1")
    assert parser.puede_parsear(str(f)) is False

def test_no_detecta_kutxabank(parser):
    kutxa = Path(__file__).parent / "fixtures" / "kutxabank_ejemplo.xls"
    if not kutxa.exists():
        pytest.skip("Fixture de Kutxabank no disponible")
    assert parser.puede_parsear(str(kutxa)) is False

def test_kutxabank_no_detecta_ing():
    from presupuesto.parsers.kutxabank import ParserKutxabank
    pk = ParserKutxabank()
    assert pk.puede_parsear(str(FIXTURE)) is False


# --- Parseo del fixture ---

def test_parsea_8_movimientos(movimientos):
    assert len(movimientos) == 8

def test_tipos_correctos(movimientos):
    from presupuesto.parsers.base import MovimientoCrudo
    for m in movimientos:
        assert isinstance(m.fecha, date)
        assert isinstance(m.importe, Decimal)
        assert isinstance(m.concepto, str)
        assert isinstance(m.concepto_original, str)

def test_fecha_desde_serial_excel(movimientos):
    """El serial 46087 debe convertirse a 2026-03-06."""
    assert movimientos[0].fecha == date(2026, 3, 6)
    assert movimientos[1].fecha == date(2026, 3, 6)

def test_pago_tarjeta_eroski(movimientos):
    m = movimientos[0]
    assert m.importe == Decimal("-25.04")
    assert "EROSKI" in m.concepto.upper()
    assert "Pago en" in m.concepto

def test_recibo_eroski(movimientos):
    m = movimientos[1]
    assert m.importe == Decimal("-4.99")
    assert "Recibo" in m.concepto
    assert "EROSKI" in m.concepto.upper()

def test_transferencia_recibida(movimientos):
    m = movimientos[2]
    assert m.fecha == date(2026, 3, 3)
    assert m.importe == Decimal("70.00")
    assert m.importe > 0
    assert "Transferencia recibida" in m.concepto

def test_transferencia_emitida(movimientos):
    m = movimientos[3]
    assert m.fecha == date(2026, 2, 8)
    assert m.importe == Decimal("-60.00")
    assert "Transferencia emitida" in m.concepto or "emitida" in m.concepto.lower()

def test_devolucion_tarjeta(movimientos):
    m = movimientos[4]
    assert m.fecha == date(2026, 1, 2)
    assert m.importe == Decimal("14.99")
    assert m.importe > 0
    assert "Devolución" in m.concepto or "devolucion" in m.concepto.lower()

def test_gastos_negativos(movimientos):
    gastos = [m for m in movimientos if m.importe < 0]
    assert len(gastos) == 6

def test_ingresos_positivos(movimientos):
    ingresos = [m for m in movimientos if m.importe > 0]
    assert len(ingresos) == 2

def test_concepto_sin_espacios_extra(movimientos):
    for m in movimientos:
        assert "  " not in m.concepto

def test_concepto_original_contiene_fecha(movimientos):
    for m in movimientos:
        assert str(movimientos[0].fecha)[:4] in m.concepto_original or "|" in m.concepto_original


# --- Archivo real ---

def test_parsea_archivo_real(parser):
    if not XLS_REAL.exists():
        pytest.skip("Archivo real no disponible")
    movs = parser.parsear(str(XLS_REAL))
    assert len(movs) == 400

def test_archivo_real_detectado(parser):
    if not XLS_REAL.exists():
        pytest.skip("Archivo real no disponible")
    assert parser.puede_parsear(str(XLS_REAL)) is True

def test_archivo_real_tipos_correctos(parser):
    if not XLS_REAL.exists():
        pytest.skip("Archivo real no disponible")
    movs = parser.parsear(str(XLS_REAL))
    for m in movs:
        assert isinstance(m.fecha, date)
        assert isinstance(m.importe, Decimal)
        assert m.concepto.strip() != ""

def test_archivo_real_fechas_validas(parser):
    if not XLS_REAL.exists():
        pytest.skip("Archivo real no disponible")
    movs = parser.parsear(str(XLS_REAL))
    años = {m.fecha.year for m in movs}
    assert años.issubset({2025, 2026})

def test_archivo_real_precision_decimales(parser):
    if not XLS_REAL.exists():
        pytest.skip("Archivo real no disponible")
    movs = parser.parsear(str(XLS_REAL))
    importes = {m.importe for m in movs}
    assert Decimal("-25.04") in importes
    assert Decimal("-4.99") in importes
