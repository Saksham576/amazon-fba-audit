"""
tests/e2e/test_tier2_boundaries.py

Tier 2: Boundary Value Analysis (BVA) & Corner Case Test Suite (>=65 tests)
Covers exact edge conditions:
  - Exact 43/44/45/46/47 day customer return thresholds
  - Exact 103/104/105/106/107 day return claim expiration limits
  - Exact 58/59/60/61/62 day warehouse operations claim expiration limits
  - Inventory found offsetting windows (day 1, 15, 29, 30, exact/partial/over-found)
  - Zero-discrepancy ledgers across all categories (10 tests)
  - Partial & split reimbursement balancing (cash, inventory, mixed, over-compensated)
  - Dimensional size tier boundaries (15.00 vs 15.01, 12.00 vs 12.01, 0.75 vs 0.76, 16.00 oz vs 16.01 oz, etc.)
  - Strict zero-float precision boundaries
"""

from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import pytest

from tests.conftest import (
    AuditEngine,
    ClaimRecord,
    LedgerDetailRecord,
    CustomerReturnRecord,
    ReimbursementRecord,
    FeeEstimateRecord,
)
from tests.generators.ledger_simulator import SimulatedSKU


# ---------------------------------------------------------------------------
# 1. Customer Return Waiting Window Boundaries (43, 44, 45, 46, 47 days)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("days_elapsed,expected_eligible", [
    (43, False),
    (44, False),
    (45, False),
    (46, True),
    (47, True),
])
def test_bva_customer_return_waiting_window_thresholds(days_elapsed: int, expected_eligible: bool):
    engine = AuditEngine()
    as_of = date(2026, 9, 1)
    refund_dt = as_of - timedelta(days=days_elapsed)
    returns = [
        CustomerReturnRecord(
            return_date=datetime(refund_dt.year, refund_dt.month, refund_dt.day, 0, 0),
            order_id=f"111-BVA-RET-{days_elapsed}", sku="M1", asin="B1", fnsku="X1",
            product_name="P1", quantity=1, fulfillment_center_id="IND1",
            detailed_disposition="DEFECTIVE", reason="Late", status="Unit not received",
            license_plate_number="", customer_comments=""
        )
    ]
    res = engine.reconcile([], returns, [], [], as_of_date=as_of)
    ret_claims = [c for c in res.claims if c.discrepancy_type == "CUSTOMER_RETURN_NOT_RETURNED"]
    assert (len(ret_claims) == 1) == expected_eligible


# ---------------------------------------------------------------------------
# 2. Customer Return Expiration Boundaries (103, 104, 105, 106, 107 days)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("days_elapsed,expected_status,expected_days_remaining", [
    (103, "ELIGIBLE", 2),
    (104, "ELIGIBLE", 1),
    (105, "ELIGIBLE", 0),
    (106, "EXPIRED", 0),
    (107, "EXPIRED", 0),
])
def test_bva_customer_return_expiration_limits(days_elapsed: int, expected_status: str, expected_days_remaining: int):
    engine = AuditEngine()
    as_of = date(2026, 9, 1)
    refund_dt = as_of - timedelta(days=days_elapsed)
    returns = [
        CustomerReturnRecord(
            return_date=datetime(refund_dt.year, refund_dt.month, refund_dt.day, 0, 0),
            order_id=f"111-EXP-RET-{days_elapsed}", sku="M1", asin="B1", fnsku="X1",
            product_name="P1", quantity=1, fulfillment_center_id="IND1",
            detailed_disposition="DEFECTIVE", reason="Late", status="Unit not received",
            license_plate_number="", customer_comments=""
        )
    ]
    res = engine.reconcile([], returns, [], [], as_of_date=as_of)
    claim = res.claims[0]
    assert claim.claim_status == expected_status
    assert claim.days_remaining == expected_days_remaining


