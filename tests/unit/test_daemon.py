"""
Unit tests for AutonomousAuditDaemon and PayoutMailer.
"""

from decimal import Decimal
import json
from pathlib import Path
import pytest

from fba_audit.daemon import AutonomousAuditDaemon, CONTINGENCY_FEE_RATE
from fba_audit.mailer import PayoutMailer, OWNER_EMAIL


def test_payout_mailer_compose(tmp_path: Path):
    notifications_dir = tmp_path / "notifications"
    mailer = PayoutMailer(notifications_dir=notifications_dir)

    msg = mailer.compose_payout_email(
        seller_id="TEST_SELLER_123",
        total_claims_count=5,
        eligible_amount=Decimal("500.00"),
        payout_cut=Decimal("75.00"),
    )

    assert "virajtiwari52@gmail.com" in msg["To"]
    assert "75.00" in msg["Subject"]
    assert "TEST_SELLER_123" in msg["Subject"]


def test_payout_mailer_dispatch(tmp_path: Path):
    notifications_dir = tmp_path / "notifications"
    mailer = PayoutMailer(notifications_dir=notifications_dir)

    meta = mailer.dispatch_payout_alert(
        seller_id="TEST_SELLER_123",
        total_claims_count=3,
        eligible_amount=Decimal("300.00"),
        payout_cut=Decimal("45.00"),
    )

    assert meta["seller_id"] == "TEST_SELLER_123"
    assert meta["payout_cut"] == 45.0
    assert meta["recipient"] == OWNER_EMAIL
    assert Path(meta["eml_path"]).exists()


def test_daemon_idle_empty_inbound(tmp_path: Path):
    inbound = tmp_path / "inbound"
    output = tmp_path / "output"
    payouts = tmp_path / "payouts"

    daemon = AutonomousAuditDaemon(inbound_dir=inbound, output_dir=output, payouts_dir=payouts)
    res = daemon.run_cycle(simulate_if_empty=False)

    assert res["status"] == "IDLE_NO_REPORTS"
    assert res["new_payout_cut"] == 0.0


def test_daemon_simulation_and_idempotency(tmp_path: Path):
    inbound = tmp_path / "inbound"
    output = tmp_path / "output"
    payouts = tmp_path / "payouts"
    fixtures_dir = Path("tests/fixtures")

    daemon = AutonomousAuditDaemon(inbound_dir=inbound, output_dir=output, payouts_dir=payouts)

    # First run with simulation enabled
    res1 = daemon.run_cycle(simulate_if_empty=True, fixtures_dir=fixtures_dir, seller_id="TEST_ACC")
    assert res1["status"] == "COMPLETED"
    assert res1["new_payout_cut"] > 0
    assert (payouts / "payout_ledger.json").exists()

    with open(payouts / "payout_ledger.json", "r", encoding="utf-8") as f:
        ledger1 = json.load(f)
    assert ledger1["total_earned_usd"] == res1["new_payout_cut"]
    assert len(ledger1["processed_claim_hashes"]) > 0

    # Second run: should be completely idempotent (0 new payout)
    res2 = daemon.run_cycle(simulate_if_empty=True, fixtures_dir=fixtures_dir, seller_id="TEST_ACC")
    assert res2["status"] == "COMPLETED"
    assert res2["new_payout_cut"] == 0.0
    assert res2["new_claims_count"] == 0

    with open(payouts / "payout_ledger.json", "r", encoding="utf-8") as f:
        ledger2 = json.load(f)
    assert ledger2["total_earned_usd"] == ledger1["total_earned_usd"]


def test_daemon_cli_status(monkeypatch, capsys, tmp_path: Path):
    from fba_audit.daemon import main
    payouts = tmp_path / "payouts"
    monkeypatch.setattr("sys.argv", ["fba-daemon", "--status", "--payouts-dir", str(payouts)])
    ret = main()
    assert ret == 0
    out = capsys.readouterr().out
    assert "AUTONOMOUS AMAZON FBA REIMBURSEMENT AUDIT ENGINE" in out


def test_daemon_cli_once_simulate(monkeypatch, capsys, tmp_path: Path):
    from fba_audit.daemon import main
    inbound = tmp_path / "inbound"
    output = tmp_path / "output"
    payouts = tmp_path / "payouts"
    monkeypatch.setattr(
        "sys.argv",
        [
            "fba-daemon",
            "--once",
            "--simulate-if-empty",
            "--inbound-dir", str(inbound),
            "--output-dir", str(output),
            "--payouts-dir", str(payouts),
        ],
    )
    ret = main()
    assert ret == 0
    out = capsys.readouterr().out
    assert "Cycle Result: COMPLETED" in out
    assert "[PAYOUT] Payout Alert Dispatched:" in out

