"""
Unit tests for Zoho Mail SMTP mailer_diag.py diagnostic verification utility & CLI.
"""

import json
from pathlib import Path
import socket
import smtplib
from unittest.mock import MagicMock, patch
import pytest

from fba_audit.mailer_diag import (
    main,
    print_diagnostic_report,
    probe_auth,
    probe_dns,
    probe_port_handshake,
    run_diagnostics,
)


def _mock_server():
    server = MagicMock()
    server.__enter__.return_value = server
    server.__exit__.return_value = None
    server.ehlo.return_value = (250, b"smtp.zoho.in at your service")
    return server


def test_probe_dns():
    with patch("socket.gethostbyname", return_value="103.103.197.104"):
        res = probe_dns("smtppro.zoho.in")
        assert res["status"] == "PASS"
        assert res["ip"] == "103.103.197.104"
        assert res["latency_ms"] >= 0

    with patch("socket.gethostbyname", side_effect=socket.gaierror("Name or service not known")):
        res = probe_dns("nonexistent.host.local")
        assert res["status"] == "FAIL"
        assert res["ip"] is None
        assert "Name or service not known" in res["error"]


def test_probe_port_handshake_ssl_and_starttls():
    srv = _mock_server()

    # Port 465 SSL
    with patch("smtplib.SMTP_SSL", return_value=srv):
        res = probe_port_handshake("smtppro.zoho.in", 465)
        assert res["status"] == "PASS"
        assert res["protocol"] == "SSL"
        assert res["port"] == 465

    # Port 587 STARTTLS
    with patch("smtplib.SMTP", return_value=srv):
        res = probe_port_handshake("smtppro.zoho.in", 587)
        assert res["status"] == "PASS"
        assert res["protocol"] == "STARTTLS"
        assert res["port"] == 587
        srv.starttls.assert_called_once()

    # Timeout
    with patch("smtplib.SMTP_SSL", side_effect=socket.timeout("Timed out")):
        res = probe_port_handshake("smtppro.zoho.in", 465, timeout=0.1)
        assert res["status"] == "TIMEOUT"
        assert "timed out" in res["error"].lower()

    # Connection error
    with patch("smtplib.SMTP_SSL", side_effect=ConnectionRefusedError("Refused")):
        res = probe_port_handshake("smtppro.zoho.in", 465)
        assert res["status"] == "FAIL"
        assert "ConnectionRefusedError" in res["error"]


def test_probe_auth_pass_and_fail_2fa():
    srv = _mock_server()

    # Auth Pass
    with patch("smtplib.SMTP_SSL", return_value=srv):
        res = probe_auth("smtppro.zoho.in", 465, "team@nexuspulsetech.com", "app_pass_123")
        assert res["status"] == "PASS"
        srv.login.assert_called_once_with("team@nexuspulsetech.com", "app_pass_123")

    # Auth Fail 535 (2FA App Password needed)
    srv_fail = _mock_server()
    srv_fail.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Authentication Failed")
    with patch("smtplib.SMTP_SSL", return_value=srv_fail):
        res = probe_auth("smtppro.zoho.in", 465, "team@nexuspulsetech.com", "wrong_pass")
        assert res["status"] == "FAIL_2FA"
        assert "App Passwords" in res["guidance"]


def test_run_diagnostics_firewall_detection(monkeypatch):
    monkeypatch.delenv("FBA_SMTP_PASS", raising=False)
    with patch("fba_audit.mailer_diag.probe_dns", return_value={"status": "PASS", "ip": "1.1.1.1", "latency_ms": 1.0, "host": "h"}):
        with patch("fba_audit.mailer_diag.probe_port_handshake", return_value={"status": "TIMEOUT", "port": 465, "protocol": "SSL", "host": "h", "latency_ms": 100.0, "error": "timeout"}):
            res = run_diagnostics(user="team@nexuspulsetech.com")
            assert res["firewall_block_detected"] is True
            assert res["overall_status"] == "FIREWALL_BLOCKED"
            assert any("firewall" in rec.lower() for rec in res["recommendations"])


def test_run_diagnostics_with_test_send(monkeypatch):
    monkeypatch.delenv("FBA_SMTP_PASS", raising=False)
    srv = _mock_server()
    with patch("fba_audit.mailer_diag.probe_dns", return_value={"status": "PASS", "ip": "103.103.197.104", "latency_ms": 5.0, "host": "smtppro.zoho.in"}):
        with patch("fba_audit.mailer_diag.probe_port_handshake", return_value={"status": "PASS", "port": 465, "protocol": "SSL", "host": "smtppro.zoho.in", "latency_ms": 10.0, "banner": "OK"}):
            with patch("smtplib.SMTP_SSL", return_value=srv):
                res = run_diagnostics(
                    user="team@nexuspulsetech.com",
                    password="valid_app_password",
                    send_test_to="virajtiwari52@gmail.com",
                )
                assert res["test_send"] is not None
                assert res["test_send"]["success"] is True
                assert res["overall_status"] == "HEALTHY"


