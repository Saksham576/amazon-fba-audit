"""
Unit tests for Zoho Mail SMTP configuration, auto-detection,
header sanitization, and resilient error recovery.
"""

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
from pathlib import Path
import socket
import smtplib
from unittest.mock import MagicMock, patch
import pytest

from fba_audit.zoho_smtp import (
    DEFAULT_SENDER,
    ZOHO_INDIA_PRO_HOST,
    ZOHO_INDIA_STD_HOST,
    ZOHO_US_PRO_HOST,
    format_auth_error_message,
    format_network_error_message,
    format_relay_error_message,
    get_smtp_credentials,
    load_dotenv,
    resolve_smtp_hosts,
    sanitize_sender_headers,
    send_smtp_message,
)


@pytest.fixture(autouse=True)
def clean_smtp_env(monkeypatch):
    """Ensure tests run in clean, predictable environment without leaking credentials."""
    for key in [
        "FBA_SMTP_HOST",
        "FBA_SMTP_PORT",
        "FBA_SMTP_USER",
        "FBA_SMTP_PASS",
        "FBA_SMTP_PASSWORD",
        "ZOHO_SMTP_HOST",
        "ZOHO_SMTP_PORT",
        "ZOHO_SMTP_USER",
        "ZOHO_SMTP_PASSWORD",
        "ZOHO_SMTP_PASS",
        "ZOHO_PASSWORD",
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USER",
        "SMTP_PASSWORD",
    ]:
        monkeypatch.delenv(key, raising=False)


def _create_mock_server():
    server = MagicMock()
    server.__enter__.return_value = server
    server.__exit__.return_value = None
    return server


def test_load_dotenv_parsing(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# Comment line\n"
        "FBA_SMTP_HOST=smtppro.zoho.in\n"
        "FBA_SMTP_PORT=465\n"
        "FBA_SMTP_USER=\"team@nexuspulsetech.com\"\n"
        "FBA_SMTP_PASS='app_specific_secret_123'\n"
        "EMPTY_VAL=\n",
        encoding="utf-8",
    )

    loaded = load_dotenv(env_file, override=True)
    assert loaded["FBA_SMTP_HOST"] == "smtppro.zoho.in"
    assert loaded["FBA_SMTP_PORT"] == "465"
    assert loaded["FBA_SMTP_USER"] == "team@nexuspulsetech.com"
    assert loaded["FBA_SMTP_PASS"] == "app_specific_secret_123"
    assert os.environ.get("FBA_SMTP_USER") == "team@nexuspulsetech.com"


def test_resolve_smtp_hosts_auto_detection():
    # Nexuspulse domain defaults to India Pro with India Std fallback (no US leakage)
    pri, fb = resolve_smtp_hosts("team@nexuspulsetech.com")
    assert pri == ZOHO_INDIA_PRO_HOST
    assert ZOHO_INDIA_STD_HOST in fb
    assert ZOHO_US_PRO_HOST not in fb

    # .in domain
    pri, fb = resolve_smtp_hosts("sales@business.in")
    assert pri == ZOHO_INDIA_PRO_HOST
    assert ZOHO_INDIA_STD_HOST in fb

    # .eu domain
    pri, fb = resolve_smtp_hosts("contact@agency.eu")
    assert pri == "smtppro.zoho.eu"
    assert "smtp.zoho.eu" in fb

    # Zoho US domain
    pri_us, fb_us = resolve_smtp_hosts("support@zoho.com")
    assert pri_us == ZOHO_US_PRO_HOST
    assert "smtp.zoho.com" in fb_us

    # Explicit configured host
    pri, fb = resolve_smtp_hosts(configured_host="smtp.zoho.in")
    assert pri == "smtp.zoho.in"
    assert "smtppro.zoho.in" in fb


def test_sanitize_sender_headers_rewrites_mismatched_from():
    msg = MIMEMultipart()
    msg["From"] = "Personal Founder <virajtiwari52@gmail.com>"
    msg["To"] = "client@brand.com"
    msg["Subject"] = "Audit Report"

    sanitize_sender_headers(msg, authenticated_user="team@nexuspulsetech.com")

    # From should be rewritten to match authenticated user
    assert msg["From"] == "Personal Founder <team@nexuspulsetech.com>"
    # Original address preserved in Reply-To
    assert msg["Reply-To"] == "virajtiwari52@gmail.com"
    # Essential email headers present
    assert "Date" in msg
    assert "Message-ID" in msg


def test_sanitize_sender_headers_preserves_matching_from():
    msg = MIMEMultipart()
    msg["From"] = "NexusPulse Engine <team@nexuspulsetech.com>"
    msg["To"] = "client@brand.com"
    msg["Reply-To"] = "support@nexuspulsetech.com"

    sanitize_sender_headers(msg, authenticated_user="team@nexuspulsetech.com")

    assert msg["From"] == "NexusPulse Engine <team@nexuspulsetech.com>"
    assert msg["Reply-To"] == "support@nexuspulsetech.com"


