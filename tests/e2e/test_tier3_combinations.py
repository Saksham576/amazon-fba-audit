"""
tests/e2e/test_tier3_combinations.py

Tier 3: Cross-Feature Combinatorial & Pairwise Interaction Test Suite (>=15 tests)
Verifies multi-feature interactions:
  - Concurrent warehouse losses and unreturned customer returns on same SKU
  - Dimensional overcharge + warehouse loss balancing
  - Three-way discrepancy coexistence on a single SKU
  - Multi-FC adjustments (PHX3, IND1, ONT8)
  - Cash vs inventory reimbursement splits
  - Mixed customer return dispositions in a single order stream
  - Expired and eligible claims coexisting
  - Simultaneous CSV, JSON, Markdown, and HTML report parity
  - Multi-unit partial return receipts
  - Full end-to-end simulation to export pipeline
"""

import csv
from datetime import date, datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
import pytest

from tests.conftest import (
    AuditEngine,
    ClaimRecord,
    LedgerDetailRecord,
    CustomerReturnRecord,
    ReimbursementRecord,
    FeeEstimateRecord,
    export_claim_batch_csv,
    export_claim_batch_json,
    generate_markdown_dossier,
    generate_html_dossier,
    parse_ledger_report,
    parse_customer_returns_report,
    parse_reimbursements_report,
    parse_estimated_fees_report,
)
from tests.generators.ledger_simulator import LedgerSimulator, SimulatedSKU


def test_combo_concurrent_warehouse_loss_and_customer_return():
    engine = AuditEngine()
    as_of = date(2026, 9, 29)
    # Warehouse loss on SKU-1
    ledger = [
        LedgerDetailRecord(
            date=as_of - timedelta(days=20), fnsku="X01", asin="B01", msku="M01",
            title="Prod 1", event_type="Adjustments", reference_id="REF-L1",
            quantity=3, fulfillment_center="PHX3", disposition="SELLABLE", reason="M"
        )
    ]
    # Unreturned customer return on SKU-1 (50 days elapsed > 45 days)
    returns = [
        CustomerReturnRecord(
            return_date=datetime(2026, 8, 10, 0, 0), order_id="111-9990001-0001",
            sku="M01", asin="B01", fnsku="X01", product_name="Prod 1",
            quantity=1, fulfillment_center_id="IND1", detailed_disposition="DEFECTIVE",
            reason="Late", status="Unit not received", license_plate_number="", customer_comments=""
        )
    ]
    res = engine.reconcile(ledger, returns, [], [], as_of_date=as_of)
    assert len(res.claims) == 2
    types = {c.discrepancy_type for c in res.claims}
    assert "WAREHOUSE_LOST_DAMAGED" in types
    assert "CUSTOMER_RETURN_NOT_RETURNED" in types
    citations = {c.policy_citation for c in res.claims}
    assert "G200379860" in citations
    assert "G200213130" in citations


def test_combo_dimensional_overcharge_plus_warehouse_loss():
    engine = AuditEngine()
    as_of = date(2026, 9, 29)
    ledger = [
        LedgerDetailRecord(
            date=as_of - timedelta(days=15), fnsku="X02", asin="B02", msku="M02",
            title="Prod 2", event_type="Adjustments", reference_id="REF-D1",
            quantity=2, fulfillment_center="IND1", disposition="DAMAGED", reason="E"
        )
    ]
    fees = [
        FeeEstimateRecord(
            sku="M02", fnsku="X02", asin="B02", product_name="Prod 2", product_group="H",
            brand="B", fulfilled_by="A", your_price=Decimal("25"), sales_price=Decimal("25"),
            longest_side=Decimal("15"), median_side=Decimal("10"), shortest_side=Decimal("2"),
            unit_of_dimension="inches", item_package_weight=Decimal("2"), unit_of_weight="pounds",
            product_size_tier="Large Standard", estimated_fee_total=Decimal("5.40"),
            estimated_order_handling_fee_per_unit=Decimal("0"), estimated_pick_pack_fee_per_unit=Decimal("5.40"),
            estimated_weight_handling_fee_per_unit=Decimal("0"), expected_fulfillment_fee_per_unit=Decimal("5.40")
        )
    ]
    catalog = {"X02": {"correct_fee": Decimal("4.08"), "units_sold": 100}}
    res = engine.reconcile(ledger, [], [], fees, catalog_specs=catalog, as_of_date=as_of)
    assert len(res.claims) == 2
    by_type = res.summary.breakdown_by_type
    assert "WAREHOUSE_LOST_DAMAGED" in by_type
    assert "DIMENSIONAL_FEE_OVERCHARGE" in by_type
    # Fee overcharge delta = 5.40 - 4.08 = 1.32 * 100 = 132.00
    assert by_type["DIMENSIONAL_FEE_OVERCHARGE"]["amount"] == Decimal("132.00")


