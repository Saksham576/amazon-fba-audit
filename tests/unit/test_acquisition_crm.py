"""
Unit tests for AutonomousCRM and autonomous business runner.
"""

from datetime import datetime, timezone
from pathlib import Path
import pytest

from fba_audit.acquisition.crm import AutonomousCRM
from fba_audit.acquisition.autonomous_runner import run_autonomous_business_cycle


def test_crm_initialization_and_state(tmp_path: Path):
    crm_dir = tmp_path / "crm"
    crm = AutonomousCRM(crm_dir=crm_dir)

    state = crm.load_state()
    assert state["total_leads"] == 9
    assert len(state["leads"]) == 9
    assert (crm_dir / "crm_state.json").exists()


def test_crm_dispatch_due_touches(tmp_path: Path):
    crm_dir = tmp_path / "crm"
    crm = AutonomousCRM(crm_dir=crm_dir)

    due = crm.get_due_outreach_leads()
    assert len(due) == 9

    dispatched = crm.dispatch_due_touches(max_batch_size=2)
    assert len(dispatched) == 2
    assert dispatched[0]["step"] == 1

    state = crm.load_state()
    assert state["total_dispatched_touches"] == 2

    # Check outbox has .eml files
    eml_files = list((crm_dir / "outbox").glob("*.eml"))
    assert len(eml_files) == 2


def test_autonomous_business_cycle_executes(tmp_path: Path):
    res = run_autonomous_business_cycle(max_outreach_batch=2, simulate_audit=True, seller_id="TEST_CYCLE")
    assert res["dispatched_touches_count"] >= 0
    assert res["audit_result"]["status"] == "COMPLETED"
    assert Path(res["summary_markdown_path"]).exists()
