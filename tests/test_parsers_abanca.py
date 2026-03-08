"""Tests del parser Abanca."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from presupuesto.parsers.abanca import ParserAbanca

FIXTURE = Path(__file__).parent / "fixtures" / "abanca_ejemplo.csv"
CSV_REAL = Path(__file__).parent.parent / "movimientos_bancos" / "abanca.csv"


@pytest.fixture(scope="module")
def parser():
    return ParserAbanca()


@pytest.fixture(scope="module")
def movimientos(parser):
    return parser.parsear(str(FIXTURE))


# --- Detección ---

def test_detecta_csv_abanca(parser):
    assert parser.puede_parsear(str(FIXTURE)) is True

def test_no_detecta_xls(parser, tmp_path):
    f = tmp_path / "datos.xls"
    f.write_bytes(b"<html></html>")
    assert parser.puede_parsear(str(f)) is False

def test_no_detecta_csv_sin_cabeceras_abanca(parser, tmp_path):
    f = tmp_path / "otro.csv"
    f.write_text("Fecha,Concepto,Importe\n01/01/2025,compra,10\n", encoding="utf-8")
    assert parser.puede_parsear(str(f)) is False

def test_no_detecta_csv_n26(parser, tmp_path):
    f = tmp_path / "n26.csv"
    f.write_text(
        '"Booking Date","Value Date","Partner Name","Amount (EUR)"\n'
        '2025-01-01,2025-01-01,EROSKI,-10\n',
        encoding="utf-8",
    )
    assert parser.puede_parsear(str(f)) is False


# --- Parseo del fixture ---

def test_parsea_10_movimientos(movimientos):
    assert len(movimientos) == 10

def test_tipos_correctos(movimientos):
    from presupuesto.parsers.base import MovimientoCrudo
    for m in movimientos:
        assert isinstance(m.fecha, date)
        assert isinstance(m.importe, Decimal)
        assert isinstance(m.concepto, str)
        assert isinstance(m.concepto_original, str)

def test_apertura_cuenta(movimientos):
    m = movimientos[0]
    assert m.fecha == date(2025, 10, 2)
    assert m.importe == Decimal("0.00")
    assert "APERTURA" in m.concepto.upper()

def test_nomina_ziv_usa_concepto_ampliado(movimientos):
    """La nómina de ZIV tiene un Concepto largo con NIF; debe usar el Concepto ampliado."""
    m = movimientos[1]
    assert m.fecha == date(2025, 10, 31)
    assert m.importe == Decimal("2308.10")
    assert "ZIV" in m.concepto.upper()
    assert "NOMINA" in m.concepto.upper()
    # No debe contener el NIF
    assert "72744098C" not in m.concepto

def test_concepto_simple_se_mantiene(movimientos):
    """Un concepto manual como 'ALQUILER' se devuelve tal cual."""
    m = movimientos[2]
    assert m.concepto.upper() == "ALQUILER"

def test_bizum_ingreso_usa_concepto(movimientos):
    """Los ingresos Bizum tienen un Concepto legible; el ampliado tiene referencia, no se usa."""
    m = movimientos[3]
    assert m.importe == Decimal("124.00")
    assert "BIZUM" in m.concepto.upper()
    assert "platos" in m.concepto.lower()
    # La referencia #BIZUM_BC2C no debe aparecer en el concepto
    assert "#BIZUM" not in m.concepto

def test_tarjeta_eroski_limpia_prefijo(movimientos):
    """Las compras con tarjeta empiezan con '767003185863'; debe extraerse el comercio."""
    m = movimientos[4]
    assert m.importe == Decimal("-21.45")
    assert "767003185863" not in m.concepto
    assert "EROSKI" in m.concepto.upper()
    # No debe contener la parte de ubicación
    assert "VITORIA" not in m.concepto

def test_bizum_pago_usa_concepto(movimientos):
    m = movimientos[5]
    assert m.importe == Decimal("-65.00")
    assert "BIZUM" in m.concepto.upper()
    assert "#BIZUM" not in m.concepto

def test_tarjeta_paypal_limpia_sufijo(movimientos):
    """PayPal via tarjeta: limpiar prefijo numérico y sufijo."""
    m = movimientos[6]
    assert "767003185863" not in m.concepto
    assert "PAYPAL" in m.concepto.upper() or "LEROYMERLIN" in m.concepto.upper()

def test_paga_extra_navidad(movimientos):
    m = movimientos[7]
    assert m.fecha == date(2025, 12, 19)
    assert m.importe == Decimal("2520.38")
    assert "NAVIDAD" in m.concepto.upper()

def test_transferencia_con_concepto_ampliado(movimientos):
    """Transferencia entre personas: ampliado tiene el detalle real."""
    m = movimientos[9]
    assert m.importe == Decimal("139.00")
    assert "IKEA" in m.concepto.upper()

def test_concepto_sin_referencia_bizum(movimientos):
    """Ningún concepto debe contener referencias #BIZUM_BC2C o #BIZUM_BC2E."""
    for m in movimientos:
        assert "#BIZUM" not in m.concepto

def test_concepto_original_contiene_concepto_raw(movimientos):
    for m in movimientos:
        assert "|" in m.concepto_original


# --- Archivo real ---

def test_parsea_archivo_real(parser):
    if not CSV_REAL.exists():
        pytest.skip("CSV real no disponible")
    movs = parser.parsear(str(CSV_REAL))
    assert len(movs) > 0

def test_archivo_real_detectado(parser):
    if not CSV_REAL.exists():
        pytest.skip("CSV real no disponible")
    assert parser.puede_parsear(str(CSV_REAL)) is True

def test_archivo_real_nominas_usan_ampliado(parser):
    """Las nóminas de ZIV deben mostrar 'ZIV NOMINA ...' no el NIF."""
    if not CSV_REAL.exists():
        pytest.skip("CSV real no disponible")
    movs = parser.parsear(str(CSV_REAL))
    nominas = [m for m in movs if "72744098C" in m.concepto_original]
    assert len(nominas) > 0
    for m in nominas:
        assert "72744098C" not in m.concepto
        assert "ZIV" in m.concepto.upper()

def test_archivo_real_sin_referencias_bizum(parser):
    if not CSV_REAL.exists():
        pytest.skip("CSV real no disponible")
    movs = parser.parsear(str(CSV_REAL))
    for m in movs:
        assert "#BIZUM" not in m.concepto

def test_archivo_real_tarjetas_sin_prefijo(parser):
    if not CSV_REAL.exists():
        pytest.skip("CSV real no disponible")
    movs = parser.parsear(str(CSV_REAL))
    for m in movs:
        assert "767003185863" not in m.concepto