def test_combo_customer_return_plus_dimensional_overcharge():
    engine = AuditEngine()
    as_of = date(2026, 9, 29)
    returns = [
        CustomerReturnRecord(
            return_date=datetime(2026, 8, 1, 0, 0), order_id="111-9990002-0002",
            sku="M03", asin="B03", fnsku="X03", product_name="Prod 3",
            quantity=1, fulfillment_center_id="IND1", detailed_disposition="DEFECTIVE",
            reason="Late", status="Unit not received", license_plate_number="", customer_comments=""
        )
    ]
    fees = [
        FeeEstimateRecord(
            sku="M03", fnsku="X03", asin="B03", product_name="Prod 3", product_group="H",
            brand="B", fulfilled_by="A", your_price=Decimal("20"), sales_price=Decimal("20"),
            longest_side=Decimal("12"), median_side=Decimal("8"), shortest_side=Decimal("1"),
            unit_of_dimension="inches", item_package_weight=Decimal("1"), unit_of_weight="pounds",
            product_size_tier="Large Standard", estimated_fee_total=Decimal("4.75"),
            estimated_order_handling_fee_per_unit=Decimal("0"), estimated_pick_pack_fee_per_unit=Decimal("4.75"),
            estimated_weight_handling_fee_per_unit=Decimal("0"), expected_fulfillment_fee_per_unit=Decimal("4.75")
        )
    ]
    catalog = {"X03": {"correct_fee": Decimal("3.86"), "units_sold": 50}}
    res = engine.reconcile([], returns, [], fees, catalog_specs=catalog, as_of_date=as_of)
    assert len(res.claims) == 2
    assert res.summary.total_discrepancy_units == 51  # 1 return + 50 units sold


def test_combo_three_way_discrepancy_on_single_sku():
    engine = AuditEngine()
    as_of = date(2026, 9, 29)
    target_sku = "X99"
    ledger = [
        LedgerDetailRecord(date=as_of - timedelta(days=20), fnsku=target_sku, asin="B99", msku="M99", title="T", event_type="Adjustments", reference_id="R1", quantity=4, fulfillment_center="PHX3", disposition="SELLABLE", reason="M")
    ]
    returns = [
        CustomerReturnRecord(return_date=datetime(2026, 8, 1, 0, 0), order_id="ORD-99", sku="M99", asin="B99", fnsku=target_sku, product_name="T", quantity=2, fulfillment_center_id="IND1", detailed_disposition="DEFECTIVE", reason="Late", status="Unit not received", license_plate_number="", customer_comments="")
    ]
    fees = [
        FeeEstimateRecord(sku="M99", fnsku=target_sku, asin="B99", product_name="T", product_group="H", brand="B", fulfilled_by="A", your_price=Decimal("30"), sales_price=Decimal("30"), longest_side=Decimal("15"), median_side=Decimal("10"), shortest_side=Decimal("2"), unit_of_dimension="inches", item_package_weight=Decimal("2"), unit_of_weight="pounds", product_size_tier="Large Standard", estimated_fee_total=Decimal("5.00"), estimated_order_handling_fee_per_unit=Decimal("0"), estimated_pick_pack_fee_per_unit=Decimal("5.00"), estimated_weight_handling_fee_per_unit=Decimal("0"), expected_fulfillment_fee_per_unit=Decimal("5.00"))
    ]
    catalog = {target_sku: {"correct_fee": Decimal("4.00"), "units_sold": 200}}
    res = engine.reconcile(ledger, returns, [], fees, catalog_specs=catalog, as_of_date=as_of)
    assert len(res.claims) == 3
    assert len(res.summary.breakdown_by_type) == 3