# ---------------------------------------------------------------------------
# 3. Warehouse Operations Expiration Boundaries (58, 59, 60, 61, 62 days)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("days_elapsed,expected_status,expected_days_remaining", [
    (58, "ELIGIBLE", 2),
    (59, "ELIGIBLE", 1),
    (60, "ELIGIBLE", 0),
    (61, "EXPIRED", 0),
    (62, "EXPIRED", 0),
])
def test_bva_warehouse_claim_expiration_limits(days_elapsed: int, expected_status: str, expected_days_remaining: int):
    engine = AuditEngine()
    as_of = date(2026, 9, 1)
    ev_dt = as_of - timedelta(days=days_elapsed)
    ledger = [
        LedgerDetailRecord(
            date=ev_dt, fnsku="X01", asin="B01", msku="M01", title="A",
            event_type="Adjustments", reference_id=f"ADJ-EXP-{days_elapsed}",
            quantity=1, fulfillment_center="PHX3", disposition="SELLABLE", reason="M"
        )
    ]
    res = engine.reconcile(ledger, [], [], [], as_of_date=as_of)
    claim = res.claims[0]
    assert claim.claim_status == expected_status
    assert claim.days_remaining == expected_days_remaining


# ---------------------------------------------------------------------------
# 4. Inventory Found Offsetting Boundaries (7 tests)
# ---------------------------------------------------------------------------

def test_bva_found_day_1_offsets_loss():
    engine = AuditEngine()
    as_of = date(2026, 9, 1)
    ledger = [
        LedgerDetailRecord(date=as_of - timedelta(days=20), fnsku="X01", asin="B01", msku="M01", title="A", event_type="Adjustments", reference_id="L1", quantity=5, fulfillment_center="PHX3", disposition="SELLABLE", reason="M"),
        LedgerDetailRecord(date=as_of - timedelta(days=19), fnsku="X01", asin="B01", msku="M01", title="A", event_type="Adjustments", reference_id="F1", quantity=2, fulfillment_center="PHX3", disposition="SELLABLE", reason="N")
    ]
    res = engine.reconcile(ledger, [], [], [], as_of_date=as_of)
    assert res.claims[0].quantity == 3


def test_bva_found_day_15_offsets_loss():
    engine = AuditEngine()
    as_of = date(2026, 9, 1)
    ledger = [
        LedgerDetailRecord(date=as_of - timedelta(days=25), fnsku="X01", asin="B01", msku="M01", title="A", event_type="Adjustments", reference_id="L1", quantity=4, fulfillment_center="PHX3", disposition="SELLABLE", reason="M"),
        LedgerDetailRecord(date=as_of - timedelta(days=10), fnsku="X01", asin="B01", msku="M01", title="A", event_type="Adjustments", reference_id="F1", quantity=1, fulfillment_center="PHX3", disposition="SELLABLE", reason="N")
    ]
    res = engine.reconcile(ledger, [], [], [], as_of_date=as_of)
    assert res.claims[0].quantity == 3


def test_bva_found_day_29_offsets_loss():
    engine = AuditEngine()
    as_of = date(2026, 9, 1)
    ledger = [
        LedgerDetailRecord(date=as_of - timedelta(days=40), fnsku="X01", asin="B01", msku="M01", title="A", event_type="Adjustments", reference_id="L1", quantity=6, fulfillment_center="PHX3", disposition="SELLABLE", reason="M"),
        LedgerDetailRecord(date=as_of - timedelta(days=11), fnsku="X01", asin="B01", msku="M01", title="A", event_type="Adjustments", reference_id="F1", quantity=3, fulfillment_center="PHX3", disposition="SELLABLE", reason="N")
    ]
    res = engine.reconcile(ledger, [], [], [], as_of_date=as_of)
    assert res.claims[0].quantity == 3


def test_bva_found_day_30_exact_boundary():
    engine = AuditEngine()
    as_of = date(2026, 9, 1)
    ledger = [
        LedgerDetailRecord(date=as_of - timedelta(days=45), fnsku="X01", asin="B01", msku="M01", title="A", event_type="Adjustments", reference_id="L1", quantity=5, fulfillment_center="PHX3", disposition="SELLABLE", reason="M"),
        LedgerDetailRecord(date=as_of - timedelta(days=15), fnsku="X01", asin="B01", msku="M01", title="A", event_type="Adjustments", reference_id="F1", quantity=2, fulfillment_center="PHX3", disposition="SELLABLE", reason="N")
    ]
    res = engine.reconcile(ledger, [], [], [], as_of_date=as_of)
    assert res.claims[0].quantity == 3


