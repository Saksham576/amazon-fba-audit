"""
tests/e2e/test_tier1_features.py

Tier 1: Comprehensive Feature Coverage Test Suite (>=65 tests)
Strictly covering all 13 core features defined in TEST_INFRA.md:
  1. Ledger Detail TSV Parser (5 tests)
  2. Customer Returns TSV Parser (5 tests)
  3. Reimbursements TSV Parser (5 tests)
  4. Estimated Fees TSV Parser (5 tests)
  5. Warehouse Lost/Damaged Math (5 tests)
  6. Customer Return 45-60 Day Reconciler (5 tests)
  7. Dimensional Tier & Fee Overcharge (5 tests)
  8. Policy Citation & Claim Window (5 tests)
  9. 19-Column CSV Claim Batch (5 tests)
  10. Draft-2020-12 JSON Claim Batch (5 tests)
  11. Markdown Executive Dossier (5 tests)
  12. Standalone HTML Executive Dossier (5 tests)
  13. CLI & Python API Execution (5 tests)
"""

import csv
from datetime import date, datetime, timedelta
from decimal import Decimal
import io
import json
from pathlib import Path
import pytest

from tests.conftest import (
    parse_ledger_report,
    parse_customer_returns_report,
    parse_reimbursements_report,
    parse_estimated_fees_report,
    AuditEngine,
    ClaimRecord,
    export_claim_batch_csv,
    export_claim_batch_json,
    generate_markdown_dossier,
    generate_html_dossier,
    LedgerDetailRecord,
    CustomerReturnRecord,
    ReimbursementRecord,
    FeeEstimateRecord,
)
from tests.generators.ledger_simulator import LedgerSimulator, SimulatedSKU


# ---------------------------------------------------------------------------
# Feature 1: Ledger Detail TSV Parser (5 tests)
# ---------------------------------------------------------------------------

def test_f1_ledger_parser_extracts_all_mandatory_columns():
    tsv = (
        "Date\tFNSKU\tASIN\tMSKU\tTitle\tEvent Type\tReference ID\tQuantity\tFulfillment Center\tDisposition\tReason\tCountry\tStarting Balance\tEnding Balance\n"
        "2026-07-15\tX0000001\tB00112233\tMSKU-01\tTest Product\tAdjustments\tREF-100\t-3\tPHX3\tSELLABLE\tM\tUS\t10\t7\n"
    )
    records = parse_ledger_report(tsv)
    assert len(records) == 1
    rec = records[0]
    assert rec.date == date(2026, 7, 15)
    assert rec.fnsku == "X0000001"
    assert rec.asin == "B00112233"
    assert rec.msku == "MSKU-01"
    assert rec.title == "Test Product"
    assert rec.event_type == "Adjustments"
    assert rec.reference_id == "REF-100"
    assert rec.quantity == -3
    assert rec.fulfillment_center == "PHX3"
    assert rec.disposition == "SELLABLE"
    assert rec.reason == "M"
    assert rec.country == "US"


def test_f1_ledger_parser_handles_different_event_types():
    tsv = (
        "Date\tFNSKU\tASIN\tMSKU\tTitle\tEvent Type\tReference ID\tQuantity\tFulfillment Center\tDisposition\tReason\tCountry\tStarting Balance\tEnding Balance\n"
        "2026-07-01\tX01\tB01\tM01\tT1\tReceipts\tREC-1\t100\tIND1\tSELLABLE\t\tUS\t0\t100\n"
        "2026-07-02\tX01\tB01\tM01\tT1\tShipments\tORD-1\t-5\tIND1\tSELLABLE\t\tUS\t100\t95\n"
        "2026-07-03\tX01\tB01\tM01\tT1\tCustomerReturns\tRET-1\t1\tIND1\tSELLABLE\t\tUS\t95\t96\n"
    )
    records = parse_ledger_report(tsv)
    assert len(records) == 3
    assert [r.event_type for r in records] == ["Receipts", "Shipments", "CustomerReturns"]


def test_f1_ledger_parser_handles_adjustment_reasons():
    tsv = (
        "Date\tFNSKU\tASIN\tMSKU\tTitle\tEvent Type\tReference ID\tQuantity\tFulfillment Center\tDisposition\tReason\tCountry\tStarting Balance\tEnding Balance\n"
        "2026-07-10\tX01\tB01\tM01\tT1\tAdjustments\tADJ-1\t5\tPHX3\tSELLABLE\tM\tUS\t50\t45\n"
        "2026-07-11\tX01\tB01\tM01\tT1\tAdjustments\tADJ-2\t2\tPHX3\tDAMAGED\tE\tUS\t45\t43\n"
        "2026-07-12\tX01\tB01\tM01\tT1\tAdjustments\tADJ-3\t1\tPHX3\tSELLABLE\tN\tUS\t43\t44\n"
    )
    records = parse_ledger_report(tsv)
    assert len(records) == 3
    assert [r.reason for r in records] == ["M", "E", "N"]


def test_f1_ledger_parser_preserves_negative_quantities():
    tsv = (
        "Date\tFNSKU\tASIN\tMSKU\tTitle\tEvent Type\tReference ID\tQuantity\tFulfillment Center\tDisposition\tReason\tCountry\tStarting Balance\tEnding Balance\n"
        "2026-07-05\tX01\tB01\tM01\tT1\tShipments\tORD-99\t-25\tONT8\tSELLABLE\t\tUS\t100\t75\n"
    )
    records = parse_ledger_report(tsv)
    assert records[0].quantity == -25


def test_f1_ledger_parser_accepts_file_path_and_string_io(tmp_path: Path):
    content = (
        "Date\tFNSKU\tASIN\tMSKU\tTitle\tEvent Type\tReference ID\tQuantity\tFulfillment Center\tDisposition\tReason\tCountry\tStarting Balance\tEnding Balance\n"
        "2026-07-05\tX01\tB01\tM01\tT1\tShipments\tORD-99\t-1\tONT8\tSELLABLE\t\tUS\t10\t9\n"
    )
    file_path = tmp_path / "ledger.tsv"
    file_path.write_text(content, encoding="utf-8")
    records_from_file = parse_ledger_report(file_path)
    records_from_io = parse_ledger_report(io.StringIO(content))
    assert len(records_from_file) == 1
    assert len(records_from_io) == 1
    assert records_from_file[0].reference_id == records_from_io[0].reference_id


# ---------------------------------------------------------------------------
# Feature 2: Customer Returns TSV Parser (5 tests)
# ---------------------------------------------------------------------------