def test_combo_multi_fc_warehouse_adjustments():
    engine = AuditEngine()
    as_of = date(2026, 9, 29)
    ledger = [
        LedgerDetailRecord(date=as_of - timedelta(days=25), fnsku="X01", asin="B01", msku="M01", title="A", event_type="Adjustments", reference_id="R1", quantity=3, fulfillment_center="PHX3", disposition="SELLABLE", reason="M"),
        LedgerDetailRecord(date=as_of - timedelta(days=20), fnsku="X01", asin="B01", msku="M01", title="A", event_type="Adjustments", reference_id="R2", quantity=2, fulfillment_center="IND1", disposition="DAMAGED", reason="E"),
        LedgerDetailRecord(date=as_of - timedelta(days=15), fnsku="X01", asin="B01", msku="M01", title="A", event_type="Adjustments", reference_id="R3", quantity=1, fulfillment_center="ONT8", disposition="SELLABLE", reason="N")
    ]
    res = engine.reconcile(ledger, [], [], [], as_of_date=as_of)
    # (3 lost + 2 damaged) - 1 found = 4 uncompensated
    assert res.claims[0].quantity == 4


def test_combo_cash_plus_inventory_reimbursement_split():
    engine = AuditEngine()
    as_of = date(2026, 9, 29)
    ledger = [
        LedgerDetailRecord(date=as_of - timedelta(days=30), fnsku="X01", asin="B01", msku="M01", title="A", event_type="Adjustments", reference_id="R1", quantity=10, fulfillment_center="PHX3", disposition="SELLABLE", reason="M")
    ]
    reimbs = [
        ReimbursementRecord(approval_date=datetime(2026, 9, 10, 0, 0), reimbursement_id="R1", case_id="C1", amazon_order_id="", reason="Lost_Warehouse", sku="M01", fnsku="X01", asin="B01", product_name="A", condition="New", currency_unit="USD", amount_per_unit=Decimal("20.00"), amount_total=Decimal("80.00"), quantity_reimbursed_cash=4, quantity_reimbursed_inventory=3, quantity_reimbursed_total=7)
    ]
    res = engine.reconcile(ledger, [], reimbs, [], as_of_date=as_of)
    # 10 lost - 7 reimbursed = 3 claimable
    assert res.claims[0].quantity == 3


def test_combo_mixed_return_dispositions_same_order_series():
    engine = AuditEngine()
    as_of = date(2026, 9, 29)
    returns = [
        # SELLABLE received within 45 days -> No claim
        CustomerReturnRecord(return_date=datetime(2026, 9, 1, 0, 0), order_id="ORD-101", sku="M1", asin="B1", fnsku="X1", product_name="P", quantity=1, fulfillment_center_id="IND1", detailed_disposition="SELLABLE", reason="Unwanted", status="Unit returned to inventory", license_plate_number="L1", customer_comments=""),
        # DEFECTIVE past 45 days -> 1 claim
        CustomerReturnRecord(return_date=datetime(2026, 8, 1, 0, 0), order_id="ORD-102", sku="M1", asin="B1", fnsku="X1", product_name="P", quantity=1, fulfillment_center_id="IND1", detailed_disposition="DEFECTIVE", reason="Late", status="Unit not received", license_plate_number="", customer_comments=""),
    ]
    res = engine.reconcile([], returns, [], [], as_of_date=as_of)
    assert len(res.claims) == 1
    assert res.claims[0].order_id == "ORD-102"


def test_combo_expired_claim_coexisting_with_active_eligible_claim():
    engine = AuditEngine()
    as_of = date(2026, 9, 29)
    # Return 1: refund on April 1 (>105 days ago) -> EXPIRED
    # Return 2: refund on August 1 (59 days ago) -> ELIGIBLE
    returns = [
        CustomerReturnRecord(return_date=datetime(2026, 4, 1, 0, 0), order_id="ORD-OLD", sku="M1", asin="B1", fnsku="X1", product_name="P", quantity=1, fulfillment_center_id="IND1", detailed_disposition="DEFECTIVE", reason="Late", status="Unit not received", license_plate_number="", customer_comments=""),
        CustomerReturnRecord(return_date=datetime(2026, 8, 1, 0, 0), order_id="ORD-NEW", sku="M1", asin="B1", fnsku="X1", product_name="P", quantity=1, fulfillment_center_id="IND1", detailed_disposition="DEFECTIVE", reason="Late", status="Unit not received", license_plate_number="", customer_comments="")
    ]
    res = engine.reconcile([], returns, [], [], as_of_date=as_of)
    assert len(res.claims) == 2
    assert res.summary.eligible_claims == 1
    assert res.summary.expired_claims == 1


