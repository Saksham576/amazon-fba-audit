"""
Unit tests for report exporters.
"""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import pytest

from fba_audit.models import AuditResult, AuditSummary, ClaimRecord
from fba_audit.reports import (
    export_claim_batch_csv,
    export_claim_batch_json,
    generate_html_dossier,
    generate_markdown_dossier,
)


@pytest.fixture
def sample_audit_result() -> AuditResult:
    claim = ClaimRecord(
        claim_id="CLAIM12345",
        fnsku="X001ABC",
        msku="PROD-001",
        asin="B00123",
        order_id="111-222-333",
        transaction_id="TX123",
        event_date=date(2026, 9, 1),
        discrepancy_type="WAREHOUSE_LOST_DAMAGED",
        quantity=5,
        unit_price=Decimal("20.00"),
        claim_amount=Decimal("100.00"),
        currency="USD",
        policy_citation="G200379860",
        policy_clause="FBA inventory reimbursement policy: Fulfillment center operations claims",
        claim_window_days=60,
        days_remaining=32,
        claim_status="ELIGIBLE",
        evidence_notes="5 lost units uncompensated",
        fulfillment_center="PHX3",
    )
    summary = AuditSummary(
        as_of_date=date(2026, 9, 29),
        total_claims_count=1,
        total_eligible_count=1,
        total_expired_count=0,
        total_discrepancy_units=5,
        total_claim_amount=Decimal("100.00"),
        eligible_claim_amount=Decimal("100.00"),
        expired_claim_amount=Decimal("0.00"),
        amount_by_discrepancy_type={"WAREHOUSE_LOST_DAMAGED": Decimal("100.00")},
        units_by_discrepancy_type={"WAREHOUSE_LOST_DAMAGED": 5},
    )
    return AuditResult(
        reconciled_at=datetime(2026, 9, 29, 12, 0, 0),
        as_of_date=date(2026, 9, 29),
        claims=[claim],
        summary=summary,
    )


def test_export_claim_batch_csv(tmp_path: Path, sample_audit_result: AuditResult):
    out = tmp_path / "claims.csv"
    res = export_claim_batch_csv(sample_audit_result.claims, out)
    assert res.exists()
    content = res.read_text(encoding="utf-8")
    assert "CLAIM12345" in content
    assert "G200379860" in content


def test_export_claim_batch_json(tmp_path: Path, sample_audit_result: AuditResult):
    out = tmp_path / "claims.json"
    res = export_claim_batch_json(sample_audit_result, out)
    assert res.exists()
    content = res.read_text(encoding="utf-8")
    assert "CLAIM12345" in content
    assert "100.00" in content


def test_generate_markdown_dossier(tmp_path: Path, sample_audit_result: AuditResult):
    out = tmp_path / "dossier.md"
    res = generate_markdown_dossier(sample_audit_result, out)
    assert res.exists()
    content = res.read_text(encoding="utf-8")
    assert "# Amazon FBA Inventory Discrepancy & Reimbursement Audit Dossier" in content
    assert "$100.00" in content


def test_generate_html_dossier(tmp_path: Path, sample_audit_result: AuditResult):
    out = tmp_path / "dossier.html"
    res = generate_html_dossier(sample_audit_result, out)
    assert res.exists()
    content = res.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content
    assert "X001ABC" in content
    assert "CLAIM12345" in content


def test_generate_github_step_summary(tmp_path: Path):
    import json
    from fba_audit.reports.github_summary import generate_github_step_summary, main

    payouts_dir = tmp_path / "payouts"
    notifications_dir = payouts_dir / "notifications"
    notifications_dir.mkdir(parents=True, exist_ok=True)

    ledger_data = {
        "total_recoverable_usd": 1500.0,
        "total_earned_usd": 225.0,
        "audit_runs": [{"run_id": "run_01"}],
        "processed_claim_hashes": ["hash1", "hash2"],
    }
    with open(payouts_dir / "payout_ledger.json", "w", encoding="utf-8") as f:
        json.dump(ledger_data, f)

    notif_data = {
        "recipient": "virajtiwari52@gmail.com",
        "total_claims": 5,
        "payout_cut": 225.0,
        "smtp_sent": True,
        "eml_path": "sample.eml",
    }
    with open(notifications_dir / "payout_alert_01.json", "w", encoding="utf-8") as f:
        json.dump(notif_data, f)

    summary_file = tmp_path / "summary.md"
    summary_text = generate_github_step_summary(payouts_dir=payouts_dir, summary_path=str(summary_file))

    assert "virajtiwari52@gmail.com" in summary_text
    assert "$1,500.00" in summary_text
    assert "$225.00" in summary_text
    assert "Transmitted via Live SMTP" in summary_text
    assert summary_file.exists()
    assert summary_file.read_text(encoding="utf-8") == summary_text

    # Also test empty/fallback summary
    empty_summary = generate_github_step_summary(payouts_dir=tmp_path / "empty")
    assert "No new unnotified claims" in empty_summary
