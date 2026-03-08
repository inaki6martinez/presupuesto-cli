"""Tests del parser Openbank."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from presupuesto.parsers.openbank import ParserOpenbank

FIXTURE = Path(__file__).parent / "fixtures" / "openbank_ejemplo.xls"
XLS_REAL = Path(__file__).parent.parent / "movimientos_bancos" / "openbank_20250503_20260307.xls"


@pytest.fixture(scope="module")
def parser():
    return ParserOpenbank()


@pytest.fixture(scope="module")
def movimientos(parser):
    return parser.parsear(str(FIXTURE))


# --- Detección ---

def test_detecta_xls_openbank(parser):
    assert parser.puede_parsear(str(FIXTURE)) is True

def test_no_detecta_csv(parser, tmp_path):
    f = tmp_path / "datos.csv"
    f.write_text("Fecha,Concepto,Importe\n01/01/2025,compra,10\n", encoding="utf-8")
    assert parser.puede_parsear(str(f)) is False

def test_no_detecta_xls_sin_marcador(parser, tmp_path):
    f = tmp_path / "otro.xls"
    f.write_text("<html><body><table><tr><td>Datos</td></tr></table></body></html>",
                 encoding="iso-8859-1")
    assert parser.puede_parsear(str(f)) is False


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

def test_primer_movimiento_dreamfit(movimientos):
    m = movimientos[0]
    assert m.fecha == date(2025, 1, 5)
    assert "DREAMFIT" in m.concepto.upper()
    assert m.importe == Decimal("-40.90")

def test_segundo_movimiento_eroski(movimientos):
    m = movimientos[1]
    assert m.fecha == date(2025, 1, 10)
    assert "EROSKI" in m.concepto.upper()
    assert m.importe == Decimal("-62.40")

def test_importe_grande_con_separador_miles(movimientos):
    # Nómina: '2.308,10' debe parsearse como 2308.10
    nomina = next(m for m in movimientos if m.importe > 0)
    assert nomina.importe == Decimal("2308.10")

def test_importe_negativo_grande(movimientos):
    # Transferencia reforma: '-1.200,00' → -1200.00
    reforma = next(m for m in movimientos if m.importe == Decimal("-1200.00"))
    assert reforma is not None
    assert reforma.fecha == date(2025, 2, 14)

def test_gastos_son_negativos(movimientos):
    gastos = [m for m in movimientos if m.importe < 0]
    assert len(gastos) == 7

def test_ingresos_son_positivos(movimientos):
    ingresos = [m for m in movimientos if m.importe > 0]
    assert len(ingresos) == 1

def test_concepto_sin_espacios_extra(movimientos):
    for m in movimientos:
        assert "  " not in m.concepto  # sin dobles espacios

def test_concepto_original_contiene_fecha(movimientos):
    for m in movimientos:
        assert "/" in m.concepto_original  # la fecha DD/MM/YYYY está en el original


# --- Archivo real ---

def test_parsea_archivo_real(parser):
    if not XLS_REAL.exists():
        pytest.skip("Archivo real no disponible")
    movs = parser.parsear(str(XLS_REAL))
    assert len(movs) > 0

def test_archivo_real_tipos_correctos(parser):
    if not XLS_REAL.exists():
        pytest.skip("Archivo real no disponible")
    movs = parser.parsear(str(XLS_REAL))
    for m in movs:
        assert isinstance(m.fecha, date)
        assert isinstance(m.importe, Decimal)
        assert m.concepto.strip() != ""

def test_archivo_real_importes_europeos(parser):
    """Los importes grandes (con punto de miles) deben parsearse correctamente."""
    if not XLS_REAL.exists():
        pytest.skip("Archivo real no disponible")
    movs = parser.parsear(str(XLS_REAL))
    nominas = [m for m in movs if m.importe > Decimal("2000")]
    assert len(nominas) > 0, "Esperaba al menos una nómina > 2000€"
    for m in nominas:
        # No deben haberse partido en cifras pequeñas por mal parseo del separador
        assert m.importe > Decimal("2000")

def test_archivo_real_detectado(parser):
    if not XLS_REAL.exists():
        pytest.skip("Archivo real no disponible")
    assert parser.puede_parsear(str(XLS_REAL)) is True