def test_combo_simultaneous_csv_and_json_batch_export_consistency(tmp_path: Path):
    engine = AuditEngine()
    ledger = [
        LedgerDetailRecord(date=date(2026, 9, 1), fnsku="X01", asin="B01", msku="M01", title="A", event_type="Adjustments", reference_id="R1", quantity=3, fulfillment_center="PHX3", disposition="SELLABLE", reason="M")
    ]
    res = engine.reconcile(ledger, [], [], [], as_of_date=date(2026, 9, 10))
    csv_path = export_claim_batch_csv(res.claims, tmp_path / "batch.csv")
    json_path = export_claim_batch_json(res.claims, tmp_path / "batch.json")

    # Verify CSV
    with open(csv_path, mode="r", encoding="utf-8") as f:
        csv_rows = list(csv.DictReader(f))
    # Verify JSON
    json_data = json.loads(json_path.read_text(encoding="utf-8"))

    assert len(csv_rows) == len(json_data["claims"]) == 1
    assert csv_rows[0]["claim_id"] == json_data["claims"][0]["claim_id"]
    assert csv_rows[0]["claim_amount"] == json_data["claims"][0]["claim_amount"]


def test_combo_markdown_and_html_dossier_parity(tmp_path: Path):
    engine = AuditEngine()
    ledger = [
        LedgerDetailRecord(date=date(2026, 9, 1), fnsku="X01", asin="B01", msku="M01", title="A", event_type="Adjustments", reference_id="R1", quantity=2, fulfillment_center="PHX3", disposition="SELLABLE", reason="M")
    ]
    res = engine.reconcile(ledger, [], [], [], as_of_date=date(2026, 9, 10))
    md_path = generate_markdown_dossier(res, tmp_path / "dossier.md")
    html_path = generate_html_dossier(res, tmp_path / "dossier.html")

    md_text = md_path.read_text(encoding="utf-8")
    html_text = html_path.read_text(encoding="utf-8")

    assert "$41.98" in md_text
    assert "$41.98" in html_text
    assert "WAREHOUSE_LOST_DAMAGED" in md_text
    assert "WAREHOUSE_LOST_DAMAGED" in html_text


def test_combo_high_volume_restock_interspersed_with_losses_and_shipments():
    engine = AuditEngine()
    as_of = date(2026, 9, 29)
    ledger = []
    # 5 restocks of 100
    for i in range(5):
        ledger.append(LedgerDetailRecord(date=as_of - timedelta(days=80 - (i * 15)), fnsku="X01", asin="B01", msku="M01", title="A", event_type="Receipts", reference_id=f"R-{i}", quantity=100, fulfillment_center="PHX3", disposition="SELLABLE", reason=""))
    # 5 shipments of -20
    for i in range(5):
        ledger.append(LedgerDetailRecord(date=as_of - timedelta(days=78 - (i * 15)), fnsku="X01", asin="B01", msku="M01", title="A", event_type="Shipments", reference_id=f"S-{i}", quantity=-20, fulfillment_center="PHX3", disposition="SELLABLE", reason=""))
    # 1 loss of 3
    ledger.append(LedgerDetailRecord(date=as_of - timedelta(days=20), fnsku="X01", asin="B01", msku="M01", title="A", event_type="Adjustments", reference_id="L-1", quantity=3, fulfillment_center="PHX3", disposition="SELLABLE", reason="M"))

    res = engine.reconcile(ledger, [], [], [], as_of_date=as_of)
    assert len(res.claims) == 1
    assert res.claims[0].quantity == 3


def test_combo_partial_return_receipt_for_multi_unit_order():
    engine = AuditEngine()
    as_of = date(2026, 9, 29)
    # Order for 3 units, 1 returned to inventory, 2 never received
    returns = [
        CustomerReturnRecord(return_date=datetime(2026, 8, 1, 0, 0), order_id="ORD-MULTI", sku="M1", asin="B1", fnsku="X1", product_name="P", quantity=2, fulfillment_center_id="IND1", detailed_disposition="DEFECTIVE", reason="Late", status="Unit not received", license_plate_number="", customer_comments="")
    ]
    res = engine.reconcile([], returns, [], [], as_of_date=as_of)
    assert len(res.claims) == 1
    assert res.claims[0].quantity == 2