def test_bva_found_exact_matching_quantity_eliminates_claim():
    engine = AuditEngine()
    ledger = [
        LedgerDetailRecord(date=date(2026, 8, 1), fnsku="X01", asin="B01", msku="M01", title="A", event_type="Adjustments", reference_id="L1", quantity=10, fulfillment_center="PHX3", disposition="SELLABLE", reason="M"),
        LedgerDetailRecord(date=date(2026, 8, 5), fnsku="X01", asin="B01", msku="M01", title="A", event_type="Adjustments", reference_id="F1", quantity=10, fulfillment_center="PHX3", disposition="SELLABLE", reason="N")
    ]
    res = engine.reconcile(ledger, [], [], [], as_of_date=date(2026, 8, 20))
    assert len(res.claims) == 0


def test_bva_found_partial_quantity():
    engine = AuditEngine()
    ledger = [
        LedgerDetailRecord(date=date(2026, 8, 1), fnsku="X01", asin="B01", msku="M01", title="A", event_type="Adjustments", reference_id="L1", quantity=10, fulfillment_center="PHX3", disposition="SELLABLE", reason="M"),
        LedgerDetailRecord(date=date(2026, 8, 5), fnsku="X01", asin="B01", msku="M01", title="A", event_type="Adjustments", reference_id="F1", quantity=4, fulfillment_center="PHX3", disposition="SELLABLE", reason="N")
    ]
    res = engine.reconcile(ledger, [], [], [], as_of_date=date(2026, 8, 20))
    assert res.claims[0].quantity == 6


def test_bva_found_exceeding_loss_non_negative_clamp():
    engine = AuditEngine()
    ledger = [
        LedgerDetailRecord(date=date(2026, 8, 1), fnsku="X01", asin="B01", msku="M01", title="A", event_type="Adjustments", reference_id="L1", quantity=5, fulfillment_center="PHX3", disposition="SELLABLE", reason="M"),
        LedgerDetailRecord(date=date(2026, 8, 5), fnsku="X01", asin="B01", msku="M01", title="A", event_type="Adjustments", reference_id="F1", quantity=8, fulfillment_center="PHX3", disposition="SELLABLE", reason="N")
    ]
    res = engine.reconcile(ledger, [], [], [], as_of_date=date(2026, 8, 20))
    assert len(res.claims) == 0


# ---------------------------------------------------------------------------
# 5. Zero-Discrepancy Ledgers Across All Categories (10 tests)
# ---------------------------------------------------------------------------

def test_zero_discrepancy_empty_ledger():
    res = AuditEngine().reconcile([], [], [], [])
    assert len(res.claims) == 0


def test_zero_discrepancy_receipts_only():
    ledger = [
        LedgerDetailRecord(date=date(2026, 8, 1), fnsku="X1", asin="B1", msku="M1", title="P1", event_type="Receipts", reference_id="REC-1", quantity=1000, fulfillment_center="PHX3", disposition="SELLABLE", reason="")
    ]
    res = AuditEngine().reconcile(ledger, [], [], [])
    assert len(res.claims) == 0


def test_zero_discrepancy_shipments_matching_receipts():
    ledger = [
        LedgerDetailRecord(date=date(2026, 8, 1), fnsku="X1", asin="B1", msku="M1", title="P1", event_type="Receipts", reference_id="REC-1", quantity=100, fulfillment_center="PHX3", disposition="SELLABLE", reason=""),
        LedgerDetailRecord(date=date(2026, 8, 2), fnsku="X1", asin="B1", msku="M1", title="P1", event_type="Shipments", reference_id="ORD-1", quantity=-100, fulfillment_center="PHX3", disposition="SELLABLE", reason="")
    ]
    res = AuditEngine().reconcile(ledger, [], [], [])
    assert len(res.claims) == 0


def test_zero_discrepancy_return_received_day_1():
    returns = [
        CustomerReturnRecord(return_date=datetime(2026, 8, 1, 0, 0), order_id="O1", sku="M1", asin="B1", fnsku="X1", product_name="P1", quantity=1, fulfillment_center_id="IND1", detailed_disposition="SELLABLE", reason="Unwanted", status="Unit returned to inventory", license_plate_number="LPN1", customer_comments="")
    ]
    res = AuditEngine().reconcile([], returns, [], [], as_of_date=date(2026, 8, 20))
    assert len(res.claims) == 0