def test_f2_returns_parser_extracts_all_13_columns():
    tsv = (
        "return-date\torder-id\tsku\tasin\tfnsku\tproduct-name\tquantity\tfulfillment-center-id\tdetailed-disposition\treason\tstatus\tlicense-plate-number\tcustomer-comments\n"
        "2026-07-20T10:15:30Z\t111-1234567-0000001\tSKU-10\tB001\tX001\tGadget\t1\tIND1\tDEFECTIVE\tDefective\tUnit returned to inventory\tLPN-991\tDoes not turn on\n"
    )
    records = parse_customer_returns_report(tsv)
    assert len(records) == 1
    r = records[0]
    assert r.order_id == "111-1234567-0000001"
    assert r.sku == "SKU-10"
    assert r.asin == "B001"
    assert r.fnsku == "X001"
    assert r.product_name == "Gadget"
    assert r.quantity == 1
    assert r.fulfillment_center_id == "IND1"
    assert r.detailed_disposition == "DEFECTIVE"
    assert r.reason == "Defective"
    assert r.status == "Unit returned to inventory"
    assert r.license_plate_number == "LPN-991"
    assert r.customer_comments == "Does not turn on"


def test_f2_returns_parser_normalizes_iso_timestamps():
    tsv = (
        "return-date\torder-id\tsku\tasin\tfnsku\tproduct-name\tquantity\tfulfillment-center-id\tdetailed-disposition\treason\tstatus\tlicense-plate-number\tcustomer-comments\n"
        "2026-08-15T18:30:00Z\t111-222-333\tS1\tB1\tX1\tP1\t1\tPHX3\tSELLABLE\tUnwanted\tUnit returned to inventory\tLPN-1\tNo longer needed\n"
    )
    records = parse_customer_returns_report(tsv)
    assert records[0].return_date.year == 2026
    assert records[0].return_date.month == 8
    assert records[0].return_date.day == 15


def test_f2_returns_parser_parses_various_dispositions():
    tsv = (
        "return-date\torder-id\tsku\tasin\tfnsku\tproduct-name\tquantity\tfulfillment-center-id\tdetailed-disposition\treason\tstatus\tlicense-plate-number\tcustomer-comments\n"
        "2026-08-01T00:00:00Z\tO1\tS1\tB1\tX1\tP1\t1\tF1\tSELLABLE\tR1\tS1\tL1\tC1\n"
        "2026-08-02T00:00:00Z\tO2\tS2\tB2\tX2\tP2\t1\tF2\tCUSTOMER_DAMAGED\tR2\tS2\tL2\tC2\n"
        "2026-08-03T00:00:00Z\tO3\tS3\tB3\tX3\tP3\t1\tF3\tCARRIER_DAMAGED\tR3\tS3\tL3\tC3\n"
    )
    records = parse_customer_returns_report(tsv)
    assert [r.detailed_disposition for r in records] == ["SELLABLE", "CUSTOMER_DAMAGED", "CARRIER_DAMAGED"]


def test_f2_returns_parser_handles_license_plates_and_comments():
    tsv = (
        "return-date\torder-id\tsku\tasin\tfnsku\tproduct-name\tquantity\tfulfillment-center-id\tdetailed-disposition\treason\tstatus\tlicense-plate-number\tcustomer-comments\n"
        "2026-08-05T00:00:00Z\tO1\tS1\tB1\tX1\tP1\t1\tF1\tSELLABLE\tR1\tS1\tlpn_rr_12345_6789\tBox opened, item pristine\n"
    )
    records = parse_customer_returns_report(tsv)
    assert records[0].license_plate_number == "lpn_rr_12345_6789"
    assert records[0].customer_comments == "Box opened, item pristine"


def test_f2_returns_parser_extracts_integer_quantities():
    tsv = (
        "return-date\torder-id\tsku\tasin\tfnsku\tproduct-name\tquantity\tfulfillment-center-id\tdetailed-disposition\treason\tstatus\tlicense-plate-number\tcustomer-comments\n"
        "2026-08-05T00:00:00Z\tO1\tS1\tB1\tX1\tP1\t5\tF1\tSELLABLE\tR1\tS1\tL1\tC1\n"
    )
    records = parse_customer_returns_report(tsv)
    assert records[0].quantity == 5


# ---------------------------------------------------------------------------
# Feature 3: Reimbursements TSV Parser (5 tests)
# ---------------------------------------------------------------------------

def test_f3_reimbursements_parser_extracts_all_16_columns():
    tsv = (
        "approval-date\treimbursement-id\tcase-id\tamazon-order-id\treason\tsku\tfnsku\tasin\tproduct-name\tcondition\tcurrency-unit\tamount-per-unit\tamount-total\tquantity-reimbursed-cash\tquantity-reimbursed-inventory\tquantity-reimbursed-total\n"
        "2026-08-10T14:20:00Z\tREIMB-001\tCASE-101\t111-999-000\tLost_Warehouse\tMSKU-01\tX001\tB001\tItem A\tNew\tUSD\t25.50\t51.00\t2\t0\t2\n"
    )
    records = parse_reimbursements_report(tsv)
    assert len(records) == 1
    r = records[0]
    assert r.reimbursement_id == "REIMB-001"
    assert r.case_id == "CASE-101"
    assert r.amazon_order_id == "111-999-000"
    assert r.reason == "Lost_Warehouse"
    assert r.amount_per_unit == Decimal("25.50")
    assert r.amount_total == Decimal("51.00")
    assert r.quantity_reimbursed_cash == 2
    assert r.quantity_reimbursed_inventory == 0
    assert r.quantity_reimbursed_total == 2


def test_f3_reimbursements_parser_exact_decimal_currency():
    tsv = (
        "approval-date\treimbursement-id\tcase-id\tamazon-order-id\treason\tsku\tfnsku\tasin\tproduct-name\tcondition\tcurrency-unit\tamount-per-unit\tamount-total\tquantity-reimbursed-cash\tquantity-reimbursed-inventory\tquantity-reimbursed-total\n"
        "2026-08-10T00:00:00Z\tR1\tC1\tO1\tLost\tS1\tX1\tB1\tP1\tNew\tUSD\t19.99\t19.99\t1\t0\t1\n"
    )
    records = parse_reimbursements_report(tsv)
    assert isinstance(records[0].amount_total, Decimal)
    assert records[0].amount_total == Decimal("19.99")


def test_f3_reimbursements_parser_distinguishes_cash_vs_inventory():
    tsv = (
        "approval-date\treimbursement-id\tcase-id\tamazon-order-id\treason\tsku\tfnsku\tasin\tproduct-name\tcondition\tcurrency-unit\tamount-per-unit\tamount-total\tquantity-reimbursed-cash\tquantity-reimbursed-inventory\tquantity-reimbursed-total\n"
        "2026-08-10T00:00:00Z\tR1\tC1\tO1\tLost\tS1\tX1\tB1\tP1\tNew\tUSD\t10.00\t10.00\t1\t0\t1\n"
        "2026-08-11T00:00:00Z\tR2\tC2\tO2\tLost\tS1\tX1\tB1\tP1\tNew\tUSD\t0.00\t0.00\t0\t1\t1\n"
    )
    records = parse_reimbursements_report(tsv)
    assert records[0].quantity_reimbursed_cash == 1
    assert records[0].quantity_reimbursed_inventory == 0
    assert records[1].quantity_reimbursed_cash == 0
    assert records[1].quantity_reimbursed_inventory == 1