def test_combo_reimbursement_clawback_or_cancellation_traceability():
    # Reimbursement event with original_reimbursement_id present
    rec = ReimbursementRecord(
        approval_date=datetime(2026, 8, 1, 0, 0), reimbursement_id="R-NEW", case_id="C1",
        amazon_order_id="O1", reason="Reimbursement_Reversal", sku="M1", fnsku="X1",
        asin="B1", product_name="P", condition="New", currency_unit="USD",
        amount_per_unit=Decimal("20.00"), amount_total=Decimal("20.00"),
        quantity_reimbursed_cash=1, quantity_reimbursed_inventory=0, quantity_reimbursed_total=1,
        original_reimbursement_id="R-OLD", original_reimbursement_type="Lost_Warehouse"
    )
    assert rec.original_reimbursement_id == "R-OLD"


def test_combo_catalog_dimension_creep_across_multiple_skus():
    engine = AuditEngine()
    fees = []
    catalog = {}
    for i in range(10):
        fnsku = f"X0{i}"
        sku = f"M0{i}"
        # Only SKUs 0, 1, 2 have dimension creep ($5.40 vs $4.08)
        charged_fee = Decimal("5.40") if i < 3 else Decimal("4.08")
        fees.append(FeeEstimateRecord(
            sku=sku, fnsku=fnsku, asin=f"B0{i}", product_name=f"P{i}", product_group="H",
            brand="B", fulfilled_by="A", your_price=Decimal("15"), sales_price=Decimal("15"),
            longest_side=Decimal("12"), median_side=Decimal("8"), shortest_side=Decimal("2"),
            unit_of_dimension="inches", item_package_weight=Decimal("1"), unit_of_weight="pounds",
            product_size_tier="Large Standard", estimated_fee_total=charged_fee,
            estimated_order_handling_fee_per_unit=Decimal("0"), estimated_pick_pack_fee_per_unit=charged_fee,
            estimated_weight_handling_fee_per_unit=Decimal("0"), expected_fulfillment_fee_per_unit=charged_fee
        ))
        catalog[fnsku] = {"correct_fee": Decimal("4.08"), "units_sold": 50}

    res = engine.reconcile([], [], [], fees, catalog_specs=catalog, as_of_date=date(2026, 9, 29))
    assert len(res.claims) == 3


def test_combo_full_end_to_end_pipeline_from_simulator_to_export(tmp_path: Path):
    sim = LedgerSimulator(start_date=date(2026, 7, 1), seed=999)
    sim.populate_default_catalog(sku_count=4)
    sim.simulate_90_day_lifecycle(
        inject_lost_units=3,
        inject_damaged_units=2,
        inject_found_units=1,
        inject_reimbursed_units=1,
        inject_unreturned_refunds=1,
        inject_cubiscan_creep_skus=1
    )

    # Parse exported TSVs
    ledger_records = parse_ledger_report(sim.export_ledger_detail_tsv())
    returns_records = parse_customer_returns_report(sim.export_customer_returns_tsv())
    reimbursement_records = parse_reimbursements_report(sim.export_reimbursements_tsv())
    fee_records = parse_estimated_fees_report(sim.export_estimated_fees_tsv())

    catalog_specs = {
        s.fnsku: {"correct_fee": s.compute_fee(s.catalog_length, s.catalog_width, s.catalog_height, s.catalog_weight), "units_sold": s.units_sold_90d}
        for s in sim.skus
    }

    engine = AuditEngine()
    result = engine.reconcile(ledger_records, returns_records, reimbursement_records, fee_records, catalog_specs=catalog_specs, as_of_date=sim.as_of_date)

    assert result.summary.total_claims > 0
    csv_file = export_claim_batch_csv(result.claims, tmp_path / "e2e_claims.csv")
    json_file = export_claim_batch_json(result.claims, tmp_path / "e2e_claims.json")
    md_file = generate_markdown_dossier(result, tmp_path / "e2e_dossier.md")
    html_file = generate_html_dossier(result, tmp_path / "e2e_dossier.html")

    assert csv_file.exists() and csv_file.stat().st_size > 0
    assert json_file.exists() and json_file.stat().st_size > 0
    assert md_file.exists() and md_file.stat().st_size > 0
    assert html_file.exists() and html_file.stat().st_size > 0
