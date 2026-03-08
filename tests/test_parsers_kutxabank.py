"""Tests del parser Kutxabank."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from presupuesto.parsers.kutxabank import ParserKutxabank

FIXTURE = Path(__file__).parent / "fixtures" / "kutxabank_ejemplo.xls"
XLS_REAL = Path(__file__).parent.parent / "movimientos_bancos" / "kutxabank_20250503_20260307.xls"


@pytest.fixture(scope="module")
def parser():
    return ParserKutxabank()


@pytest.fixture(scope="module")
def movimientos(parser):
    return parser.parsear(str(FIXTURE))


# --- Detección ---

def test_detecta_xls_kutxabank(parser):
    assert parser.puede_parsear(str(FIXTURE)) is True

def test_no_detecta_csv(parser, tmp_path):
    f = tmp_path / "datos.csv"
    f.write_text("fecha;concepto;importe\n06/05/2025;TRANSF;100\n", encoding="utf-8")
    assert parser.puede_parsear(str(f)) is False

def test_no_detecta_html_xls(parser, tmp_path):
    """El HTML disfrazado de XLS (Openbank) no debe ser detectado."""
    f = tmp_path / "openbank.xls"
    f.write_text("<html><body><table><tr><td>fecha operacion</td></tr></table></body></html>",
                 encoding="iso-8859-1")
    assert parser.puede_parsear(str(f)) is False

def test_no_detecta_xls_sin_cabeceras(parser, tmp_path):
    """Un XLS binario sin las cabeceras de Kutxabank no debe detectarse."""
    import xlwt
    wb = xlwt.Workbook()
    ws = wb.add_sheet("Hoja1")
    ws.write(0, 0, "Datos varios")
    ruta = tmp_path / "otro.xls"
    wb.save(str(ruta))
    assert parser.puede_parsear(str(ruta)) is False


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

def test_primer_movimiento_transferencia(movimientos):
    m = movimientos[0]
    assert m.fecha == date(2025, 5, 6)
    assert m.importe == Decimal("141.00")
    assert "TRANSF" in m.concepto.upper()

def test_segundo_movimiento_gasto(movimientos):
    m = movimientos[1]
    assert m.fecha == date(2025, 5, 6)
    assert m.importe == Decimal("-141.50")
    assert "RECIBO" in m.concepto.upper()

def test_importe_cero_incluido(movimientos):
    """Los movimientos de liquidación de intereses tienen importe 0 y deben incluirse."""
    ceros = [m for m in movimientos if m.importe == Decimal("0.00")]
    assert len(ceros) == 1
    assert "INT" in ceros[0].concepto.upper()

def test_importe_decimal(movimientos):
    """Importes con decimales deben conservar la precisión."""
    tarjeta = next(m for m in movimientos if "TARJ" in m.concepto.upper())
    assert tarjeta.importe == Decimal("-15.00")

def test_importe_decimal_no_redondea(movimientos):
    """El importe -71.49 no debe redondearse a -71.5 ni -71."""
    m = next(m for m in movimientos if m.importe == Decimal("-71.49"))
    assert m is not None

def test_concepto_sin_espacios_extra(movimientos):
    for m in movimientos:
        assert "  " not in m.concepto

def test_gastos_negativos_ingresos_positivos(movimientos):
    assert all(m.importe < 0 for m in movimientos if "RECIBO" in m.concepto.upper()
               or "TARJ" in m.concepto.upper() or "COMISION" in m.concepto.upper())
    assert all(m.importe > 0 for m in movimientos if "TRANSF." in m.concepto.upper())

def test_concepto_original_contiene_fecha(movimientos):
    for m in movimientos:
        assert "/" in m.concepto_original


# --- Archivo real ---

def test_parsea_archivo_real(parser):
    if not XLS_REAL.exists():
        pytest.skip("Archivo real no disponible")
    movs = parser.parsear(str(XLS_REAL))
    assert len(movs) == 22

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

def test_archivo_real_precision_decimales(parser):
    """Verificar que los importes float de xlrd se convierten con precisión correcta."""
    if not XLS_REAL.exists():
        pytest.skip("Archivo real no disponible")
    movs = parser.parsear(str(XLS_REAL))
    # El archivo real tiene -71.49 y -25.04 que son propensos a errores float
    importes = {m.importe for m in movs}
    assert Decimal("-71.49") in importes
    assert Decimal("-25.04") in importes