def test_print_diagnostic_report_output(capsys):
    mock_res = {
        "timestamp": "2026-10-18T12:00:00Z",
        "overall_status": "HEALTHY",
        "configuration": {
            "user": "team@nexuspulsetech.com",
            "primary_host": "smtppro.zoho.in",
            "configured_port": 465,
            "fallback_hosts": ["smtp.zoho.in"],
            "password_configured": True,
            "password_length": 16,
        },
        "dns_checks": [
            {"host": "smtppro.zoho.in", "status": "PASS", "ip": "103.103.197.104", "latency_ms": 5.0}
        ],
        "handshake_checks": [
            {"host": "smtppro.zoho.in", "port": 465, "protocol": "SSL", "status": "PASS", "banner": "OK", "error": None}
        ],
        "auth_check": {
            "status": "PASS",
            "user": "team@nexuspulsetech.com",
            "host": "smtppro.zoho.in",
            "port": 465,
        },
        "test_send": None,
        "recommendations": [],
    }

    print_diagnostic_report(mock_res)
    captured = capsys.readouterr().out
    assert "ZOHO MAIL SMTP VERIFICATION" in captured
    assert "smtppro.zoho.in" in captured
    assert "DNS RESOLUTION" in captured
    assert "AUTHENTICATION CHECK" in captured


def test_mailer_diag_cli_json(capsys):
    with patch("fba_audit.mailer_diag.run_diagnostics", return_value={"overall_status": "HEALTHY", "test": True}):
        ret = main(["--json"])
        assert ret == 0
        captured = capsys.readouterr().out
        data = json.loads(captured)
        assert data["overall_status"] == "HEALTHY"


def test_mailer_diag_cli_exit_code_on_auth_fail():
    failed_auth_diag = {
        "overall_status": "AUTH_FAILED",
        "auth_check": {"status": "FAIL_2FA"},
        "test_send": None,
        "configuration": {
            "user": "team@nexuspulsetech.com",
            "primary_host": "smtppro.zoho.in",
            "configured_port": 465,
            "fallback_hosts": [],
            "password_configured": True,
            "password_length": 10,
        },
        "dns_checks": [],
        "handshake_checks": [],
        "recommendations": [],
    }
    with patch("fba_audit.mailer_diag.run_diagnostics", return_value=failed_auth_diag):
        ret = main(["--pass", "bad_pass", "--user", "team@nexuspulsetech.com"])
        assert ret == 2


def test_run_diagnostics_dns_failure_status(monkeypatch):
    monkeypatch.delenv("FBA_SMTP_PASS", raising=False)
    with patch("fba_audit.mailer_diag.probe_dns", return_value={"status": "FAIL", "ip": None, "latency_ms": 1.0, "host": "smtppro.zoho.in", "error": "NXDOMAIN"}):
        with patch("fba_audit.mailer_diag.probe_port_handshake", return_value={"status": "FAIL", "port": 465, "protocol": "SSL", "host": "smtppro.zoho.in", "latency_ms": 1.0, "error": "gaierror"}):
            res = run_diagnostics(user="team@nexuspulsetech.com", password="secret_password")
            assert res["overall_status"] == "DNS_ERROR"
            assert any("DNS Resolution failure" in rec for rec in res["recommendations"])


def test_run_diagnostics_unreachable_skips_auth(monkeypatch):
    monkeypatch.delenv("FBA_SMTP_PASS", raising=False)
    with patch("fba_audit.mailer_diag.probe_dns", return_value={"status": "PASS", "ip": "1.1.1.1", "latency_ms": 1.0, "host": "smtppro.zoho.in"}):
        with patch("fba_audit.mailer_diag.probe_port_handshake", return_value={"status": "TIMEOUT", "port": 465, "protocol": "SSL", "host": "smtppro.zoho.in", "latency_ms": 10.0, "error": "timeout"}):
            with patch("fba_audit.mailer_diag.probe_auth") as mock_auth:
                res = run_diagnostics(user="team@nexuspulsetech.com", password="some_password")
                assert res["firewall_block_detected"] is True
                assert res["overall_status"] == "FIREWALL_BLOCKED"
                # Auth should NOT be probed if no endpoints are reachable
                assert res["auth_check"] is None
                mock_auth.assert_not_called()


def test_mailer_diag_cli_exit_code_on_send_test_fail():
    failed_test_diag = {
        "overall_status": "FIREWALL_BLOCKED",
        "auth_check": None,
        "test_send": {"success": False, "error": "Firewall blocked"},
        "configuration": {"user": "team@nexuspulsetech.com"},
        "dns_checks": [],
        "handshake_checks": [],
        "recommendations": [],
    }
    with patch("fba_audit.mailer_diag.run_diagnostics", return_value=failed_test_diag):
        ret = main(["--send-test-to", "virajtiwari52@gmail.com"])
        assert ret == 3
