"""Tests del parser N26."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from presupuesto.parsers.n26 import ParserN26

FIXTURE = Path(__file__).parent / "fixtures" / "n26_ejemplo.csv"
CSV_REAL = Path(__file__).parent.parent / "movimientos_bancos" / "n26_20250503_20260307.csv"


@pytest.fixture(scope="module")
def parser():
    return ParserN26()


@pytest.fixture(scope="module")
def movimientos(parser):
    return parser.parsear(str(FIXTURE))


# --- Detección ---

def test_detecta_csv_n26(parser):
    assert parser.puede_parsear(str(FIXTURE)) is True

def test_no_detecta_archivo_no_csv(parser, tmp_path):
    f = tmp_path / "datos.xlsx"
    f.write_bytes(b"dummy")
    assert parser.puede_parsear(str(f)) is False

def test_no_detecta_csv_sin_cabeceras_n26(parser, tmp_path):
    f = tmp_path / "otro.csv"
    f.write_text("Fecha,Concepto,Importe\n2025-01-01,compra,10\n", encoding="utf-8")
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

def test_primer_movimiento_eroski(movimientos):
    m = movimientos[0]
    assert m.fecha == date(2025, 1, 3)
    assert "EROSKI" in m.concepto.upper()
    assert m.importe == Decimal("-62.4")

def test_segundo_movimiento_dreamfit(movimientos):
    m = movimientos[1]
    assert m.fecha == date(2025, 1, 7)
    assert "DREAMFIT" in m.concepto.upper()
    assert m.importe == Decimal("-3")

def test_ingreso_positivo(movimientos):
    # Movimiento 3: transferencia de 200€ (ingreso)
    m = movimientos[2]
    assert m.importe == Decimal("200.00")
    assert m.importe > 0

def test_nombre_poco_descriptivo_usa_referencia(movimientos):
    # Movimiento 6: "Cuenta de Ahorro" → debe usar "Transferencia ahorro enero"
    m = movimientos[5]
    assert "transferencia ahorro" in m.concepto.lower()

def test_n26_con_salto_de_linea_usa_referencia(movimientos):
    # Movimiento 5: Partner Name = "N26\n" → debe usar Payment Reference
    m = movimientos[4]
    assert "membresía" in m.concepto.lower() or "metal" in m.concepto.lower()
    assert m.importe == Decimal("-16.9")

def test_concepto_sin_saltos_de_linea(movimientos):
    for m in movimientos:
        assert "\n" not in m.concepto
        assert "\r" not in m.concepto

def test_concepto_original_no_vacio(movimientos):
    for m in movimientos:
        assert m.concepto_original.strip() != ""

def test_netflix_importe_decimal(movimientos):
    m = movimientos[8]
    assert "NETFLIX" in m.concepto.upper()
    assert m.importe == Decimal("-17.99")

def test_lowi_ultimo(movimientos):
    m = movimientos[9]
    assert "LOWI" in m.concepto.upper()
    assert m.importe == Decimal("-9.99")


# --- CSV real ---

def test_parsea_csv_real(parser):
    if not CSV_REAL.exists():
        pytest.skip("CSV real no disponible")
    movs = parser.parsear(str(CSV_REAL))
    assert len(movs) > 0
    # Verificar que todos tienen fecha, concepto e importe válidos
    for m in movs:
        assert m.fecha is not None
        assert m.concepto.strip() != ""
        assert isinstance(m.importe, Decimal)

def test_csv_real_sin_saltos_de_linea_en_concepto(parser):
    if not CSV_REAL.exists():
        pytest.skip("CSV real no disponible")
    movs = parser.parsear(str(CSV_REAL))
    for m in movs:
        assert "\n" not in m.concepto, f"Concepto con salto de línea: {repr(m.concepto)}"

def test_csv_real_n26_metal_usa_referencia(parser):
    """Las cuotas de N26 Metal tienen Partner Name='N26\n'; el concepto debe venir de Payment Reference."""
    if not CSV_REAL.exists():
        pytest.skip("CSV real no disponible")
    movs = parser.parsear(str(CSV_REAL))
    cuotas = [m for m in movs if m.importe == Decimal("-16.9")]
    assert len(cuotas) > 0
    for m in cuotas:
        assert "metal" in m.concepto.lower() or "membresía" in m.concepto.lower(), (
            f"Concepto inesperado para cuota N26: {repr(m.concepto)}"
        )
