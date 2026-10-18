"""Unit tests for SP-API report ingestion parsers."""

from datetime import datetime, timezone
from decimal import Decimal
import io
from pathlib import Path
import pytest

from fba_audit.models.enums import Disposition, EventType
from fba_audit.parsers import (
    ParserError,
    RowParsingError,
    SchemaValidationError,
    parse_customer_returns_report,
    parse_estimated_fees_report,
    parse_ledger_report,
    parse_reimbursements_report,
)


@pytest.fixture
def fixtures_dir() -> Path:
    """Fixture returning path to test fixtures directory."""
    return Path(__file__).resolve().parent.parent / "fixtures"


# ---------------------------------------------------------------------------
# Extraction Accuracy & Field Completeness Tests
# ---------------------------------------------------------------------------

def test_parse_ledger_report_success(fixtures_dir: Path):
    """Ingests ledger_detail_sample.tsv and validates extraction fidelity."""
    path = fixtures_dir / "ledger_detail_sample.tsv"
    records = parse_ledger_report(path)
    assert len(records) == 14

    # First record check
    first = records[0]
    assert first.event_date_time == datetime(2026, 8, 1, 8, 30, tzinfo=timezone.utc)
    assert first.fnsku == "X002ABC101"
    assert first.asin == "B09ABCDEFG"
    assert first.msku == "SKU-WIRELESS-EARBUDS"
    assert first.event_type == EventType.Receipts or first.event_type == "Receipts"
    assert first.quantity == 100
    assert first.fulfillment_center_id == "DFW6"
    assert first.disposition == Disposition.SELLABLE
    assert first.reconciled_quantity == 100
    assert first.unreconciled_quantity == 0

    # Misplaced adjustment check (line 5 in data: -3 misplaced)
    misplaced = next(r for r in records if r.reference_id == "ADJ90812341")
    assert misplaced.quantity == -3
    assert misplaced.reason == "Inventory misplaced"
    assert misplaced.unreconciled_quantity == -3


def test_parse_customer_returns_report_success(fixtures_dir: Path):
    """Ingests customer_returns_sample.tsv and validates disposition and order ID extraction."""
    path = fixtures_dir / "customer_returns_sample.tsv"
    records = parse_customer_returns_report(path)
    assert len(records) == 4

    first = records[0]
    assert first.amazon_order_id == "114-8761234-9876543"
    assert first.order_id == "114-8761234-9876543"
    assert first.detailed_disposition == Disposition.SELLABLE
    assert first.reason == "UNWANTED_ITEM"
    assert first.license_plate_number == "LPNRR102938475"

    carrier_damaged = next(r for r in records if r.amazon_order_id == "112-5432109-8765432")
    assert carrier_damaged.detailed_disposition == Disposition.CARRIER_DAMAGED
    assert carrier_damaged.customer_comments == "Box was crushed upon arrival"


def test_parse_reimbursements_report_success(fixtures_dir: Path):
    """Ingests reimbursements_sample.tsv and validates cash, inventory, and clawback amounts."""
    path = fixtures_dir / "reimbursements_sample.tsv"
    records = parse_reimbursements_report(path)
    assert len(records) == 4

    # Physical inventory restitution (0 Cash, 1 inventory)
    inv_rec = next(r for r in records if r.reimbursement_id == "1092837463")
    assert inv_rec.quantity_reimbursed_cash == 0
    assert inv_rec.quantity_reimbursed_inventory == 1
    assert inv_rec.quantity_reimbursed_total == 1
    assert inv_rec.amount_total == Decimal("0.00")

    # Clawback record (negative amount)
    clawback = next(r for r in records if r.reimbursement_id == "1092837464")
    assert clawback.amount_total == Decimal("-12.50")
    assert clawback.quantity_reimbursed_cash == -1


def test_parse_estimated_fees_report_success(fixtures_dir: Path):
    """Ingests estimated_fees_sample.tsv and validates dimensions and fee rates."""
    path = fixtures_dir / "estimated_fees_sample.tsv"
    records = parse_estimated_fees_report(path)
    assert len(records) == 4

    first = records[0]
    assert first.longest_side == Decimal("6.50")
    assert first.unit_of_dimension == "inches"
    assert first.item_package_weight == Decimal("0.450")
    assert first.expected_fulfillment_fee == Decimal("4.87")
    assert first.expected_fulfillment_fee_per_unit == Decimal("4.87")


# ---------------------------------------------------------------------------
# Zero-Float & Decimal Precision Invariant Tests
# ---------------------------------------------------------------------------

