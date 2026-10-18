"""
Unit tests for fba_audit.cli.
"""

from pathlib import Path
import pytest
import sys

from fba_audit.cli import main


def test_cli_no_args(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["fba-audit"])
    ret = main()
    assert ret == 1
    err = capsys.readouterr().err
    assert "Error: At least one SP-API report file must be provided." in err


def test_cli_full_audit(monkeypatch, capsys, tmp_path: Path):
    fixtures_dir = Path("tests/fixtures")
    out_dir = tmp_path / "cli_output"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "fba-audit",
            "--ledger", str(fixtures_dir / "ledger_detail_sample.tsv"),
            "--returns", str(fixtures_dir / "customer_returns_sample.tsv"),
            "--reimbursements", str(fixtures_dir / "reimbursements_sample.tsv"),
            "--fees", str(fixtures_dir / "estimated_fees_sample.tsv"),
            "--as-of-date", "2026-10-15",
            "--output-dir", str(out_dir),
        ],
    )

    ret = main()
    assert ret == 0
    out = capsys.readouterr().out
    assert "--- Audit Summary ---" in out
    assert "Total Discrepancies:" in out
    assert "Actionable Eligible:" in out
    assert (out_dir / "claims_batch.csv").exists()
    assert (out_dir / "audit_dossier.html").exists()