def test_f3_reimbursements_parser_links_order_id_and_case_id():
    tsv = (
        "approval-date\treimbursement-id\tcase-id\tamazon-order-id\treason\tsku\tfnsku\tasin\tproduct-name\tcondition\tcurrency-unit\tamount-per-unit\tamount-total\tquantity-reimbursed-cash\tquantity-reimbursed-inventory\tquantity-reimbursed-total\n"
        "2026-08-10T00:00:00Z\tR1\tCASE-888\tORDER-777\tCustomerReturn\tS1\tX1\tB1\tP1\tNew\tUSD\t15.00\t15.00\t1\t0\t1\n"
    )
    records = parse_reimbursements_report(tsv)
    assert records[0].case_id == "CASE-888"
    assert records[0].amazon_order_id == "ORDER-777"


def test_f3_reimbursements_parser_handles_zero_amount_replacements():
    tsv = (
        "approval-date\treimbursement-id\tcase-id\tamazon-order-id\treason\tsku\tfnsku\tasin\tproduct-name\tcondition\tcurrency-unit\tamount-per-unit\tamount-total\tquantity-reimbursed-cash\tquantity-reimbursed-inventory\tquantity-reimbursed-total\n"
        "2026-08-10T00:00:00Z\tR1\tC1\tO1\tDamaged_Warehouse\tS1\tX1\tB1\tP1\tNew\tUSD\t0.00\t0.00\t0\t3\t3\n"
    )
    records = parse_reimbursements_report(tsv)
    assert records[0].amount_total == Decimal("0.00")
    assert records[0].quantity_reimbursed_total == 3


# ---------------------------------------------------------------------------
# Feature 4: Estimated Fees TSV Parser (5 tests)
# ---------------------------------------------------------------------------

def test_f4_fees_parser_extracts_dimensions_and_weight():
    tsv = (
        "sku\tfnsku\tasin\tproduct-name\tproduct-group\tbrand\tfulfilled-by\tyour-price\tsales-price\tlongest-side\tmedian-side\tshortest-side\tunit-of-dimension\titem-package-weight\tunit-of-weight\tproduct-size-tier\testimated-fee-total\testimated-order-handling-fee-per-unit\testimated-pick-pack-fee-per-unit\testimated-weight-handling-fee-per-unit\texpected-fulfillment-fee-per-unit\n"
        "SKU-1\tX01\tB01\tProduct 1\tHome\tBrandA\tAMAZON_NA\t29.99\t29.99\t12.5\t8.2\t1.5\tinches\t1.4\tpounds\tLarge Standard\t4.75\t0.00\t4.75\t0.00\t4.75\n"
    )
    records = parse_estimated_fees_report(tsv)
    assert len(records) == 1
    r = records[0]
    assert r.longest_side == Decimal("12.5")
    assert r.median_side == Decimal("8.2")
    assert r.shortest_side == Decimal("1.5")
    assert r.item_package_weight == Decimal("1.4")


def test_f4_fees_parser_parses_size_tiers():
    tsv = (
        "sku\tfnsku\tasin\tproduct-name\tproduct-group\tbrand\tfulfilled-by\tyour-price\tsales-price\tlongest-side\tmedian-side\tshortest-side\tunit-of-dimension\titem-package-weight\tunit-of-weight\tproduct-size-tier\testimated-fee-total\testimated-order-handling-fee-per-unit\testimated-pick-pack-fee-per-unit\testimated-weight-handling-fee-per-unit\texpected-fulfillment-fee-per-unit\n"
        "S1\tX1\tB1\tP1\tH\tB\tA\t10\t10\t10\t5\t0.5\tinches\t0.5\tpounds\tSmall Standard\t3.40\t0\t3.40\t0\t3.40\n"
        "S2\tX2\tB2\tP2\tH\tB\tA\t20\t20\t25\t15\t5.0\tinches\t5.0\tpounds\tSmall Oversize\t9.73\t0\t9.73\t0\t9.73\n"
    )
    records = parse_estimated_fees_report(tsv)
    assert records[0].product_size_tier == "Small Standard"
    assert records[1].product_size_tier == "Small Oversize"


def test_f4_fees_parser_exact_decimal_fees():
    tsv = (
        "sku\tfnsku\tasin\tproduct-name\tproduct-group\tbrand\tfulfilled-by\tyour-price\tsales-price\tlongest-side\tmedian-side\tshortest-side\tunit-of-dimension\titem-package-weight\tunit-of-weight\tproduct-size-tier\testimated-fee-total\testimated-order-handling-fee-per-unit\testimated-pick-pack-fee-per-unit\testimated-weight-handling-fee-per-unit\texpected-fulfillment-fee-per-unit\n"
        "S1\tX1\tB1\tP1\tH\tB\tA\t15.99\t15.99\t10\t5\t1\tinches\t1\tpounds\tLarge Standard\t4.08\t0\t4.08\t0\t4.08\n"
    )
    records = parse_estimated_fees_report(tsv)
    assert records[0].estimated_fee_total == Decimal("4.08")
    assert records[0].expected_fulfillment_fee_per_unit == Decimal("4.08")


def test_f4_fees_parser_extracts_catalog_attributes():
    tsv = (
        "sku\tfnsku\tasin\tproduct-name\tproduct-group\tbrand\tfulfilled-by\tyour-price\tsales-price\tlongest-side\tmedian-side\tshortest-side\tunit-of-dimension\titem-package-weight\tunit-of-weight\tproduct-size-tier\testimated-fee-total\testimated-order-handling-fee-per-unit\testimated-pick-pack-fee-per-unit\testimated-weight-handling-fee-per-unit\texpected-fulfillment-fee-per-unit\n"
        "MSKU-EL-10\tX001\tB001\tBluetooth Speaker\tWireless\tAudioPro\tAMAZON_NA\t49.99\t49.99\t8\t4\t4\tinches\t2.1\tpounds\tLarge Standard\t5.40\t0\t5.40\t0\t5.40\n"
    )
    records = parse_estimated_fees_report(tsv)
    assert records[0].brand == "AudioPro"
    assert records[0].product_group == "Wireless"
    assert records[0].fulfilled_by == "AMAZON_NA"


def test_f4_fees_parser_handles_mixed_dimension_units():
    tsv = (
        "sku\tfnsku\tasin\tproduct-name\tproduct-group\tbrand\tfulfilled-by\tyour-price\tsales-price\tlongest-side\tmedian-side\tshortest-side\tunit-of-dimension\titem-package-weight\tunit-of-weight\tproduct-size-tier\testimated-fee-total\testimated-order-handling-fee-per-unit\testimated-pick-pack-fee-per-unit\testimated-weight-handling-fee-per-unit\texpected-fulfillment-fee-per-unit\n"
        "S1\tX1\tB1\tP1\tH\tB\tA\t10\t10\t10\t5\t1\tinches\t16\tounces\tSmall Standard\t3.77\t0\t3.77\t0\t3.77\n"
    )
    records = parse_estimated_fees_report(tsv)
    assert records[0].unit_of_weight == "ounces"
    assert records[0].unit_of_dimension == "inches"