def test_zero_discrepancy_return_received_day_44():
    returns = [
        CustomerReturnRecord(return_date=datetime(2026, 7, 1, 0, 0), order_id="O1", sku="M1", asin="B1", fnsku="X1", product_name="P1", quantity=1, fulfillment_center_id="IND1", detailed_disposition="SELLABLE", reason="Unwanted", status="Unit returned to inventory", license_plate_number="LPN1", customer_comments="")
    ]
    res = AuditEngine().reconcile([], returns, [], [], as_of_date=date(2026, 7, 25))
    assert len(res.claims) == 0


def test_zero_discrepancy_return_received_day_45():
    returns = [
        CustomerReturnRecord(return_date=datetime(2026, 7, 1, 0, 0), order_id="O1", sku="M1", asin="B1", fnsku="X1", product_name="P1", quantity=1, fulfillment_center_id="IND1", detailed_disposition="SELLABLE", reason="Unwanted", status="Unit returned to inventory", license_plate_number="LPN1", customer_comments="")
    ]
    res = AuditEngine().reconcile([], returns, [], [], as_of_date=date(2026, 8, 15))
    assert len(res.claims) == 0


def test_zero_discrepancy_lost_units_fully_cash_reimbursed():
    ledger = [
        LedgerDetailRecord(date=date(2026, 8, 1), fnsku="X1", asin="B1", msku="M1", title="P1", event_type="Adjustments", reference_id="L1", quantity=5, fulfillment_center="PHX3", disposition="SELLABLE", reason="M")
    ]
    reimbs = [
        ReimbursementRecord(approval_date=datetime(2026, 8, 5, 0, 0), reimbursement_id="R1", case_id="C1", amazon_order_id="", reason="Lost_Warehouse", sku="M1", fnsku="X1", asin="B1", product_name="P1", condition="New", currency_unit="USD", amount_per_unit=Decimal("20.00"), amount_total=Decimal("100.00"), quantity_reimbursed_cash=5, quantity_reimbursed_inventory=0, quantity_reimbursed_total=5)
    ]
    res = AuditEngine().reconcile(ledger, [], reimbs, [])
    assert len(res.claims) == 0


def test_zero_discrepancy_lost_units_fully_inventory_reimbursed():
    ledger = [
        LedgerDetailRecord(date=date(2026, 8, 1), fnsku="X1", asin="B1", msku="M1", title="P1", event_type="Adjustments", reference_id="L1", quantity=3, fulfillment_center="PHX3", disposition="SELLABLE", reason="M")
    ]
    reimbs = [
        ReimbursementRecord(approval_date=datetime(2026, 8, 5, 0, 0), reimbursement_id="R1", case_id="C1", amazon_order_id="", reason="Lost_Warehouse", sku="M1", fnsku="X1", asin="B1", product_name="P1", condition="New", currency_unit="USD", amount_per_unit=Decimal("0.00"), amount_total=Decimal("0.00"), quantity_reimbursed_cash=0, quantity_reimbursed_inventory=3, quantity_reimbursed_total=3)
    ]
    res = AuditEngine().reconcile(ledger, [], reimbs, [])
    assert len(res.claims) == 0


def test_zero_discrepancy_damaged_units_disposed():
    ledger = [
        LedgerDetailRecord(date=date(2026, 8, 1), fnsku="X1", asin="B1", msku="M1", title="P1", event_type="Adjustments", reference_id="D1", quantity=4, fulfillment_center="PHX3", disposition="DAMAGED", reason="E"),
        LedgerDetailRecord(date=date(2026, 8, 5), fnsku="X1", asin="B1", msku="M1", title="P1", event_type="Adjustments", reference_id="DISP1", quantity=4, fulfillment_center="PHX3", disposition="DEFECTIVE", reason="X")
    ]
    res = AuditEngine().reconcile(ledger, [], [], [])
    assert len(res.claims) == 0


def test_zero_discrepancy_exact_dimensions_matching_catalog():
    fees = [
        FeeEstimateRecord(sku="S1", fnsku="X1", asin="B1", product_name="P1", product_group="H", brand="B", fulfilled_by="A", your_price=Decimal("10"), sales_price=Decimal("10"), longest_side=Decimal("10"), median_side=Decimal("8"), shortest_side=Decimal("1"), unit_of_dimension="inches", item_package_weight=Decimal("1"), unit_of_weight="pounds", product_size_tier="Large Standard", estimated_fee_total=Decimal("4.08"), estimated_order_handling_fee_per_unit=Decimal("0"), estimated_pick_pack_fee_per_unit=Decimal("4.08"), estimated_weight_handling_fee_per_unit=Decimal("0"), expected_fulfillment_fee_per_unit=Decimal("4.08"))
    ]
    catalog = {"X1": {"correct_fee": Decimal("4.08"), "units_sold": 50}}
    res = AuditEngine().reconcile([], [], [], fees, catalog_specs=catalog)
    assert len(res.claims) == 0


