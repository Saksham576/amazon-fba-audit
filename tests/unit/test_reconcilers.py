"""
Unit tests for core reconciliation modules.
"""

from datetime import date, timedelta
from decimal import Decimal
import pytest

from fba_audit.engine import (
    CustomerReturnReconciler,
    DimensionalOverchargeReconciler,
    WarehouseReconciler,
    compute_correct_fba_fee,
    compute_dimensional_weight,
    compute_size_tier,
)
from fba_audit.models import (
    CustomerReturnRecord,
    FeeEstimateRecord,
    LedgerDetailRecord,
    ReimbursementRecord,
)


def test_warehouse_reconciler_uncompensated_balance():
    as_of = date(2026, 9, 29)
    reconciler = WarehouseReconciler(as_of_date=as_of)

    # 10 lost, 2 damaged, 3 found, 1 reimbursed = 8 uncompensated
    records = [
        LedgerDetailRecord(date=as_of - timedelta(days=20), fnsku="SKU1", event_type="Lost", quantity=10),
        LedgerDetailRecord(date=as_of - timedelta(days=19), fnsku="SKU1", event_type="Damaged", quantity=2),
        LedgerDetailRecord(date=as_of - timedelta(days=15), fnsku="SKU1", event_type="Found", quantity=3),
    ]
    reimbursements = [
        ReimbursementRecord(
            approval_date=as_of - timedelta(days=10),
            reimbursement_id="REIMB1",
            fnsku="SKU1",
            quantity_reimbursed_total=1,
            reason="Lost:Warehouse",
        )
    ]
    prices = {"SKU1": Decimal("25.00")}

    claims = reconciler.reconcile(records, reimbursements, sku_prices=prices)
    assert len(claims) == 1
    c = claims[0]
    assert c.quantity == 8
    assert c.unit_price == Decimal("25.00")
    assert c.claim_amount == Decimal("200.00")
    assert c.claim_status == "ELIGIBLE"
    assert c.days_remaining == 40  # 60 - 20


def test_customer_return_reconciler_45_day_hold():
    as_of = date(2026, 9, 29)
    reconciler = CustomerReturnReconciler(as_of_date=as_of)

    # Under 45 days: 30 days elapsed -> no claim
    rec_recent = CustomerReturnRecord(
        return_date=as_of - timedelta(days=30),
        order_id="ORD-RECENT",
        fnsku="SKU1",
        quantity=1,
    )
    # Over 45 days: 60 days elapsed -> eligible claim
    rec_eligible = CustomerReturnRecord(
        return_date=as_of - timedelta(days=60),
        order_id="ORD-ELIGIBLE",
        fnsku="SKU2",
        quantity=2,
    )

    claims = reconciler.reconcile([rec_recent, rec_eligible], sku_prices={"SKU2": Decimal("15.00")})
    assert len(claims) == 1
    c = claims[0]
    assert c.order_id == "ORD-ELIGIBLE"
    assert c.quantity == 2
    assert c.claim_amount == Decimal("30.00")
    assert c.claim_status == "ELIGIBLE"
    assert c.days_remaining == 45  # 105 - 60


def test_dimensional_fee_calculations():
    # 10 x 8 x 2 inches, 1.5 lbs
    l, w, h, wt = Decimal("10.0"), Decimal("8.0"), Decimal("2.0"), Decimal("1.5")
    tier = compute_size_tier(l, w, h, wt)
    assert tier == "Large Standard"

    dim_w = compute_dimensional_weight(l, w, h)
    assert dim_w == Decimal("1.15")  # 160 / 139 = 1.15

    fee = compute_correct_fba_fee(l, w, h, wt)
    assert fee > Decimal("5.00")


def test_dimensional_overcharge_reconciler():
    as_of = date(2026, 9, 29)
    reconciler = DimensionalOverchargeReconciler(as_of_date=as_of)

    # Physical catalog specs: 10 x 8 x 0.5 inches, 0.4 lbs -> Small Standard fee $3.40
    catalog = {
        "SKU_DIM": {
            "length": "10.0",
            "width": "8.0",
            "height": "0.5",
            "weight": "0.4",
            "units_sold_90d": 50,
        }
    }
    # Amazon charged $5.40 (overcharge of $2.00 per unit)
    fee_records = [
        FeeEstimateRecord(
            sku="MSKU_DIM",
            fnsku="SKU_DIM",
            expected_fulfillment_fee_per_unit=Decimal("5.40"),
        )
    ]

    claims = reconciler.reconcile(fee_records, catalog_specs=catalog)
    assert len(claims) == 1
    c = claims[0]
    assert c.discrepancy_type == "DIMENSIONAL_FEE_OVERCHARGE"
    assert c.quantity == 50
    assert c.unit_price == Decimal("2.00")
    assert c.claim_amount == Decimal("100.00")
    assert c.policy_citation == "G21213"