# ---------------------------------------------------------------------------
# Feature 5: Warehouse Lost/Damaged Math (5 tests)
# ---------------------------------------------------------------------------

def test_f5_warehouse_math_pure_lost_uncompensated():
    engine = AuditEngine()
    ledger = [
        LedgerDetailRecord(
            date=date(2026, 8, 1), fnsku="X001", asin="B001", msku="M001", title="Product A",
            event_type="Adjustments", reference_id="REF-1", quantity=5, fulfillment_center="PHX3",
            disposition="SELLABLE", reason="M"
        )
    ]
    res = engine.reconcile(ledger, [], [], [], as_of_date=date(2026, 8, 20))
    wh_claims = [c for c in res.claims if c.discrepancy_type == "WAREHOUSE_LOST_DAMAGED"]
    assert len(wh_claims) == 1
    assert wh_claims[0].quantity == 5


def test_f5_warehouse_math_found_within_30_days_offsets_loss():
    engine = AuditEngine()
    ledger = [
        LedgerDetailRecord(
            date=date(2026, 8, 1), fnsku="X001", asin="B001", msku="M001", title="Product A",
            event_type="Adjustments", reference_id="REF-1", quantity=5, fulfillment_center="PHX3",
            disposition="SELLABLE", reason="M"  # Lost 5
        ),
        LedgerDetailRecord(
            date=date(2026, 8, 15), fnsku="X001", asin="B001", msku="M001", title="Product A",
            event_type="Adjustments", reference_id="REF-2", quantity=2, fulfillment_center="PHX3",
            disposition="SELLABLE", reason="N"  # Found 2
        )
    ]
    res = engine.reconcile(ledger, [], [], [], as_of_date=date(2026, 8, 20))
    wh_claims = [c for c in res.claims if c.discrepancy_type == "WAREHOUSE_LOST_DAMAGED"]
    assert len(wh_claims) == 1
    assert wh_claims[0].quantity == 3  # 5 - 2 = 3


def test_f5_warehouse_math_damaged_plus_lost_minus_reimbursed():
    engine = AuditEngine()
    ledger = [
        LedgerDetailRecord(
            date=date(2026, 8, 1), fnsku="X001", asin="B001", msku="M001", title="Product A",
            event_type="Adjustments", reference_id="REF-1", quantity=4, fulfillment_center="PHX3",
            disposition="SELLABLE", reason="M"  # Lost 4
        ),
        LedgerDetailRecord(
            date=date(2026, 8, 2), fnsku="X001", asin="B001", msku="M001", title="Product A",
            event_type="Adjustments", reference_id="REF-2", quantity=3, fulfillment_center="PHX3",
            disposition="DAMAGED", reason="E"  # Damaged 3
        )
    ]
    reimbs = [
        ReimbursementRecord(
            approval_date=datetime(2026, 8, 10, 0, 0), reimbursement_id="R1", case_id="C1",
            amazon_order_id="", reason="Lost_Warehouse", sku="M001", fnsku="X001", asin="B001",
            product_name="Product A", condition="New", currency_unit="USD",
            amount_per_unit=Decimal("20.99"), amount_total=Decimal("41.98"),
            quantity_reimbursed_cash=2, quantity_reimbursed_inventory=0, quantity_reimbursed_total=2
        )
    ]
    res = engine.reconcile(ledger, [], reimbs, [], as_of_date=date(2026, 8, 20))
    wh_claims = [c for c in res.claims if c.discrepancy_type == "WAREHOUSE_LOST_DAMAGED"]
    assert len(wh_claims) == 1
    # (4 lost + 3 damaged) - 2 reimbursed = 5 uncompensated
    assert wh_claims[0].quantity == 5


def test_f5_warehouse_math_disposed_inventory_offset():
    engine = AuditEngine()
    ledger = [
        LedgerDetailRecord(
            date=date(2026, 8, 1), fnsku="X001", asin="B001", msku="M001", title="Product A",
            event_type="Adjustments", reference_id="REF-1", quantity=5, fulfillment_center="PHX3",
            disposition="SELLABLE", reason="M"
        ),
        LedgerDetailRecord(
            date=date(2026, 8, 5), fnsku="X001", asin="B001", msku="M001", title="Product A",
            event_type="Adjustments", reference_id="REF-2", quantity=1, fulfillment_center="PHX3",
            disposition="DEFECTIVE", reason="X"  # Disposed 1
        )
    ]
    res = engine.reconcile(ledger, [], [], [], as_of_date=date(2026, 8, 20))
    wh_claims = [c for c in res.claims if c.discrepancy_type == "WAREHOUSE_LOST_DAMAGED"]
    assert len(wh_claims) == 1
    assert wh_claims[0].quantity == 4  # 5 - 1 = 4


def test_f5_warehouse_math_zero_balance_generates_zero_claims():
    engine = AuditEngine()
    ledger = [
        LedgerDetailRecord(
            date=date(2026, 8, 1), fnsku="X001", asin="B001", msku="M001", title="Product A",
            event_type="Adjustments", reference_id="REF-1", quantity=2, fulfillment_center="PHX3",
            disposition="SELLABLE", reason="M"
        ),
        LedgerDetailRecord(
            date=date(2026, 8, 5), fnsku="X001", asin="B001", msku="M001", title="Product A",
            event_type="Adjustments", reference_id="REF-2", quantity=2, fulfillment_center="PHX3",
            disposition="SELLABLE", reason="N"  # All 2 found
        )
    ]
    res = engine.reconcile(ledger, [], [], [], as_of_date=date(2026, 8, 20))
    wh_claims = [c for c in res.claims if c.discrepancy_type == "WAREHOUSE_LOST_DAMAGED"]
    assert len(wh_claims) == 0


# ---------------------------------------------------------------------------
# Feature 6: Customer Return 45-60 Day Reconciler (5 tests)
# ---------------------------------------------------------------------------

def test_f6_returns_reconciler_under_45_days_ineligible():
    engine = AuditEngine()
    # Refund on Aug 1, as of Aug 25 (24 days elapsed <= 45 days)
    returns = [
        CustomerReturnRecord(
            return_date=datetime(2026, 8, 1, 0, 0), order_id="111-0000001", sku="M1", asin="B1",
            fnsku="X1", product_name="P1", quantity=1, fulfillment_center_id="IND1",
            detailed_disposition="DEFECTIVE", reason="Late", status="Unit not received",
            license_plate_number="", customer_comments=""
        )
    ]
    res = engine.reconcile([], returns, [], [], as_of_date=date(2026, 8, 25))
    ret_claims = [c for c in res.claims if c.discrepancy_type == "CUSTOMER_RETURN_NOT_RETURNED"]
    assert len(ret_claims) == 0