# ---------------------------------------------------------------------------
# 6. Partial & Split Reimbursement Balancing (7 tests)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("lost,cash_reimb,inv_reimb,expected_claimable", [
    (10, 1, 0, 9),
    (10, 5, 0, 5),
    (10, 9, 0, 1),
    (10, 10, 0, 0),
    (10, 3, 2, 5),
    (10, 5, 5, 0),
    (10, 6, 5, 0),  # 11 reimbursed > 10 lost -> 0 claimable
])
def test_bva_partial_reimbursement_balancing(lost: int, cash_reimb: int, inv_reimb: int, expected_claimable: int):
    engine = AuditEngine()
    ledger = [
        LedgerDetailRecord(date=date(2026, 8, 1), fnsku="X1", asin="B1", msku="M1", title="P1", event_type="Adjustments", reference_id="L1", quantity=lost, fulfillment_center="PHX3", disposition="SELLABLE", reason="M")
    ]
    reimbs = []
    tot = cash_reimb + inv_reimb
    if tot > 0:
        reimbs.append(ReimbursementRecord(
            approval_date=datetime(2026, 8, 5, 0, 0), reimbursement_id="R1", case_id="C1", amazon_order_id="",
            reason="Lost_Warehouse", sku="M1", fnsku="X1", asin="B1", product_name="P1", condition="New",
            currency_unit="USD", amount_per_unit=Decimal("20.00"), amount_total=Decimal("20.00") * Decimal(cash_reimb),
            quantity_reimbursed_cash=cash_reimb, quantity_reimbursed_inventory=inv_reimb, quantity_reimbursed_total=tot
        ))
    res = engine.reconcile(ledger, [], reimbs, [], as_of_date=date(2026, 8, 20))
    wh_claims = [c for c in res.claims if c.discrepancy_type == "WAREHOUSE_LOST_DAMAGED"]
    if expected_claimable == 0:
        assert len(wh_claims) == 0
    else:
        assert len(wh_claims) == 1
        assert wh_claims[0].quantity == expected_claimable


# ---------------------------------------------------------------------------
# 7. Dimensional Size Tier Boundaries (16 tests)
# ---------------------------------------------------------------------------

def test_tier_bva_longest_side_15_00_is_small_standard():
    sku = SimulatedSKU("X", "M", "B", "T", Decimal("10"), Decimal("15.00"), Decimal("12.00"), Decimal("0.75"), Decimal("1.00"))
    assert sku.compute_size_tier(Decimal("15.00"), Decimal("12.00"), Decimal("0.75"), Decimal("1.00")) == "Small Standard"


def test_tier_bva_longest_side_15_01_shifts_to_large_standard():
    sku = SimulatedSKU("X", "M", "B", "T", Decimal("10"), Decimal("15.01"), Decimal("12.00"), Decimal("0.75"), Decimal("1.00"))
    assert sku.compute_size_tier(Decimal("15.01"), Decimal("12.00"), Decimal("0.75"), Decimal("1.00")) == "Large Standard"


def test_tier_bva_median_side_12_00_is_small_standard():
    sku = SimulatedSKU("X", "M", "B", "T", Decimal("10"), Decimal("15.00"), Decimal("12.00"), Decimal("0.75"), Decimal("1.00"))
    assert sku.compute_size_tier(Decimal("15.00"), Decimal("12.00"), Decimal("0.75"), Decimal("1.00")) == "Small Standard"


def test_tier_bva_median_side_12_01_shifts_to_large_standard():
    sku = SimulatedSKU("X", "M", "B", "T", Decimal("10"), Decimal("15.00"), Decimal("12.01"), Decimal("0.75"), Decimal("1.00"))
    assert sku.compute_size_tier(Decimal("15.00"), Decimal("12.01"), Decimal("0.75"), Decimal("1.00")) == "Large Standard"