def test_parsers_decimal_precision(fixtures_dir: Path):
    """Verifies that all monetary and dimensional fields are Decimal instances with zero float artifacts."""
    reimbs = parse_reimbursements_report(fixtures_dir / "reimbursements_sample.tsv")
    for r in reimbs:
        assert isinstance(r.amount_per_unit, Decimal)
        assert not isinstance(r.amount_per_unit, float)
        assert isinstance(r.amount_total, Decimal)
        assert not isinstance(r.amount_total, float)

    fees = parse_estimated_fees_report(fixtures_dir / "estimated_fees_sample.tsv")
    for f in fees:
        assert isinstance(f.your_price, Decimal)
        assert not isinstance(f.your_price, float)
        assert isinstance(f.longest_side, Decimal)
        assert not isinstance(f.longest_side, float)
        assert isinstance(f.item_package_weight, Decimal)
        assert not isinstance(f.item_package_weight, float)
        assert isinstance(f.expected_fulfillment_fee, Decimal)
        assert not isinstance(f.expected_fulfillment_fee, float)


# ---------------------------------------------------------------------------
# Header Normalization & Dialect Resiliency Tests
# ---------------------------------------------------------------------------

def test_header_alias_normalization():
    """Verifies that aliased headers like order-id vs amazon-order-id and currency-unit are parsed seamlessly."""
    # Returns with order-id vs amazon-order-id
    tsv_content = (
        "return-date\torder-id\tsku\tasin\tfnsku\tquantity\tfulfillment-center-id\tdetailed-disposition\treason\n"
        "2026-08-20T14:10:05Z\tORD-101\tSKU1\tB001\tX001\t1\tPHX3\tSELLABLE\tDEFECTIVE\n"
    )
    records = parse_customer_returns_report(tsv_content)
    assert len(records) == 1
    assert records[0].amazon_order_id == "ORD-101"

    # Reimbursements with currency-unit vs currency
    tsv_reimb = (
        "approval-date\treimbursement-id\tfnsku\tamount-per-unit\tamount-total\tcurrency-unit\n"
        "2026-08-25T11:45:00Z\tR999\tX001\t19.99\t19.99\tUSD\n"
    )
    reimbs = parse_reimbursements_report(tsv_reimb)
    assert len(reimbs) == 1
    assert reimbs[0].currency == "USD"


def test_dialect_variations_and_bom():
    """Verifies handling of UTF-8 BOM, Windows CRLF, and CSV comma-separated content."""
    # 1. UTF-8 BOM with Windows CRLF
    bom_content = (
        "\ufeffDate and Time\tFNSKU\tQuantity\tEvent Type\r\n"
        "2026-08-01T08:30:00Z\tX001\t10\tReceipts\r\n"
    )
    records = parse_ledger_report(bom_content)
    assert len(records) == 1
    assert records[0].fnsku == "X001"
    assert records[0].quantity == 10

    # 2. Comma-separated CSV format
    csv_content = (
        "Date and Time,FNSKU,Quantity,Event Type\n"
        "2026-08-01T08:30:00Z,X002,5,Receipts\n"
    )
    records_csv = parse_ledger_report(csv_content)
    assert len(records_csv) == 1
    assert records_csv[0].fnsku == "X002"
    assert records_csv[0].quantity == 5


# ---------------------------------------------------------------------------
# Error Handling & Edge Case Tests
# ---------------------------------------------------------------------------

def test_missing_mandatory_column_raises_schema_validation_error():
    """Verifies that missing essential mandatory headers raises SchemaValidationError."""
    tsv_missing_fnsku = "Date and Time\tQuantity\tEvent Type\n2026-08-01\t10\tReceipts\n"
    with pytest.raises(SchemaValidationError) as exc_info:
        parse_ledger_report(tsv_missing_fnsku)
    assert "missing mandatory column" in str(exc_info.value).lower()
    assert "fnsku" in exc_info.value.missing_columns


def test_corrupted_numeric_value_handling():
    """Verifies that non-numeric values in numeric fields raise RowParsingError."""
    tsv_bad_qty = (
        "Date and Time\tFNSKU\tQuantity\tEvent Type\n"
        "2026-08-01T08:30:00Z\tX001\tNOT_A_NUMBER\tReceipts\n"
    )
    with pytest.raises(RowParsingError) as exc_info:
        parse_ledger_report(tsv_bad_qty)
    assert "quantity" in str(exc_info.value).lower()
    assert exc_info.value.line_number == 2