def test_send_smtp_message_unconfigured():
    msg = MIMEMultipart()
    res = send_smtp_message(msg, user=None, password=None)
    assert res["success"] is False
    assert res["mode"] == "unconfigured"
    assert "credentials not configured" in res["error"]


def test_send_smtp_message_ssl_port_465_success():
    msg = MIMEMultipart()
    msg["Subject"] = "Test"
    msg["To"] = "virajtiwari52@gmail.com"
    msg.attach(MIMEText("Body", "plain"))

    mock_server = _create_mock_server()
    with patch("smtplib.SMTP_SSL", return_value=mock_server) as mock_ssl:
        res = send_smtp_message(
            msg=msg,
            host="smtppro.zoho.in",
            port=465,
            user="team@nexuspulsetech.com",
            password="app_password_123",
            auto_fallback=False,
        )

        assert res["success"] is True
        assert res["mode"] == "live_smtp"
        assert res["host_used"] == "smtppro.zoho.in"
        assert res["port_used"] == 465
        mock_ssl.assert_called_once_with("smtppro.zoho.in", 465, timeout=10.0)
        mock_server.login.assert_called_once_with("team@nexuspulsetech.com", "app_password_123")
        mock_server.send_message.assert_called_once()
        _, kwargs = mock_server.send_message.call_args
        assert kwargs.get("from_addr") == "team@nexuspulsetech.com"


def test_send_smtp_message_starttls_port_587_success():
    msg = MIMEMultipart()
    msg["Subject"] = "Test 587"
    msg["To"] = "virajtiwari52@gmail.com"

    mock_server = _create_mock_server()
    with patch("smtplib.SMTP", return_value=mock_server) as mock_smtp:
        res = send_smtp_message(
            msg=msg,
            host="smtppro.zoho.in",
            port=587,
            user="team@nexuspulsetech.com",
            password="app_password_123",
            auto_fallback=False,
        )

        assert res["success"] is True
        assert res["port_used"] == 587
        mock_smtp.assert_called_once_with("smtppro.zoho.in", 587, timeout=10.0)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("team@nexuspulsetech.com", "app_password_123")


def test_send_smtp_message_automatic_port_fallback_465_to_587():
    msg = MIMEMultipart()
    msg["Subject"] = "Fallback Test"
    msg["To"] = "virajtiwari52@gmail.com"

    mock_server_587 = _create_mock_server()
    with patch("smtplib.SMTP_SSL", side_effect=socket.timeout("SSL timed out")):
        with patch("smtplib.SMTP", return_value=mock_server_587) as mock_smtp:
            res = send_smtp_message(
                msg=msg,
                host="smtppro.zoho.in",
                port=465,
                user="team@nexuspulsetech.com",
                password="app_password_123",
                auto_fallback=True,
            )

            assert res["success"] is True
            assert res["port_used"] == 587
            mock_smtp.assert_called_once()
            mock_server_587.starttls.assert_called_once()


def test_send_smtp_message_host_fallback():
    msg = MIMEMultipart()
    msg["Subject"] = "Host Fallback Test"
    msg["To"] = "virajtiwari52@gmail.com"

    mock_server_fallback = _create_mock_server()

    def ssl_side_effect(host, port, timeout):
        if host == "smtppro.zoho.in":
            raise ConnectionRefusedError("Connection refused")
        return mock_server_fallback

    with patch("smtplib.SMTP_SSL", side_effect=ssl_side_effect):
        res = send_smtp_message(
            msg=msg,
            host="smtppro.zoho.in",
            port=465,
            user="team@nexuspulsetech.com",
            password="app_password_123",
            auto_fallback=True,
        )

        assert res["success"] is True
        assert res["host_used"] == "smtp.zoho.in"


def test_send_smtp_message_auth_error_535_gives_2fa_guidance():
    msg = MIMEMultipart()
    msg["Subject"] = "Auth Error Test"
    msg["To"] = "virajtiwari52@gmail.com"

    mock_server = _create_mock_server()
    mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Authentication Failed")

    with patch("smtplib.SMTP_SSL", return_value=mock_server):
        res = send_smtp_message(
            msg=msg,
            host="smtppro.zoho.in",
            port=465,
            user="team@nexuspulsetech.com",
            password="wrong_password",
            auto_fallback=False,
        )

        assert res["success"] is False
        assert res["mode"] == "smtp_error"
        assert "Two-Factor Authentication" in res["guidance"]
        assert "App Passwords" in res["guidance"]
        assert "accounts.zoho.in" in res["guidance"]