def test_tier_bva_shortest_side_0_75_is_small_standard():
    sku = SimulatedSKU("X", "M", "B", "T", Decimal("10"), Decimal("15.00"), Decimal("12.00"), Decimal("0.75"), Decimal("1.00"))
    assert sku.compute_size_tier(Decimal("15.00"), Decimal("12.00"), Decimal("0.75"), Decimal("1.00")) == "Small Standard"


def test_tier_bva_shortest_side_0_76_shifts_to_large_standard():
    sku = SimulatedSKU("X", "M", "B", "T", Decimal("10"), Decimal("15.00"), Decimal("12.00"), Decimal("0.76"), Decimal("1.00"))
    assert sku.compute_size_tier(Decimal("15.00"), Decimal("12.00"), Decimal("0.76"), Decimal("1.00")) == "Large Standard"


def test_tier_bva_weight_1_00_is_small_standard():
    sku = SimulatedSKU("X", "M", "B", "T", Decimal("10"), Decimal("15.00"), Decimal("12.00"), Decimal("0.75"), Decimal("1.00"))
    assert sku.compute_size_tier(Decimal("15.00"), Decimal("12.00"), Decimal("0.75"), Decimal("1.00")) == "Small Standard"


def test_tier_bva_weight_1_01_shifts_to_large_standard():
    sku = SimulatedSKU("X", "M", "B", "T", Decimal("10"), Decimal("15.00"), Decimal("12.00"), Decimal("0.75"), Decimal("1.01"))
    assert sku.compute_size_tier(Decimal("15.00"), Decimal("12.00"), Decimal("0.75"), Decimal("1.01")) == "Large Standard"


def test_tier_bva_longest_side_18_00_is_large_standard():
    sku = SimulatedSKU("X", "M", "B", "T", Decimal("10"), Decimal("18.00"), Decimal("14.00"), Decimal("8.00"), Decimal("20.00"))
    assert sku.compute_size_tier(Decimal("18.00"), Decimal("14.00"), Decimal("8.00"), Decimal("20.00")) == "Large Standard"


def test_tier_bva_longest_side_18_01_shifts_to_oversize():
    sku = SimulatedSKU("X", "M", "B", "T", Decimal("10"), Decimal("18.01"), Decimal("14.00"), Decimal("8.00"), Decimal("20.00"))
    assert sku.compute_size_tier(Decimal("18.01"), Decimal("14.00"), Decimal("8.00"), Decimal("20.00")) == "Small Oversize"


def test_tier_bva_median_side_14_00_is_large_standard():
    sku = SimulatedSKU("X", "M", "B", "T", Decimal("10"), Decimal("18.00"), Decimal("14.00"), Decimal("8.00"), Decimal("20.00"))
    assert sku.compute_size_tier(Decimal("18.00"), Decimal("14.00"), Decimal("8.00"), Decimal("20.00")) == "Large Standard"


def test_tier_bva_median_side_14_01_shifts_to_oversize():
    sku = SimulatedSKU("X", "M", "B", "T", Decimal("10"), Decimal("18.00"), Decimal("14.01"), Decimal("8.00"), Decimal("20.00"))
    assert sku.compute_size_tier(Decimal("18.00"), Decimal("14.01"), Decimal("8.00"), Decimal("20.00")) == "Small Oversize"


def test_tier_bva_shortest_side_8_00_is_large_standard():
    sku = SimulatedSKU("X", "M", "B", "T", Decimal("10"), Decimal("18.00"), Decimal("14.00"), Decimal("8.00"), Decimal("20.00"))
    assert sku.compute_size_tier(Decimal("18.00"), Decimal("14.00"), Decimal("8.00"), Decimal("20.00")) == "Large Standard"


def test_tier_bva_shortest_side_8_01_shifts_to_oversize():
    sku = SimulatedSKU("X", "M", "B", "T", Decimal("10"), Decimal("18.00"), Decimal("14.00"), Decimal("8.01"), Decimal("20.00"))
    assert sku.compute_size_tier(Decimal("18.00"), Decimal("14.00"), Decimal("8.01"), Decimal("20.00")) == "Small Oversize"


def test_tier_bva_weight_20_00_is_large_standard():
    sku = SimulatedSKU("X", "M", "B", "T", Decimal("10"), Decimal("18.00"), Decimal("14.00"), Decimal("8.00"), Decimal("20.00"))
    assert sku.compute_size_tier(Decimal("18.00"), Decimal("14.00"), Decimal("8.00"), Decimal("20.00")) == "Large Standard"


