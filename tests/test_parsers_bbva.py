"""Tests del parser BBVA."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from presupuesto.parsers.bbva import ParserBBVA

FIXTURE = Path(__file__).parent / "fixtures" / "bbva_ejemplo.xlsx"
XLSX_REAL    = Path(__file__).parent.parent / "movimientos_bancos" / "bbva_20250503_20260307.xlsx"
XLSX_REAL_ES = Path(__file__).parent.parent / "movimientos_bancos" / "bbva_20250503_20260309.xlsx"


@pytest.fixture(scope="module")
def parser():
    return ParserBBVA()


@pytest.fixture(scope="module")
def movimientos(parser):
    return parser.parsear(str(FIXTURE))


# --- Detección ---

def test_detecta_xlsx_bbva(parser):
    assert parser.puede_parsear(str(FIXTURE)) is True

def test_no_detecta_csv(parser, tmp_path):
    f = tmp_path / "datos.csv"
    f.write_text("Fecha,Concepto,Importe\n", encoding="utf-8")
    assert parser.puede_parsear(str(f)) is False

def test_no_detecta_xlsx_sin_cabeceras(parser, tmp_path):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws["A1"] = "Datos varios"
    ruta = tmp_path / "otro.xlsx"
    wb.save(str(ruta))
    assert parser.puede_parsear(str(ruta)) is False

def test_no_detecta_xls(parser, tmp_path):
    f = tmp_path / "datos.xls"
    f.write_bytes(b"\xd0\xcf\x11\xe0dummy")
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

def test_tarjeta_usa_item(movimientos):
    """Para pagos con tarjeta, Item tiene el comercio (Netflix.com)."""
    m = movimientos[0]
    assert m.fecha == date(2026, 3, 3)
    assert m.importe == Decimal("-13.99")
    assert "Netflix" in m.concepto
    # Transaction "Card payment" no debe aparecer
    assert "card payment" not in m.concepto.lower()

def test_transferencia_completada_usa_transaction(movimientos):
    """Transfer completed: Item es genérico, Transaction tiene el concepto real."""
    m = movimientos[1]
    assert m.importe == Decimal("-60.00")
    assert "transfer completed" not in m.concepto.lower()
    assert "comunidad" in m.concepto.lower()

def test_service_debit_usa_comments(movimientos):
    """Service company debit: Comments tiene el proveedor real (Aguas Municipales)."""
    m = movimientos[2]
    assert m.importe == Decimal("-20.55")
    assert "service company" not in m.concepto.lower()
    assert "aguas municipales" in m.concepto.lower()
    # El prefijo "N 123456789 " debe estar eliminado
    assert not m.concepto.startswith("N ")

def test_fee_loan_mantiene_item(movimientos):
    """Fee for loan: no tiene Transaction ni Comments útiles, mantiene Item."""
    m = movimientos[3]
    assert m.importe == Decimal("-843.88")
    assert "fee" in m.concepto.lower()

def test_comercio_tarjeta_sin_tipo(movimientos):
    """Bazar chinatown: Item es el comercio, Transaction 'Card payment' se descarta."""
    m = movimientos[4]
    assert m.importe == Decimal("-42.44")
    assert "Bazar chinatown" in m.concepto
    assert "card payment" not in m.concepto.lower()

def test_transferencia_a_persona(movimientos):
    """Transfer completed a persona: usa Transaction con el nombre del destinatario."""
    m = movimientos[5]
    assert m.importe == Decimal("-100.00")
    assert "alba" in m.concepto.lower()

def test_transferencia_recibida(movimientos):
    """Transfer received: usa Transaction con el concepto."""
    m = movimientos[6]
    assert m.importe == Decimal("600.00")
    assert "Casa" in m.concepto

def test_domiciliacion_con_debit_no(movimientos):
    """Vodafone debit con 'Debit no XXXX' en Transaction: Transaction es genérica, usa Item."""
    m = movimientos[7]
    assert m.importe == Decimal("-29.95")
    assert "Vodafone" in m.concepto
    assert "debit no" not in m.concepto.lower()

def test_fechas_formato_mmddyyyy(movimientos):
    """BBVA usa MM/DD/YYYY; verificar que las fechas no se invierten mes/día."""
    m = movimientos[0]  # '03/03/2026' → 3 de marzo
    assert m.fecha == date(2026, 3, 3)
    m = movimientos[3]  # '02/28/2026' → 28 de febrero
    assert m.fecha == date(2026, 2, 28)

def test_concepto_original_contiene_item(movimientos):
    for m in movimientos:
        assert "|" in m.concepto_original


# --- Archivo real ---

def test_parsea_archivo_real(parser):
    if not XLSX_REAL.exists():
        pytest.skip("Archivo real no disponible")
    movs = parser.parsear(str(XLSX_REAL))
    assert len(movs) == 145

def test_archivo_real_detectado(parser):
    if not XLSX_REAL.exists():
        pytest.skip("Archivo real no disponible")
    assert parser.puede_parsear(str(XLSX_REAL)) is True

def test_archivo_real_service_debit_usa_comments(parser):
    """Las domiciliaciones de Aguas Municipales deben mostrar el nombre real."""
    if not XLSX_REAL.exists():
        pytest.skip("Archivo real no disponible")
    movs = parser.parsear(str(XLSX_REAL))
    aguas = [m for m in movs if "aguas municipales" in m.concepto.lower()]
    assert len(aguas) > 0
    for m in aguas:
        assert not m.concepto.lower().startswith("service company")

def test_archivo_real_netflix_como_comercio(parser):
    """Netflix debe aparecer como concepto, no como 'Card payment'."""
    if not XLSX_REAL.exists():
        pytest.skip("Archivo real no disponible")
    movs = parser.parsear(str(XLSX_REAL))
    netflix = [m for m in movs if "netflix" in m.concepto.lower()]
    assert len(netflix) > 0

def test_archivo_real_precision_decimales(parser):
    if not XLSX_REAL.exists():
        pytest.skip("Archivo real no disponible")
    movs = parser.parsear(str(XLSX_REAL))
    assert Decimal("-13.99") in {m.importe for m in movs}
    assert Decimal("-843.88") in {m.importe for m in movs}


# --- Archivo real en español ---

def test_es_detectado(parser):
    if not XLSX_REAL_ES.exists():
        pytest.skip("Archivo real ES no disponible")
    assert parser.puede_parsear(str(XLSX_REAL_ES)) is True

def test_es_parsea_145_movimientos(parser):
    if not XLSX_REAL_ES.exists():
        pytest.skip("Archivo real ES no disponible")
    movs = parser.parsear(str(XLSX_REAL_ES))
    assert len(movs) == 145

def test_es_fechas_formato_ddmmyyyy(parser):
    """Formato español DD/MM/YYYY: primera fila es 03/03/2026 → 3 de marzo."""
    if not XLSX_REAL_ES.exists():
        pytest.skip("Archivo real ES no disponible")
    movs = parser.parsear(str(XLSX_REAL_ES))
    assert movs[0].fecha == date(2026, 3, 3)

def test_es_tarjeta_usa_concepto(parser):
    """Pago con tarjeta → Transaction genérica, usa Concepto (comercio)."""
    if not XLSX_REAL_ES.exists():
        pytest.skip("Archivo real ES no disponible")
    movs = parser.parsear(str(XLSX_REAL_ES))
    netflix = movs[0]
    assert "Netflix" in netflix.concepto
    assert "pago con tarjeta" not in netflix.concepto.lower()

def test_es_transferencia_realizada_usa_movimiento(parser):
    """Transferencia realizada → Item genérico, usa Movimiento."""
    if not XLSX_REAL_ES.exists():
        pytest.skip("Archivo real ES no disponible")
    movs = parser.parsear(str(XLSX_REAL_ES))
    transf = movs[1]
    assert transf.importe == Decimal("-60.00")
    assert "transferencia realizada" not in transf.concepto.lower()
    assert "comunidad" in transf.concepto.lower()

def test_es_adeudo_usa_observaciones(parser):
    """Adeudo de empresa de servicios → usa Observaciones (sin prefijo N XXXX)."""
    if not XLSX_REAL_ES.exists():
        pytest.skip("Archivo real ES no disponible")
    movs = parser.parsear(str(XLSX_REAL_ES))
    adeudo = movs[2]
    assert adeudo.importe == Decimal("-20.55")
    assert "aguas municipales" in adeudo.concepto.lower()
    assert not adeudo.concepto.startswith("N ")
    assert "adeudo de empresa" not in adeudo.concepto.lower()

def test_es_cargo_sin_movimiento_usa_concepto(parser):
    """Cargo por amortizacion sin Movimiento → usa Concepto."""
    if not XLSX_REAL_ES.exists():
        pytest.skip("Archivo real ES no disponible")
    movs = parser.parsear(str(XLSX_REAL_ES))
    cargo = movs[3]
    assert cargo.importe == Decimal("-843.88")
    assert "amortizacion" in cargo.concepto.lower()

def test_es_precision_decimales(parser):
    if not XLSX_REAL_ES.exists():
        pytest.skip("Archivo real ES no disponible")
    movs = parser.parsear(str(XLSX_REAL_ES))
    importes = {m.importe for m in movs}
    assert Decimal("-13.99") in importes
    assert Decimal("-843.88") in importes
    assert Decimal("-20.55") in importes
