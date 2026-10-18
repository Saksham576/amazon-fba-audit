"""
Unit tests for PayoutMailer and AutonomousCRM live SMTP integration with Zoho Mail.
"""

from decimal import Decimal
import json
from pathlib import Path
import smtplib
from unittest.mock import MagicMock, patch
import pytest

from fba_audit.mailer import PayoutMailer, OWNER_EMAIL
from fba_audit.acquisition.crm import AutonomousCRM


def _mock_smtp_server():
    server = MagicMock()
    server.__enter__.return_value = server
    server.__exit__.return_value = None
    server.ehlo.return_value = (250, b"smtp.zoho.in at your service")
    return server


def test_payout_mailer_dispatch_with_live_smtp_success(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FBA_SMTP_USER", "team@nexuspulsetech.com")
    monkeypatch.setenv("FBA_SMTP_PASS", "app_specific_secret_123")
    monkeypatch.setenv("FBA_SMTP_HOST", "smtppro.zoho.in")
    monkeypatch.setenv("FBA_SMTP_PORT", "465")

    notifications_dir = tmp_path / "notifications"
    mailer = PayoutMailer(notifications_dir=notifications_dir)

    mock_srv = _mock_smtp_server()
    with patch("smtplib.SMTP_SSL", return_value=mock_srv) as mock_ssl:
        meta = mailer.dispatch_payout_alert(
            seller_id="TEST_SELLER_ZOHO",
            total_claims_count=7,
            eligible_amount=Decimal("1200.00"),
            payout_cut=Decimal("180.00"),
        )

        assert meta["seller_id"] == "TEST_SELLER_ZOHO"
        assert meta["payout_cut"] == 180.0
        assert meta["smtp_sent"] is True
        assert meta["smtp_error"] is None
        assert meta["host_used"] == "smtppro.zoho.in"
        assert meta["port_used"] == 465
        assert Path(meta["eml_path"]).exists()

        mock_ssl.assert_called_once_with("smtppro.zoho.in", 465, timeout=10.0)
        mock_srv.login.assert_called_once_with("team@nexuspulsetech.com", "app_specific_secret_123")
        mock_srv.send_message.assert_called_once()
        _, kwargs = mock_srv.send_message.call_args
        assert kwargs.get("from_addr") == "team@nexuspulsetech.com"

        # Verify .eml content has strictly matching From address
        with open(meta["eml_path"], "r", encoding="utf-8") as f:
            eml_content = f.read()
        assert "team@nexuspulsetech.com" in eml_content


def test_payout_mailer_dispatch_with_smtp_auth_error_535(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FBA_SMTP_USER", "team@nexuspulsetech.com")
    monkeypatch.setenv("FBA_SMTP_PASS", "bad_regular_password")

    notifications_dir = tmp_path / "notifications"
    mailer = PayoutMailer(notifications_dir=notifications_dir)

    mock_srv = _mock_smtp_server()
    mock_srv.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Authentication Failed")

    with patch("smtplib.SMTP_SSL", return_value=mock_srv):
        meta = mailer.dispatch_payout_alert(
            seller_id="TEST_SELLER_ZOHO_FAIL",
            total_claims_count=1,
            eligible_amount=Decimal("50.00"),
            payout_cut=Decimal("7.50"),
        )

        assert meta["smtp_sent"] is False
        assert "Authentication Failed" in meta["smtp_error"]
        assert "Two-Factor Authentication" in meta["smtp_diagnostic"]
        # EML file still safely preserved
        assert Path(meta["eml_path"]).exists()


def test_crm_dispatch_due_touches_with_live_smtp_success(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FBA_SMTP_USER", "team@nexuspulsetech.com")
    monkeypatch.setenv("FBA_SMTP_PASS", "app_pass_test")

    crm_dir = tmp_path / "crm"
    crm = AutonomousCRM(crm_dir=crm_dir)

    mock_srv = _mock_smtp_server()
    with patch("smtplib.SMTP_SSL", return_value=mock_srv):
        dispatched = crm.dispatch_due_touches(max_batch_size=1)

        assert len(dispatched) == 1
        record = dispatched[0]
        assert record["live_smtp_sent"] is True
        assert record["smtp_error"] is None
        assert Path(record["eml_file"]).exists()

        # Verify header sanitization inside .eml file
        with open(record["eml_file"], "r", encoding="utf-8") as f:
            eml_text = f.read()
        assert "team@nexuspulsetech.com" in eml_text


def test_compose_payout_email_sanitizes_headers():
    mailer = PayoutMailer()
    msg = mailer.compose_payout_email(
        seller_id="TEST_SELLER",
        total_claims_count=3,
        eligible_amount=Decimal("300.00"),
        payout_cut=Decimal("45.00"),
    )
    assert "team@nexuspulsetech.com" in msg["From"]
    assert "virajtiwari52@gmail.com" in msg["To"]
    assert "Date" in msg
    assert "Message-ID" in msg


def test_crm_batch_dispatch_short_circuits_on_network_timeout(tmp_path: Path, monkeypatch):
    import socket
    monkeypatch.setenv("FBA_SMTP_USER", "team@nexuspulsetech.com")
    monkeypatch.setenv("FBA_SMTP_PASS", "app_pass_test")

    crm_dir = tmp_path / "crm"
    crm = AutonomousCRM(crm_dir=crm_dir)

    # Patch socket timeout so first email times out
    with patch("smtplib.SMTP_SSL", side_effect=socket.timeout("Connection timed out")):
        with patch("smtplib.SMTP", side_effect=socket.timeout("Connection timed out")):
            dispatched = crm.dispatch_due_touches(max_batch_size=2)

            assert len(dispatched) == 2
            # First lead failed due to timeout
            assert dispatched[0]["live_smtp_sent"] is False
            assert "timed out" in dispatched[0]["smtp_error"].lower()
            assert Path(dispatched[0]["eml_file"]).exists()

            # Second lead was short-circuited without re-attempting live socket connection
            assert dispatched[1]["live_smtp_sent"] is False
            assert "Skipped live delivery" in dispatched[1]["smtp_error"]
            assert Path(dispatched[1]["eml_file"]).exists()