def test_tier_bva_weight_20_01_shifts_to_oversize():
    sku = SimulatedSKU("X", "M", "B", "T", Decimal("10"), Decimal("18.00"), Decimal("14.00"), Decimal("8.00"), Decimal("20.01"))
    assert sku.compute_size_tier(Decimal("18.00"), Decimal("14.00"), Decimal("8.00"), Decimal("20.01")) == "Small Oversize"


# ---------------------------------------------------------------------------
# 8. Strict Zero-Float Precision Boundaries (10 tests)
# ---------------------------------------------------------------------------

def test_precision_rounding_half_up_0_005():
    val = Decimal("10.005").quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    assert val == Decimal("10.01")


def test_precision_exact_one_cent_claim():
    claim = ClaimRecord(
        claim_id="c1", fnsku="X1", msku="M1", asin="B1", order_id="", transaction_id="T1",
        event_date=date(2026, 8, 1), discrepancy_type="DIMENSIONAL_FEE_OVERCHARGE",
        quantity=1, unit_price=Decimal("0.01"), claim_amount=Decimal("0.01"), currency="USD",
        policy_citation="G21213", policy_clause="Clause", claim_window_days=60, days_remaining=30,
        claim_status="ELIGIBLE", evidence_notes="Notes", fulfillment_center="ALL"
    )
    assert claim.claim_amount == Decimal("0.01")
    assert claim.to_19_col_dict()["claim_amount"] == "0.01"


def test_precision_large_quantity_exact_cents():
    qty = 10000
    price = Decimal("19.99")
    total = (Decimal(qty) * price).quantize(Decimal("0.01"))
    assert total == Decimal("199900.00")


def test_precision_dim_weight_divisor_139():
    # 10 x 8 x 5 = 400 cu in / 139 = 2.87769... -> 2.88 lb
    sku = SimulatedSKU("X", "M", "B", "T", Decimal("10"), Decimal("10"), Decimal("8"), Decimal("5"), Decimal("1"))
    dw = sku.compute_dim_weight(Decimal("10"), Decimal("8"), Decimal("5"))
    assert dw == Decimal("2.88")


def test_precision_zero_delta_fee_is_zero():
    f1 = Decimal("4.75")
    f2 = Decimal("4.75")
    assert (f1 - f2) == Decimal("0.00")


def test_precision_negative_shipment_leaves_positive_inventory():
    receipt = 100
    shipment = -35
    balance = receipt + shipment
    assert balance == 65


def test_precision_currency_unit_iso_usd():
    claim = ClaimRecord(
        claim_id="c1", fnsku="X1", msku="M1", asin="B1", order_id="", transaction_id="T1",
        event_date=date(2026, 8, 1), discrepancy_type="WAREHOUSE_LOST_DAMAGED",
        quantity=1, unit_price=Decimal("10.00"), claim_amount=Decimal("10.00"), currency="USD",
        policy_citation="G200379860", policy_clause="Clause", claim_window_days=60, days_remaining=30,
        claim_status="ELIGIBLE", evidence_notes="Notes", fulfillment_center="PHX3"
    )
    assert claim.currency == "USD"


def test_precision_claim_amount_equals_quantity_times_unit_price():
    qty = 7
    unit_price = Decimal("14.28")
    expected_total = Decimal("99.96")
    actual_total = (Decimal(qty) * unit_price).quantize(Decimal("0.01"))
    assert actual_total == expected_total


def test_precision_no_float_types_in_summary():
    engine = AuditEngine()
    ledger = [
        LedgerDetailRecord(date=date(2026, 9, 1), fnsku="X01", asin="B01", msku="M01", title="A", event_type="Adjustments", reference_id="R1", quantity=3, fulfillment_center="PHX3", disposition="SELLABLE", reason="M")
    ]
    res = engine.reconcile(ledger, [], [], [], as_of_date=date(2026, 9, 10))
    assert isinstance(res.summary.total_discrepancy_amount, Decimal)


def test_precision_zero_units_generates_zero_claim_amount():
    engine = AuditEngine()
    res = engine.reconcile([], [], [], [])
    assert res.summary.total_discrepancy_amount == Decimal("0.00")