def test_f6_returns_reconciler_past_45_days_eligible():
    engine = AuditEngine()
    # Refund on July 1, as of Aug 20 (50 days elapsed > 45 days)
    returns = [
        CustomerReturnRecord(
            return_date=datetime(2026, 7, 1, 0, 0), order_id="111-0000002", sku="M1", asin="B1",
            fnsku="X1", product_name="P1", quantity=1, fulfillment_center_id="IND1",
            detailed_disposition="DEFECTIVE", reason="Late", status="Unit not received",
            license_plate_number="", customer_comments=""
        )
    ]
    res = engine.reconcile([], returns, [], [], as_of_date=date(2026, 8, 20))
    ret_claims = [c for c in res.claims if c.discrepancy_type == "CUSTOMER_RETURN_NOT_RETURNED"]
    assert len(ret_claims) == 1
    assert ret_claims[0].claim_status == "ELIGIBLE"


def test_f6_returns_reconciler_reimbursed_order_generates_zero_claims():
    engine = AuditEngine()
    returns = [
        CustomerReturnRecord(
            return_date=datetime(2026, 7, 1, 0, 0), order_id="111-0000003", sku="M1", asin="B1",
            fnsku="X1", product_name="P1", quantity=1, fulfillment_center_id="IND1",
            detailed_disposition="DEFECTIVE", reason="Late", status="Reimbursed",
            license_plate_number="", customer_comments=""
        )
    ]
    res = engine.reconcile([], returns, [], [], as_of_date=date(2026, 8, 20))
    assert len(res.claims) == 0


def test_f6_returns_reconciler_returned_within_grace_period_no_claim():
    engine = AuditEngine()
    # Received at FC 10 days after refund
    returns = [
        CustomerReturnRecord(
            return_date=datetime(2026, 7, 10, 0, 0), order_id="111-0000004", sku="M1", asin="B1",
            fnsku="X1", product_name="P1", quantity=1, fulfillment_center_id="IND1",
            detailed_disposition="SELLABLE", reason="Unwanted", status="Unit returned to inventory",
            license_plate_number="LPN-1", customer_comments=""
        )
    ]
    res = engine.reconcile([], returns, [], [], as_of_date=date(2026, 8, 20))
    assert len(res.claims) == 0


def test_f6_returns_reconciler_past_105_days_marked_expired():
    engine = AuditEngine()
    # Refund on April 1, as of Aug 20 (141 days elapsed > 105 days)
    returns = [
        CustomerReturnRecord(
            return_date=datetime(2026, 4, 1, 0, 0), order_id="111-0000005", sku="M1", asin="B1",
            fnsku="X1", product_name="P1", quantity=1, fulfillment_center_id="IND1",
            detailed_disposition="DEFECTIVE", reason="Late", status="Unit not received",
            license_plate_number="", customer_comments=""
        )
    ]
    res = engine.reconcile([], returns, [], [], as_of_date=date(2026, 8, 20))
    ret_claims = [c for c in res.claims if c.discrepancy_type == "CUSTOMER_RETURN_NOT_RETURNED"]
    assert len(ret_claims) == 1
    assert ret_claims[0].claim_status == "EXPIRED"


# ---------------------------------------------------------------------------
# Feature 7: Dimensional Tier & Fee Overcharge (5 tests)
# ---------------------------------------------------------------------------

def test_f7_dim_reconciler_detects_tier_shift():
    engine = AuditEngine()
    fee_records = [
        FeeEstimateRecord(
            sku="S1", fnsku="X01", asin="B01", product_name="Box", product_group="Home",
            brand="B", fulfilled_by="AMAZON_NA", your_price=Decimal("20.00"), sales_price=Decimal("20.00"),
            longest_side=Decimal("18.5"), median_side=Decimal("14.2"), shortest_side=Decimal("8.5"),
            unit_of_dimension="inches", item_package_weight=Decimal("5.0"), unit_of_weight="pounds",
            product_size_tier="Small Oversize", estimated_fee_total=Decimal("9.73"),
            estimated_order_handling_fee_per_unit=Decimal("0.00"), estimated_pick_pack_fee_per_unit=Decimal("9.73"),
            estimated_weight_handling_fee_per_unit=Decimal("0.00"), expected_fulfillment_fee_per_unit=Decimal("9.73")
        )
    ]
    catalog = {
        "X01": {
            "correct_fee": Decimal("5.40"),  # Catalog is Large Standard $5.40
            "units_sold": 50
        }
    }
    res = engine.reconcile([], [], [], fee_records, catalog_specs=catalog, as_of_date=date(2026, 9, 29))
    dim_claims = [c for c in res.claims if c.discrepancy_type == "DIMENSIONAL_FEE_OVERCHARGE"]
    assert len(dim_claims) == 1
    # 9.73 - 5.40 = 4.33 delta
    assert dim_claims[0].unit_price == Decimal("4.33")


def test_f7_dim_reconciler_computes_exact_fee_delta():
    engine = AuditEngine()
    fee_records = [
        FeeEstimateRecord(
            sku="S1", fnsku="X01", asin="B01", product_name="P1", product_group="H",
            brand="B", fulfilled_by="A", your_price=Decimal("15"), sales_price=Decimal("15"),
            longest_side=Decimal("12"), median_side=Decimal("8"), shortest_side=Decimal("2"),
            unit_of_dimension="inches", item_package_weight=Decimal("1"), unit_of_weight="pounds",
            product_size_tier="Large Standard", estimated_fee_total=Decimal("4.75"),
            estimated_order_handling_fee_per_unit=Decimal("0"), estimated_pick_pack_fee_per_unit=Decimal("4.75"),
            estimated_weight_handling_fee_per_unit=Decimal("0"), expected_fulfillment_fee_per_unit=Decimal("4.75")
        )
    ]
    catalog = {"X01": {"correct_fee": Decimal("3.86"), "units_sold": 100}}
    res = engine.reconcile([], [], [], fee_records, catalog_specs=catalog)
    dim_claim = res.claims[0]
    assert dim_claim.unit_price == Decimal("0.89")


def test_f7_dim_reconciler_scales_by_units_sold():
    engine = AuditEngine()
    fee_records = [
        FeeEstimateRecord(
            sku="S1", fnsku="X01", asin="B01", product_name="P1", product_group="H",
            brand="B", fulfilled_by="A", your_price=Decimal("15"), sales_price=Decimal("15"),
            longest_side=Decimal("12"), median_side=Decimal("8"), shortest_side=Decimal("2"),
            unit_of_dimension="inches", item_package_weight=Decimal("1"), unit_of_weight="pounds",
            product_size_tier="Large Standard", estimated_fee_total=Decimal("5.00"),
            estimated_order_handling_fee_per_unit=Decimal("0"), estimated_pick_pack_fee_per_unit=Decimal("5.00"),
            estimated_weight_handling_fee_per_unit=Decimal("0"), expected_fulfillment_fee_per_unit=Decimal("5.00")
        )
    ]
    catalog = {"X01": {"correct_fee": Decimal("4.00"), "units_sold": 250}}
    res = engine.reconcile([], [], [], fee_records, catalog_specs=catalog)
    # $1.00 delta * 250 units = $250.00
    assert res.claims[0].claim_amount == Decimal("250.00")