def test_empty_and_whitespace_file():
    """Verifies that empty files or whitespace-only files return an empty list without error."""
    assert parse_ledger_report("") == []
    assert parse_ledger_report("   \n\t\n   ") == []
    assert parse_customer_returns_report("") == []
    assert parse_reimbursements_report("") == []
    assert parse_estimated_fees_report("") == []


def test_parser_handles_empty_and_malformed_lines():
    """Verifies skipping of empty and blank lines in the middle of a report."""
    tsv_content = "Date\tFNSKU\tEvent Type\tQuantity\n\n\t\t\t\n2026-08-01\tX001\tLost\t5\n"
    records = parse_ledger_report(tsv_content)
    assert len(records) == 1
    assert records[0].fnsku == "X001"
    assert records[0].quantity == 5


# ---------------------------------------------------------------------------
# Direct Coercion Utility Tests
# ---------------------------------------------------------------------------

def test_base_coercion_utilities():
    """Directly test base.py conversion functions and error paths."""
    from fba_audit.parsers.base import (
        parse_decimal,
        parse_int,
        parse_iso_datetime,
        parse_str,
        read_content_string,
    )

    # Decimal
    assert parse_decimal(None, 1, "field", allow_none=True, default=Decimal("1.00")) == Decimal("1.00")
    with pytest.raises(RowParsingError):
        parse_decimal(None, 1, "field", allow_none=False)
    with pytest.raises(RowParsingError):
        parse_decimal("", 1, "field", allow_none=False)
    assert parse_decimal("", 1, "field", allow_none=True, default=None) is None
    with pytest.raises(RowParsingError):
        parse_decimal("bad_number", 1, "field")

    # Integer
    assert parse_int(None, 1, "qty", allow_none=True, default=5) == 5
    with pytest.raises(RowParsingError):
        parse_int(None, 1, "qty", allow_none=False)
    with pytest.raises(RowParsingError):
        parse_int("", 1, "qty", allow_none=False)
    assert parse_int("", 1, "qty", allow_none=True, default=0) == 0
    with pytest.raises(RowParsingError):
        parse_int("not_an_int", 1, "qty")

    # String
    assert parse_str(None, 1, "name", allow_none=True) is None
    with pytest.raises(RowParsingError):
        parse_str(None, 1, "name", allow_none=False)
    with pytest.raises(RowParsingError):
        parse_str("   ", 1, "name", allow_none=False)
    assert parse_str("  valid  ", 1, "name") == "valid"

    # Datetime legacy patterns
    dt1 = parse_iso_datetime("2026/08/15", 1, "dt")
    assert dt1.year == 2026 and dt1.month == 8 and dt1.day == 15
    dt2 = parse_iso_datetime("15-08-2026", 1, "dt")
    assert dt2.year == 2026 and dt2.month == 8 and dt2.day == 15
    with pytest.raises(RowParsingError):
        parse_iso_datetime("not_a_date", 1, "dt")
    with pytest.raises(RowParsingError):
        parse_iso_datetime("", 1, "dt")

    # Stream read
    s = io.StringIO("test content")
    assert read_content_string(s) == "test content"


def test_parsers_stream_and_error_handling():
    """Verify that all report parsers accept io.StringIO streams and handle malformed rows."""
    # Ledger stream
    s_ledger = io.StringIO("Date and Time\tFNSKU\tQuantity\tEvent Type\n2026-08-01\tX01\t1\tReceipts\n")
    recs = parse_ledger_report(s_ledger)
    assert len(recs) == 1

    # Returns stream with missing date
    s_ret_bad = "return-date\torder-id\tfnsku\n\t111-222\tX01\n"
    with pytest.raises(RowParsingError):
        parse_customer_returns_report(s_ret_bad)

    # Reimbursements with missing date
    s_reimb_bad = "approval-date\treimbursement-id\tfnsku\n\tR1\tX01\n"
    with pytest.raises(RowParsingError):
        parse_reimbursements_report(s_reimb_bad)

    # Missing mandatory column in customer returns
    with pytest.raises(SchemaValidationError):
        parse_customer_returns_report("order-id\tquantity\nORD-1\t1\n")

    # Missing mandatory column in reimbursements
    with pytest.raises(SchemaValidationError):
        parse_reimbursements_report("approval-date\tquantity\n2026-08-01\t1\n")

    # Missing mandatory column in estimated fees
    with pytest.raises(SchemaValidationError):
        parse_estimated_fees_report("fnsku\tyour-price\nX01\t10.00\n")