def test_send_smtp_message_relay_error_553_guidance():
    msg = MIMEMultipart()
    msg["Subject"] = "Relay Error Test"
    msg["To"] = "virajtiwari52@gmail.com"

    mock_server = _create_mock_server()
    mock_server.send_message.side_effect = smtplib.SMTPResponseException(
        553, b"Relaying disallowed as other@domain.com"
    )

    with patch("smtplib.SMTP_SSL", return_value=mock_server):
        res = send_smtp_message(
            msg=msg,
            host="smtppro.zoho.in",
            port=465,
            user="team@nexuspulsetech.com",
            password="secret_password",
            auto_fallback=False,
        )

        assert res["success"] is False
        assert "Relaying disallowed" in res["guidance"]


def test_send_smtp_message_network_timeout_guidance():
    msg = MIMEMultipart()
    msg["Subject"] = "Network Timeout Test"
    msg["To"] = "virajtiwari52@gmail.com"

    with patch("smtplib.SMTP_SSL", side_effect=socket.timeout("Connection timed out")):
        with patch("smtplib.SMTP", side_effect=socket.timeout("Connection timed out")):
            res = send_smtp_message(
                msg=msg,
                host="smtppro.zoho.in",
                port=465,
                user="team@nexuspulsetech.com",
                password="secret_password",
                auto_fallback=True,
            )

            assert res["success"] is False
            assert "firewall" in res["guidance"].lower()
            assert ".eml" in res["guidance"]


def test_load_dotenv_strips_inline_comments(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "FBA_SMTP_HOST=smtppro.zoho.in # Production Zoho India Host\n"
        "FBA_SMTP_PORT=465 # SSL Port\n"
        "FBA_SMTP_USER=\"team@nexuspulsetech.com\" # Quoted value with comment\n",
        encoding="utf-8",
    )
    loaded = load_dotenv(env_file, override=True)
    assert loaded["FBA_SMTP_HOST"] == "smtppro.zoho.in"
    assert loaded["FBA_SMTP_PORT"] == "465"
    assert loaded["FBA_SMTP_USER"] == "team@nexuspulsetech.com"


def test_sanitize_sender_headers_handles_quotes_and_commas():
    msg = MIMEMultipart()
    msg["From"] = "Tiwari, Viraj <virajtiwari52@gmail.com>"
    msg["Sender"] = "unauthorized@external.com"
    msg["Return-Path"] = "<spoofed@bounce.com>"
    msg.add_header("From", "duplicate@other.com")

    sanitize_sender_headers(msg, authenticated_user="team@nexuspulsetech.com")

    # Only one From header should remain
    assert len(msg.get_all("From")) == 1
    # Comma in display name must be quoted per RFC 5322
    assert msg["From"] == '"Tiwari, Viraj" <team@nexuspulsetech.com>'
    # Mismatched Sender header should be aligned or replaced
    assert "team@nexuspulsetech.com" in msg["Sender"]
    # Return-Path must be stripped
    assert "Return-Path" not in msg
    # Original address preserved in Reply-To
    assert msg["Reply-To"] == "virajtiwari52@gmail.com"


def test_send_smtp_message_retries_with_stripped_spaces_for_zoho_app_password():
    msg = MIMEMultipart()
    msg["Subject"] = "Space Password Test"
    msg["To"] = "virajtiwari52@gmail.com"

    mock_server = _create_mock_server()
    # First login attempt with space password fails with 535, second attempt without spaces succeeds
    login_calls = []

    def login_side_effect(user, password):
        login_calls.append((user, password))
        if " " in password:
            raise smtplib.SMTPAuthenticationError(535, b"Authentication Failed")
        return (235, b"2.7.0 Authentication successful")

    mock_server.login.side_effect = login_side_effect

    with patch("smtplib.SMTP_SSL", return_value=mock_server):
        res = send_smtp_message(
            msg=msg,
            host="smtppro.zoho.in",
            port=465,
            user="team@nexuspulsetech.com",
            password="abcd efgh ijkl mnop",
            auto_fallback=False,
        )

        assert res["success"] is True
        assert len(login_calls) == 2
        assert login_calls[0][1] == "abcd efgh ijkl mnop"
        assert login_calls[1][1] == "abcdefghijklmnop"


def test_send_smtp_message_immediate_fatal_stop_on_relay_553():
    msg = MIMEMultipart()
    msg["Subject"] = "Relay 553 Fast Fail"
    msg["To"] = "virajtiwari52@gmail.com"

    mock_server = _create_mock_server()
    mock_server.send_message.side_effect = smtplib.SMTPResponseException(
        553, b"Relaying disallowed as other@domain.com"
    )

    with patch("smtplib.SMTP_SSL", return_value=mock_server) as mock_ssl:
        with patch("smtplib.SMTP") as mock_smtp:
            res = send_smtp_message(
                msg=msg,
                host="smtppro.zoho.in",
                port=465,
                user="team@nexuspulsetech.com",
                password="secret_password",
                auto_fallback=True,
            )

            assert res["success"] is False
            # Should have stopped immediately on 465 without trying 587 or fallback hosts
            assert mock_ssl.call_count == 1
            mock_smtp.assert_not_called()
            assert "Relaying disallowed" in res["guidance"]
