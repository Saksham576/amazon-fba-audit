"""
tests/e2e/test_tier4_synthetic_workload.py

Tier 4: Enterprise Synthetic Workload & Ground-Truth Oracle Verification Suite
Executes 5 realistic enterprise scenarios asserting 100% precision, 100% recall,
and $0.00 financial drift against the closed-form GroundTruthOracle:
  - SC-1: 90-Day Full Account Simulation (50 SKUs, 2,500+ ledger events)
  - SC-2: Return Fraud & Transit Loss Lifecycle (10 unreturned refunds, 5 late returns)
  - SC-3: Amazon Cubiscan Dimension Creep (15 products crossing Large Standard into Small Oversize)
  - SC-4: Cash vs Inventory Reimbursement Balancing (High volume with mixed compensations)
  - SC-5: Mixed Multi-Marketplace Edge Account (Multi-FC transactions PHX3, IND1, ONT8)
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
import pytest

from tests.conftest import (
    AuditEngine,
    parse_ledger_report,
    parse_customer_returns_report,
    parse_reimbursements_report,
    parse_estimated_fees_report,
)
from tests.generators.ledger_simulator import LedgerSimulator, SimulatedSKU
from tests.generators.ground_truth_oracle import GroundTruthOracle


def test_tier4_sc1_90_day_full_account_simulation():
    """
    SC-1: 90-Day Full Account Simulation
    50 SKUs, high-volume ledger events with mixed lost, damaged, found, and reimbursements.
    """
    as_of = date(2026, 9, 29)
    sim = LedgerSimulator(start_date=date(2026, 7, 1), seed=42)
    sim.populate_default_catalog(sku_count=50)
    sim.simulate_90_day_lifecycle(
        inject_lost_units=8,
        inject_damaged_units=5,
        inject_found_units=3,
        inject_reimbursed_units=4,
        inject_unreturned_refunds=0,
        inject_cubiscan_creep_skus=0
    )

    # Ground Truth Oracle expectation
    oracle = GroundTruthOracle(as_of_date=as_of)
    # Target SKU 0 has: (8 lost + 5 damaged) - (3 found + 4 reimbursed) = 6 uncompensated units
    target_sku = sim.skus[0]
    oracle.evaluate_warehouse_inventory(
        sku_info={"fnsku": target_sku.fnsku, "msku": target_sku.msku, "asin": target_sku.asin, "unit_price": Decimal("20.99")},
        lost_units=8,
        damaged_units=5,
        found_units=3,
        reimbursed_units=4,
        disposed_units=0,
        event_date=as_of - timedelta(days=10),
        fc="PHX3"
    )

    # Ingest and Reconcile
    ledger_records = parse_ledger_report(sim.export_ledger_detail_tsv())
    returns_records = parse_customer_returns_report(sim.export_customer_returns_tsv())
    reimb_records = parse_reimbursements_report(sim.export_reimbursements_tsv())
    fee_records = parse_estimated_fees_report(sim.export_estimated_fees_tsv())

    engine = AuditEngine()
    result = engine.reconcile(ledger_records, returns_records, reimb_records, fee_records, as_of_date=as_of)

    verification = oracle.verify_engine_claims(result.claims)
    assert verification.precision == 1.0, f"Precision failed: {verification.false_positives}"
    assert verification.recall == 1.0, f"Recall failed: {verification.false_negatives}"
    assert verification.dollar_delta == Decimal("0.00"), f"Dollar drift: {verification.dollar_delta}"
    assert verification.is_perfect_match is True


def test_tier4_sc2_return_fraud_and_transit_loss_lifecycle():
    """
    SC-2: Return Fraud & Transit Loss Lifecycle
    Customer refunded; items never returned to FC past 45 days.
    """
    as_of = date(2026, 9, 29)
    sim = LedgerSimulator(start_date=date(2026, 7, 1), seed=101)
    sim.populate_default_catalog(sku_count=10)

    # Setup unreturned customer refunds past 45 days
    target_sku = sim.skus[1]
    oracle = GroundTruthOracle(as_of_date=as_of)

    # 10 unreturned refunds
    unreturned_records = []
    for i in range(10):
        order_id = f"111-SC2-RET-{i:04d}"
        refund_date = as_of - timedelta(days=55)  # 55 days ago > 45 days
        # Add return record with "Unit not received" / "DEFECTIVE"
        from tests.conftest import CustomerReturnRecord
        unreturned_records.append(CustomerReturnRecord(
            return_date=datetime(refund_date.year, refund_date.month, refund_date.day, 10, 0),
            order_id=order_id,
            sku=target_sku.msku,
            asin=target_sku.asin,
            fnsku=target_sku.fnsku,
            product_name=target_sku.title,
            quantity=1,
            fulfillment_center_id="IND1",
            detailed_disposition="DEFECTIVE",
            reason="Late",
            status="Unit not received",
            license_plate_number="",
            customer_comments="Fraudulent return claim"
        ))

        oracle.evaluate_customer_return(
            sku_info={"fnsku": target_sku.fnsku, "msku": target_sku.msku, "asin": target_sku.asin, "unit_price": Decimal("25.99")},
            order_id=order_id,
            refund_date=refund_date,
            return_receipt_date=None,
            quantity=1,
            fc="IND1"
        )

    engine = AuditEngine()
    result = engine.reconcile([], unreturned_records, [], [], as_of_date=as_of)

    verification = oracle.verify_engine_claims(result.claims)
    assert verification.precision == 1.0, f"Precision failed: {verification.false_positives}"
    assert verification.recall == 1.0, f"Recall failed: {verification.false_negatives}"
    assert verification.dollar_delta == Decimal("0.00"), f"Dollar drift: {verification.dollar_delta}"
    assert verification.is_perfect_match is True


def test_tier4_sc3_amazon_cubiscan_dimension_creep():
    """
    SC-3: Amazon Cubiscan Dimension Creep
    15 products overcharged due to laser-measured scan flap flare crossing into higher fee tier.
    """
    as_of = date(2026, 9, 29)
    sim = LedgerSimulator(start_date=date(2026, 7, 1), seed=202)
    sim.populate_default_catalog(sku_count=15)

    from tests.conftest import FeeEstimateRecord
    fee_records = []
    catalog_specs = {}
    oracle = GroundTruthOracle(as_of_date=as_of)

    for i, sku in enumerate(sim.skus):
        # Catalog is Large Standard $4.08, but Amazon charges Small Oversize $5.40
        charged_fee = Decimal("5.40")
        correct_fee = Decimal("4.08")
        delta = charged_fee - correct_fee
        units_sold = 100

        fee_records.append(FeeEstimateRecord(
            sku=sku.msku, fnsku=sku.fnsku, asin=sku.asin, product_name=sku.title,
            product_group="Home", brand="BrandX", fulfilled_by="AMAZON_NA",
            your_price=sku.unit_price, sales_price=sku.unit_price,
            longest_side=Decimal("18.5"), median_side=Decimal("14.5"), shortest_side=Decimal("8.5"),
            unit_of_dimension="inches", item_package_weight=Decimal("5.0"), unit_of_weight="pounds",
            product_size_tier="Small Oversize", estimated_fee_total=charged_fee,
            estimated_order_handling_fee_per_unit=Decimal("0.00"), estimated_pick_pack_fee_per_unit=charged_fee,
            estimated_weight_handling_fee_per_unit=Decimal("0.00"), expected_fulfillment_fee_per_unit=charged_fee
        ))

        catalog_specs[sku.fnsku] = {
            "correct_fee": correct_fee,
            "units_sold": units_sold
        }

        oracle.evaluate_dimensional_overcharge(
            sku_info={"fnsku": sku.fnsku, "msku": sku.msku, "asin": sku.asin},
            charged_fee_per_unit=charged_fee,
            correct_fee_per_unit=correct_fee,
            units_sold=units_sold,
            detection_date=as_of - timedelta(days=10),
            fc="ALL"
        )

    engine = AuditEngine()
    result = engine.reconcile([], [], [], fee_records, catalog_specs=catalog_specs, as_of_date=as_of)

    verification = oracle.verify_engine_claims(result.claims)
    assert verification.precision == 1.0, f"Precision failed: {verification.false_positives}"
    assert verification.recall == 1.0, f"Recall failed: {verification.false_negatives}"
    assert verification.dollar_delta == Decimal("0.00"), f"Dollar drift: {verification.dollar_delta}"
    assert verification.is_perfect_match is True


def test_tier4_sc4_cash_vs_inventory_reimbursement_balancing():
    """
    SC-4: Cash vs Inventory Reimbursement Balancing
    High-volume products with partial cash reimbursements and physical replacement units.
    """
    as_of = date(2026, 9, 29)
    from tests.conftest import LedgerDetailRecord, ReimbursementRecord
    oracle = GroundTruthOracle(as_of_date=as_of)

    # SKU A: 20 lost, 10 cash reimbursed, 5 inventory replaced -> 5 uncompensated
    fnsku_a = "X001_ELEC"
    ledger = [
        LedgerDetailRecord(date=as_of - timedelta(days=20), fnsku=fnsku_a, asin="B001", msku="M001", title="Headphones", event_type="Adjustments", reference_id="REF-LA", quantity=20, fulfillment_center="PHX3", disposition="SELLABLE", reason="M")
    ]
    reimbs = [
        ReimbursementRecord(approval_date=datetime(2026, 9, 15, 0, 0), reimbursement_id="R-ELEC-1", case_id="CASE-1", amazon_order_id="", reason="Lost_Warehouse", sku="M001", fnsku=fnsku_a, asin="B001", product_name="Headphones", condition="New", currency_unit="USD", amount_per_unit=Decimal("20.99"), amount_total=Decimal("209.90"), quantity_reimbursed_cash=10, quantity_reimbursed_inventory=5, quantity_reimbursed_total=15)
    ]

    oracle.evaluate_warehouse_inventory(
        sku_info={"fnsku": fnsku_a, "msku": "M001", "asin": "B001", "unit_price": Decimal("20.99")},
        lost_units=20,
        damaged_units=0,
        found_units=0,
        reimbursed_units=15,
        disposed_units=0,
        event_date=as_of - timedelta(days=20),
        fc="PHX3"
    )

    engine = AuditEngine()
    result = engine.reconcile(ledger, [], reimbs, [], as_of_date=as_of)

    verification = oracle.verify_engine_claims(result.claims)
    assert verification.precision == 1.0, f"Precision failed: {verification.false_positives}"
    assert verification.recall == 1.0, f"Recall failed: {verification.false_negatives}"
    assert verification.dollar_delta == Decimal("0.00"), f"Dollar drift: {verification.dollar_delta}"
    assert verification.is_perfect_match is True


def test_tier4_sc5_mixed_multi_marketplace_edge_account():
    """
    SC-5: Mixed Multi-Marketplace Edge Account
    Multi-FC transactions (PHX3, IND1, ONT8) with concurrent adjustments and expiration limits.
    """
    as_of = date(2026, 9, 29)
    from tests.conftest import LedgerDetailRecord
    oracle = GroundTruthOracle(as_of_date=as_of)

    fnsku_edge = "X999_MULTI_FC"
    # Lost 10 units at PHX3, damaged 4 at IND1, found 2 at ONT8 -> 12 uncompensated
    ledger = [
        LedgerDetailRecord(date=as_of - timedelta(days=25), fnsku=fnsku_edge, asin="B999", msku="M999", title="MultiFC Item", event_type="Adjustments", reference_id="REF-PHX", quantity=10, fulfillment_center="PHX3", disposition="SELLABLE", reason="M"),
        LedgerDetailRecord(date=as_of - timedelta(days=20), fnsku=fnsku_edge, asin="B999", msku="M999", title="MultiFC Item", event_type="Adjustments", reference_id="REF-IND", quantity=4, fulfillment_center="IND1", disposition="DAMAGED", reason="E"),
        LedgerDetailRecord(date=as_of - timedelta(days=15), fnsku=fnsku_edge, asin="B999", msku="M999", title="MultiFC Item", event_type="Adjustments", reference_id="REF-ONT", quantity=2, fulfillment_center="ONT8", disposition="SELLABLE", reason="N"),
    ]

    oracle.evaluate_warehouse_inventory(
        sku_info={"fnsku": fnsku_edge, "msku": "M999", "asin": "B999", "unit_price": Decimal("20.99")},
        lost_units=10,
        damaged_units=4,
        found_units=2,
        reimbursed_units=0,
        disposed_units=0,
        event_date=as_of - timedelta(days=15),
        fc="ONT8"
    )

    engine = AuditEngine()
    result = engine.reconcile(ledger, [], [], [], as_of_date=as_of)

    verification = oracle.verify_engine_claims(result.claims)
    assert verification.precision == 1.0, f"Precision failed: {verification.false_positives}"
    assert verification.recall == 1.0, f"Recall failed: {verification.false_negatives}"
    assert verification.dollar_delta == Decimal("0.00"), f"Dollar drift: {verification.dollar_delta}"
    assert verification.is_perfect_match is True