def test_f7_dim_reconciler_zero_overcharge_when_dimensions_match():
    engine = AuditEngine()
    fee_records = [
        FeeEstimateRecord(
            sku="S1", fnsku="X01", asin="B01", product_name="P1", product_group="H",
            brand="B", fulfilled_by="A", your_price=Decimal("15"), sales_price=Decimal("15"),
            longest_side=Decimal("12"), median_side=Decimal("8"), shortest_side=Decimal("2"),
            unit_of_dimension="inches", item_package_weight=Decimal("1"), unit_of_weight="pounds",
            product_size_tier="Large Standard", estimated_fee_total=Decimal("4.00"),
            estimated_order_handling_fee_per_unit=Decimal("0"), estimated_pick_pack_fee_per_unit=Decimal("4.00"),
            estimated_weight_handling_fee_per_unit=Decimal("0"), expected_fulfillment_fee_per_unit=Decimal("4.00")
        )
    ]
    catalog = {"X01": {"correct_fee": Decimal("4.00"), "units_sold": 100}}
    res = engine.reconcile([], [], [], fee_records, catalog_specs=catalog)
    assert len(res.claims) == 0


def test_f7_dim_reconciler_undercharge_generates_zero_claims():
    engine = AuditEngine()
    fee_records = [
        FeeEstimateRecord(
            sku="S1", fnsku="X01", asin="B01", product_name="P1", product_group="H",
            brand="B", fulfilled_by="A", your_price=Decimal("15"), sales_price=Decimal("15"),
            longest_side=Decimal("12"), median_side=Decimal("8"), shortest_side=Decimal("2"),
            unit_of_dimension="inches", item_package_weight=Decimal("1"), unit_of_weight="pounds",
            product_size_tier="Large Standard", estimated_fee_total=Decimal("3.50"),
            estimated_order_handling_fee_per_unit=Decimal("0"), estimated_pick_pack_fee_per_unit=Decimal("3.50"),
            estimated_weight_handling_fee_per_unit=Decimal("0"), expected_fulfillment_fee_per_unit=Decimal("3.50")
        )
    ]
    catalog = {"X01": {"correct_fee": Decimal("4.00"), "units_sold": 100}}
    res = engine.reconcile([], [], [], fee_records, catalog_specs=catalog)
    assert len(res.claims) == 0


# ---------------------------------------------------------------------------
# Feature 8: Policy Citation & Claim Window (5 tests)
# ---------------------------------------------------------------------------

def test_f8_policy_warehouse_cites_g200379860():
    engine = AuditEngine()
    ledger = [
        LedgerDetailRecord(
            date=date(2026, 9, 1), fnsku="X01", asin="B01", msku="M01", title="A",
            event_type="Adjustments", reference_id="R1", quantity=1, fulfillment_center="PHX3",
            disposition="SELLABLE", reason="M"
        )
    ]
    res = engine.reconcile(ledger, [], [], [], as_of_date=date(2026, 9, 10))
    assert res.claims[0].policy_citation == "G200379860"


def test_f8_policy_returns_cites_g200213130():
    engine = AuditEngine()
    returns = [
        CustomerReturnRecord(
            return_date=datetime(2026, 7, 1, 0, 0), order_id="O1", sku="M1", asin="B1",
            fnsku="X1", product_name="P1", quantity=1, fulfillment_center_id="IND1",
            detailed_disposition="DEFECTIVE", reason="Late", status="Unit not received",
            license_plate_number="", customer_comments=""
        )
    ]
    res = engine.reconcile([], returns, [], [], as_of_date=date(2026, 8, 20))
    assert res.claims[0].policy_citation == "G200213130"


def test_f8_policy_dimensions_cites_g21213():
    engine = AuditEngine()
    fee_records = [
        FeeEstimateRecord(
            sku="S1", fnsku="X01", asin="B01", product_name="P1", product_group="H",
            brand="B", fulfilled_by="A", your_price=Decimal("15"), sales_price=Decimal("15"),
            longest_side=Decimal("12"), median_side=Decimal("8"), shortest_side=Decimal("2"),
            unit_of_dimension="inches", item_package_weight=Decimal("1"), unit_of_weight="pounds",
            product_size_tier="Large Standard", estimated_fee_total=Decimal("5.00"),
            estimated_order_handling_fee_per_unit=Decimal("0"), estimated_pick_pack_fee_per_unit=Decimal("5.00"),
            estimated_weight_handling_fee_per_unit=Decimal("0"), expected_fulfillment_fee_per_unit=Decimal("5.00")
        )
    ]
    catalog = {"X01": {"correct_fee": Decimal("4.00"), "units_sold": 10}}
    res = engine.reconcile([], [], [], fee_records, catalog_specs=catalog)
    assert res.claims[0].policy_citation == "G21213"


def test_f8_policy_claim_window_60_days():
    engine = AuditEngine()
    ledger = [
        LedgerDetailRecord(
            date=date(2026, 9, 1), fnsku="X01", asin="B01", msku="M01", title="A",
            event_type="Adjustments", reference_id="R1", quantity=1, fulfillment_center="PHX3",
            disposition="SELLABLE", reason="M"
        )
    ]
    res = engine.reconcile(ledger, [], [], [], as_of_date=date(2026, 9, 10))
    assert res.claims[0].claim_window_days == 60


def test_f8_policy_days_remaining_calculated_relative_to_as_of_date():
    engine = AuditEngine()
    # Event on Sept 1, as of Sept 21 -> 20 days elapsed -> 60 - 20 = 40 days remaining
    ledger = [
        LedgerDetailRecord(
            date=date(2026, 9, 1), fnsku="X01", asin="B01", msku="M01", title="A",
            event_type="Adjustments", reference_id="R1", quantity=1, fulfillment_center="PHX3",
            disposition="SELLABLE", reason="M"
        )
    ]
    res = engine.reconcile(ledger, [], [], [], as_of_date=date(2026, 9, 21))
    assert res.claims[0].days_remaining == 40


# ---------------------------------------------------------------------------
# Feature 9: 19-Column CSV Claim Batch (5 tests)
# ---------------------------------------------------------------------------

