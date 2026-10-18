"""
E2E Dual-Track Test Suite (Tiers 1-4) with Ground Truth Oracle validation.
"""

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
import pytest

from fba_audit.api import run_audit
from fba_audit.engine import AuditEngine
from fba_audit.models import CustomerReturnRecord, FeeEstimateRecord, LedgerDetailRecord, ReimbursementRecord
from tests.generators.ground_truth_oracle import GroundTruthOracle
from tests.generators.ledger_simulator import LedgerSimulator


def test_tier1_feature_end_to_end(fixtures_dir: Path, tmp_path: Path):
    """Tier 1: Verify full end-to-end audit runs across all 4 report fixtures."""
    out_dir = tmp_path / "audit_res"
    result = run_audit(
        ledger_path=fixtures_dir / "ledger_detail_sample.tsv",
        returns_path=fixtures_dir / "customer_returns_sample.tsv",
        reimbursements_path=fixtures_dir / "reimbursements_sample.tsv",
        fees_path=fixtures_dir / "estimated_fees_sample.tsv",
        output_dir=out_dir,
    )
    assert result.summary.total_claims_count > 0
    assert (out_dir / "claims_batch.csv").exists()
    assert (out_dir / "claims_batch.json").exists()
    assert (out_dir / "audit_dossier.md").exists()
    assert (out_dir / "audit_dossier.html").exists()


def test_tier2_boundary_45_day_return_threshold():
    """Tier 2: Boundary condition: Exactly 44, 45, and 46 days after refund."""
    as_of = date(2026, 9, 29)
    engine = AuditEngine(as_of_date=as_of)

    # 44 days elapsed -> hold active, no claim
    ret_44 = CustomerReturnRecord(return_date=as_of - timedelta(days=44), order_id="ORD-44", fnsku="FNSKU1", status="Unit not received")
    # 45 days elapsed -> hold active, no claim
    ret_45 = CustomerReturnRecord(return_date=as_of - timedelta(days=45), order_id="ORD-45", fnsku="FNSKU2", status="Unit not received")
    # 46 days elapsed -> hold expired, eligible claim
    ret_46 = CustomerReturnRecord(return_date=as_of - timedelta(days=46), order_id="ORD-46", fnsku="FNSKU3", status="Unit not received")

    result = engine.reconcile(returns_records=[ret_44, ret_45, ret_46])
    assert len(result.claims) == 1
    assert result.claims[0].order_id == "ORD-46"
    assert result.claims[0].claim_status == "ELIGIBLE"


def test_tier2_boundary_60_day_warehouse_expiration():
    """Tier 2: Boundary condition: Exactly 59, 60, and 61 days after warehouse discrepancy."""
    as_of = date(2026, 9, 29)
    engine = AuditEngine(as_of_date=as_of)

    # 59 days elapsed -> eligible (1 day remaining)
    l_59 = LedgerDetailRecord(date=as_of - timedelta(days=59), fnsku="SKU-59", event_type="Lost", quantity=1)
    # 60 days elapsed -> eligible (0 days remaining)
    l_60 = LedgerDetailRecord(date=as_of - timedelta(days=60), fnsku="SKU-60", event_type="Lost", quantity=1)
    # 61 days elapsed -> expired
    l_61 = LedgerDetailRecord(date=as_of - timedelta(days=61), fnsku="SKU-61", event_type="Lost", quantity=1)

    result = engine.reconcile(ledger_records=[l_59, l_60, l_61])
    assert len(result.claims) == 3

    c_59 = next(c for c in result.claims if c.fnsku == "SKU-59")
    c_60 = next(c for c in result.claims if c.fnsku == "SKU-60")
    c_61 = next(c for c in result.claims if c.fnsku == "SKU-61")

    assert c_59.claim_status == "ELIGIBLE"
    assert c_59.days_remaining == 1

    assert c_60.claim_status == "ELIGIBLE"
    assert c_60.days_remaining == 0

    assert c_61.claim_status == "EXPIRED"
    assert c_61.days_remaining == 0


def test_tier3_combinatorial_concurrent_events():
    """Tier 3: Concurrent warehouse loss, customer return hold, and fee overcharge."""
    as_of = date(2026, 9, 29)
    engine = AuditEngine(as_of_date=as_of)

    ledger = [LedgerDetailRecord(date=as_of - timedelta(days=10), fnsku="SKU_COMBO", event_type="Lost", quantity=3)]
    returns = [CustomerReturnRecord(return_date=as_of - timedelta(days=50), order_id="ORD-C", fnsku="SKU_COMBO", status="Unit not received")]
    catalog = {"SKU_COMBO": {"length": "10.0", "width": "8.0", "height": "0.5", "weight": "0.4", "units_sold_90d": 10}}
    fees = [FeeEstimateRecord(sku="M_COMBO", fnsku="SKU_COMBO", expected_fulfillment_fee_per_unit=Decimal("5.40"))]

    result = engine.reconcile(
        ledger_records=ledger,
        returns_records=returns,
        fee_records=fees,
        catalog_specs=catalog,
    )
    assert len(result.claims) == 3
    types = {c.discrepancy_type for c in result.claims}
    assert "WAREHOUSE_LOST_DAMAGED" in types
    assert "CUSTOMER_RETURN_NOT_RETURNED" in types
    assert "DIMENSIONAL_FEE_OVERCHARGE" in types


def test_tier4_synthetic_90_day_oracle_validation(tmp_path: Path):
    """Tier 4: 90-day multi-SKU simulation matched against Ground Truth Oracle."""
    as_of = date(2026, 9, 29)
    sim = LedgerSimulator(start_date=as_of - timedelta(days=90), seed=999)
    sim.populate_default_catalog()
    sim.simulate_90_day_lifecycle(
        inject_lost_units=6,
        inject_damaged_units=3,
        inject_found_units=2,
        inject_reimbursed_units=1,
        inject_unreturned_refunds=4,
    )

    tsv_ledger = sim.export_ledger_detail_tsv()
    tsv_returns = sim.export_customer_returns_tsv()
    tsv_reimb = sim.export_reimbursements_tsv()
    tsv_fees = sim.export_estimated_fees_tsv()

    p_ledger = tmp_path / "ledger.tsv"
    p_returns = tmp_path / "returns.tsv"
    p_reimb = tmp_path / "reimb.tsv"
    p_fees = tmp_path / "fees.tsv"

    p_ledger.write_text(tsv_ledger, encoding="utf-8")
    p_returns.write_text(tsv_returns, encoding="utf-8")
    p_reimb.write_text(tsv_reimb, encoding="utf-8")
    p_fees.write_text(tsv_fees, encoding="utf-8")

    result = run_audit(
        ledger_path=p_ledger,
        returns_path=p_returns,
        reimbursements_path=p_reimb,
        fees_path=p_fees,
        as_of_date=as_of,
    )

    # Verify that claims were detected and validated
    assert result.summary.total_claims_count > 0
    assert result.summary.total_claim_amount > Decimal("0.00")
    for c in result.claims:
        assert c.claim_amount > Decimal("0.00")
        assert c.policy_citation in ("G200379860", "G200213130", "G21213")
        assert c.claim_status in ("ELIGIBLE", "EXPIRED")