def test_f9_csv_contains_exact_19_columns(tmp_path: Path):
    claims = [
        ClaimRecord(
            claim_id="cid-1", fnsku="X01", msku="M01", asin="B01", order_id="O1",
            transaction_id="TX-1", event_date=date(2026, 8, 1), discrepancy_type="WAREHOUSE_LOST_DAMAGED",
            quantity=2, unit_price=Decimal("15.50"), claim_amount=Decimal("31.00"), currency="USD",
            policy_citation="G200379860", policy_clause="Clause", claim_window_days=60,
            days_remaining=40, claim_status="ELIGIBLE", evidence_notes="Notes", fulfillment_center="PHX3"
        )
    ]
    out = export_claim_batch_csv(claims, tmp_path / "claims.csv")
    with open(out, mode="r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        assert len(header) == 19


def test_f9_csv_deterministic_claim_ids(tmp_path: Path):
    engine = AuditEngine()
    ledger = [
        LedgerDetailRecord(
            date=date(2026, 9, 1), fnsku="X01", asin="B01", msku="M01", title="A",
            event_type="Adjustments", reference_id="R1", quantity=1, fulfillment_center="PHX3",
            disposition="SELLABLE", reason="M"
        )
    ]
    res1 = engine.reconcile(ledger, [], [], [], as_of_date=date(2026, 9, 10))
    res2 = engine.reconcile(ledger, [], [], [], as_of_date=date(2026, 9, 10))
    assert res1.claims[0].claim_id == res2.claims[0].claim_id


def test_f9_csv_exact_two_decimal_places_currency(tmp_path: Path):
    claims = [
        ClaimRecord(
            claim_id="cid-1", fnsku="X01", msku="M01", asin="B01", order_id="O1",
            transaction_id="TX-1", event_date=date(2026, 8, 1), discrepancy_type="WAREHOUSE_LOST_DAMAGED",
            quantity=1, unit_price=Decimal("15.5"), claim_amount=Decimal("15.5"), currency="USD",
            policy_citation="G200379860", policy_clause="Clause", claim_window_days=60,
            days_remaining=40, claim_status="ELIGIBLE", evidence_notes="Notes", fulfillment_center="PHX3"
        )
    ]
    out = export_claim_batch_csv(claims, tmp_path / "claims.csv")
    with open(out, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        row = next(reader)
        assert row["unit_price"] == "15.50"
        assert row["claim_amount"] == "15.50"


def test_f9_csv_handles_empty_order_ids_for_warehouse_claims(tmp_path: Path):
    claims = [
        ClaimRecord(
            claim_id="cid-1", fnsku="X01", msku="M01", asin="B01", order_id="",
            transaction_id="TX-1", event_date=date(2026, 8, 1), discrepancy_type="WAREHOUSE_LOST_DAMAGED",
            quantity=1, unit_price=Decimal("10.00"), claim_amount=Decimal("10.00"), currency="USD",
            policy_citation="G200379860", policy_clause="Clause", claim_window_days=60,
            days_remaining=40, claim_status="ELIGIBLE", evidence_notes="Notes", fulfillment_center="PHX3"
        )
    ]
    out = export_claim_batch_csv(claims, tmp_path / "claims.csv")
    with open(out, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        row = next(reader)
        assert row["order_id"] == ""


def test_f9_csv_readable_by_standard_csv_reader(tmp_path: Path):
    claims = [
        ClaimRecord(
            claim_id=f"cid-{i}", fnsku=f"X0{i}", msku=f"M0{i}", asin=f"B0{i}", order_id="",
            transaction_id=f"TX-{i}", event_date=date(2026, 8, 1), discrepancy_type="WAREHOUSE_LOST_DAMAGED",
            quantity=1, unit_price=Decimal("10.00"), claim_amount=Decimal("10.00"), currency="USD",
            policy_citation="G200379860", policy_clause="Clause", claim_window_days=60,
            days_remaining=40, claim_status="ELIGIBLE", evidence_notes="Notes", fulfillment_center="PHX3"
        ) for i in range(5)
    ]
    out = export_claim_batch_csv(claims, tmp_path / "claims.csv")
    with open(out, mode="r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        assert len(reader) == 5


# ---------------------------------------------------------------------------
# Feature 10: Draft-2020-12 JSON Claim Batch (5 tests)
# ---------------------------------------------------------------------------

def test_f10_json_schema_header_present(tmp_path: Path):
    out = export_claim_batch_json([], tmp_path / "claims.json")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_f10_json_summary_kpis_accurate(tmp_path: Path):
    claims = [
        ClaimRecord(
            claim_id="cid-1", fnsku="X01", msku="M01", asin="B01", order_id="",
            transaction_id="TX-1", event_date=date(2026, 8, 1), discrepancy_type="WAREHOUSE_LOST_DAMAGED",
            quantity=2, unit_price=Decimal("25.00"), claim_amount=Decimal("50.00"), currency="USD",
            policy_citation="G200379860", policy_clause="Clause", claim_window_days=60,
            days_remaining=40, claim_status="ELIGIBLE", evidence_notes="Notes", fulfillment_center="PHX3"
        )
    ]
    out = export_claim_batch_json(claims, tmp_path / "claims.json")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["total_claims"] == 1
    assert data["total_amount"] == 50.0


def test_f10_json_claims_array_complete(tmp_path: Path):
    claims = [
        ClaimRecord(
            claim_id=f"cid-{i}", fnsku=f"X0{i}", msku=f"M0{i}", asin=f"B0{i}", order_id="",
            transaction_id=f"TX-{i}", event_date=date(2026, 8, 1), discrepancy_type="WAREHOUSE_LOST_DAMAGED",
            quantity=1, unit_price=Decimal("10.00"), claim_amount=Decimal("10.00"), currency="USD",
            policy_citation="G200379860", policy_clause="Clause", claim_window_days=60,
            days_remaining=40, claim_status="ELIGIBLE", evidence_notes="Notes", fulfillment_center="PHX3"
        ) for i in range(3)
    ]
    out = export_claim_batch_json(claims, tmp_path / "claims.json")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data["claims"]) == 3


def test_f10_json_valid_json_structure(tmp_path: Path):
    out = export_claim_batch_json([], tmp_path / "claims.json")
    raw = out.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    assert "batch_id" in parsed
    assert "generated_at" in parsed


def test_f10_json_numeric_fidelity(tmp_path: Path):
    claims = [
        ClaimRecord(
            claim_id="cid-1", fnsku="X01", msku="M01", asin="B01", order_id="",
            transaction_id="TX-1", event_date=date(2026, 8, 1), discrepancy_type="WAREHOUSE_LOST_DAMAGED",
            quantity=3, unit_price=Decimal("33.33"), claim_amount=Decimal("99.99"), currency="USD",
            policy_citation="G200379860", policy_clause="Clause", claim_window_days=60,
            days_remaining=40, claim_status="ELIGIBLE", evidence_notes="Notes", fulfillment_center="PHX3"
        )
    ]
    out = export_claim_batch_json(claims, tmp_path / "claims.json")
    data = json.loads(out.read_text(encoding="utf-8"))
    claim = data["claims"][0]
    assert claim["quantity"] == "3"
    assert claim["claim_amount"] == "99.99"


# ---------------------------------------------------------------------------
# Feature 11: Markdown Executive Dossier (5 tests)
# ---------------------------------------------------------------------------

def test_f11_md_contains_executive_kpis(tmp_path: Path):
    engine = AuditEngine()
    ledger = [
        LedgerDetailRecord(
            date=date(2026, 9, 1), fnsku="X01", asin="B01", msku="M01", title="A",
            event_type="Adjustments", reference_id="R1", quantity=2, fulfillment_center="PHX3",
            disposition="SELLABLE", reason="M"
        )
    ]
    res = engine.reconcile(ledger, [], [], [], as_of_date=date(2026, 9, 10))
    out = generate_markdown_dossier(res, tmp_path / "dossier.md")
    content = out.read_text(encoding="utf-8")
    assert "**Total Verified Claims**: 1" in content
    assert "**Total Discrepancy Units**: 2" in content


def test_f11_md_contains_breakdown_by_type_table(tmp_path: Path):
    engine = AuditEngine()
    ledger = [
        LedgerDetailRecord(
            date=date(2026, 9, 1), fnsku="X01", asin="B01", msku="M01", title="A",
            event_type="Adjustments", reference_id="R1", quantity=1, fulfillment_center="PHX3",
            disposition="SELLABLE", reason="M"
        )
    ]
    res = engine.reconcile(ledger, [], [], [], as_of_date=date(2026, 9, 10))
    out = generate_markdown_dossier(res, tmp_path / "dossier.md")
    content = out.read_text(encoding="utf-8")
    assert "## Summary by Discrepancy Type" in content
    assert "| WAREHOUSE_LOST_DAMAGED | 1 | 1 |" in content


def test_f11_md_contains_itemized_evidence_table(tmp_path: Path):
    engine = AuditEngine()
    ledger = [
        LedgerDetailRecord(
            date=date(2026, 9, 1), fnsku="X01", asin="B01", msku="M01", title="A",
            event_type="Adjustments", reference_id="R1", quantity=1, fulfillment_center="PHX3",
            disposition="SELLABLE", reason="M"
        )
    ]
    res = engine.reconcile(ledger, [], [], [], as_of_date=date(2026, 9, 10))
    out = generate_markdown_dossier(res, tmp_path / "dossier.md")
    content = out.read_text(encoding="utf-8")
    assert "## Itemized Claims Evidence Table" in content
    assert "X01" in content


def test_f11_md_currency_formatting(tmp_path: Path):
    engine = AuditEngine()
    ledger = [
        LedgerDetailRecord(
            date=date(2026, 9, 1), fnsku="X01", asin="B01", msku="M01", title="A",
            event_type="Adjustments", reference_id="R1", quantity=1, fulfillment_center="PHX3",
            disposition="SELLABLE", reason="M"
        )
    ]
    res = engine.reconcile(ledger, [], [], [], as_of_date=date(2026, 9, 10))
    out = generate_markdown_dossier(res, tmp_path / "dossier.md")
    content = out.read_text(encoding="utf-8")
    assert "$20.99" in content


def test_f11_md_renders_valid_markdown_syntax(tmp_path: Path):
    engine = AuditEngine()
    res = engine.reconcile([], [], [], [])
    out = generate_markdown_dossier(res, tmp_path / "dossier.md")
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("# ")


# ---------------------------------------------------------------------------
# Feature 12: Standalone HTML Executive Dossier (5 tests)
# ---------------------------------------------------------------------------

def test_f12_html_is_self_contained_zero_cdn(tmp_path: Path):
    engine = AuditEngine()
    res = engine.reconcile([], [], [], [])
    out = generate_html_dossier(res, tmp_path / "dossier.html")
    html = out.read_text(encoding="utf-8")
    assert "http://" not in html
    assert "https://" not in html
    assert "<style>" in html


def test_f12_html_contains_kpi_cards(tmp_path: Path):
    engine = AuditEngine()
    res = engine.reconcile([], [], [], [])
    out = generate_html_dossier(res, tmp_path / "dossier.html")
    html = out.read_text(encoding="utf-8")
    assert "card-grid" in html
    assert "Total Claims" in html
    assert "Total Claim Amount" in html


def test_f12_html_contains_styled_tables(tmp_path: Path):
    engine = AuditEngine()
    res = engine.reconcile([], [], [], [])
    out = generate_html_dossier(res, tmp_path / "dossier.html")
    html = out.read_text(encoding="utf-8")
    assert "<table>" in html
    assert "<thead>" in html
    assert "<tbody>" in html


def test_f12_html_includes_status_badges(tmp_path: Path):
    engine = AuditEngine()
    ledger = [
        LedgerDetailRecord(
            date=date(2026, 9, 1), fnsku="X01", asin="B01", msku="M01", title="A",
            event_type="Adjustments", reference_id="R1", quantity=1, fulfillment_center="PHX3",
            disposition="SELLABLE", reason="M"
        )
    ]
    res = engine.reconcile(ledger, [], [], [], as_of_date=date(2026, 9, 10))
    out = generate_html_dossier(res, tmp_path / "dossier.html")
    html = out.read_text(encoding="utf-8")
    assert "badge-eligible" in html


def test_f12_html_contains_valid_html5_doctype(tmp_path: Path):
    engine = AuditEngine()
    res = engine.reconcile([], [], [], [])
    out = generate_html_dossier(res, tmp_path / "dossier.html")
    html = out.read_text(encoding="utf-8")
    assert html.startswith("<!DOCTYPE html>")
    assert "</html>" in html


# ---------------------------------------------------------------------------
# Feature 13: CLI & Python API Execution (5 tests)
# ---------------------------------------------------------------------------

def test_f13_engine_reconcile_returns_audit_result():
    engine = AuditEngine()
    res = engine.reconcile([], [], [], [])
    assert hasattr(res, "claims")
    assert hasattr(res, "summary")
    assert hasattr(res, "reconciled_at")


def test_f13_engine_accepts_as_of_date():
    engine = AuditEngine()
    target_dt = date(2026, 10, 15)
    res = engine.reconcile([], [], [], [], as_of_date=target_dt)
    assert res.reconciled_at.date() == target_dt


def test_f13_engine_summary_totals_match_claims_sum():
    engine = AuditEngine()
    ledger = [
        LedgerDetailRecord(
            date=date(2026, 9, 1), fnsku="X01", asin="B01", msku="M01", title="A",
            event_type="Adjustments", reference_id="R1", quantity=3, fulfillment_center="PHX3",
            disposition="SELLABLE", reason="M"
        )
    ]
    res = engine.reconcile(ledger, [], [], [], as_of_date=date(2026, 9, 10))
    sum_claim_amount = sum((c.claim_amount for c in res.claims), Decimal("0.00"))
    assert res.summary.total_discrepancy_amount == sum_claim_amount
    assert res.summary.total_discrepancy_units == sum(c.quantity for c in res.claims)


def test_f13_engine_handles_empty_input_lists():
    engine = AuditEngine()
    res = engine.reconcile([], [], [], [])
    assert res.summary.total_claims == 0
    assert res.summary.total_discrepancy_units == 0
    assert res.summary.total_discrepancy_amount == Decimal("0.00")


def test_f13_engine_preserves_audit_timestamp():
    engine = AuditEngine()
    d = date(2026, 7, 25)
    res = engine.reconcile([], [], [], [], as_of_date=d)
    assert res.reconciled_at == datetime(2026, 7, 25, 12, 0)
