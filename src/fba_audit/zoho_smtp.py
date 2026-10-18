"""
Zoho Mail SMTP configuration, auto-detection, header sanitization,
and resilient delivery engine for Amazon FBA Audit.

Handles:
1. Datacenter auto-detection (smtppro.zoho.in vs smtp.zoho.in vs zoho.com / zoho.eu)
2. Port 465 (SSL) and Port 587 (STARTTLS) with automatic fallback
3. Two-Factor Authentication (2FA) / Application-Specific Password guidance
4. Strict MIME From / envelope sender matching to prevent Error 553 (Relaying disallowed)
5. Robust timeout and firewall block diagnosis
"""

import email.utils
from email.message import Message
import os
from pathlib import Path
import re
import socket
import smtplib
from typing import Any, Dict, List, Optional, Tuple, Union


# Standard Zoho Mail SMTP Hostnames
ZOHO_INDIA_PRO_HOST = "smtppro.zoho.in"
ZOHO_INDIA_STD_HOST = "smtp.zoho.in"
ZOHO_US_PRO_HOST = "smtppro.zoho.com"
ZOHO_US_STD_HOST = "smtp.zoho.com"
ZOHO_EU_PRO_HOST = "smtppro.zoho.eu"
ZOHO_EU_STD_HOST = "smtp.zoho.eu"

DEFAULT_SENDER = "team@nexuspulsetech.com"
DEFAULT_OWNER = "virajtiwari52@gmail.com"


def load_dotenv(env_path: Optional[Union[str, Path]] = None, override: bool = False) -> Dict[str, str]:
    """
    Parses a .env file and populates os.environ without requiring external dependencies.
    Searches in provided path, current working directory, and project root.
    Handles inline comments and quoted strings.
    """
    candidates = []
    if env_path:
        candidates.append(Path(env_path))
    else:
        cwd = Path.cwd()
        candidates.append(cwd / ".env")
        candidates.append(Path(__file__).resolve().parent.parent.parent / ".env")
        candidates.append(cwd.parent / ".env")

    loaded_vars: Dict[str, str] = {}
    target_file = None
    for p in candidates:
        if p.is_file():
            target_file = p
            break

    if not target_file:
        return loaded_vars

    try:
        with open(target_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip()
                    # Strip inline comments if not quoted
                    if not ((val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'"))):
                        if " #" in val:
                            val = val.split(" #", 1)[0].strip()
                    # Strip surrounding matching quotes
                    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                        val = val[1:-1]
                    loaded_vars[key] = val
                    if override or key not in os.environ:
                        os.environ[key] = val
    except Exception:
        pass

    return loaded_vars


def resolve_smtp_hosts(
    user_email: Optional[str] = None,
    configured_host: Optional[str] = None,
) -> Tuple[str, List[str]]:
    """
    Determines primary and fallback SMTP hostnames based on explicit configuration
    or auto-detection from the sender's email domain.
    Maintains strict Zoho datacenter segregation (India vs US vs EU).
    """
    if configured_host:
        host = configured_host.strip().lower()
        if host in (ZOHO_INDIA_PRO_HOST, ZOHO_INDIA_STD_HOST):
            fallback = [ZOHO_INDIA_STD_HOST if host == ZOHO_INDIA_PRO_HOST else ZOHO_INDIA_PRO_HOST]
            return host, fallback
        elif host in (ZOHO_US_PRO_HOST, ZOHO_US_STD_HOST):
            fallback = [ZOHO_US_STD_HOST if host == ZOHO_US_PRO_HOST else ZOHO_US_PRO_HOST]
            return host, fallback
        elif host in (ZOHO_EU_PRO_HOST, ZOHO_EU_STD_HOST):
            fallback = [ZOHO_EU_STD_HOST if host == ZOHO_EU_PRO_HOST else ZOHO_EU_PRO_HOST]
            return host, fallback
        return host, []

    email_clean = (user_email or DEFAULT_SENDER).strip().lower()

    # Zoho EU accounts
    if email_clean.endswith(".eu") or "zoho.eu" in email_clean:
        return ZOHO_EU_PRO_HOST, [ZOHO_EU_STD_HOST]

    # Zoho US accounts
    if "zoho.com" in email_clean:
        return ZOHO_US_PRO_HOST, [ZOHO_US_STD_HOST]

    # NexusPulse Technologies operates on zoho.in Forever Free plan; default to India Pro
    return ZOHO_INDIA_PRO_HOST, [ZOHO_INDIA_STD_HOST]


def get_smtp_credentials() -> Dict[str, Any]:
    """
    Reads SMTP configuration from environment variables (loading .env if needed).
    Supports standard FBA_* and ZOHO_* environment variable keys.
    """
    load_dotenv()

    configured_host = (
        os.getenv("FBA_SMTP_HOST")
        or os.getenv("ZOHO_SMTP_HOST")
        or os.getenv("SMTP_HOST")
    )
    port_raw = (
        os.getenv("FBA_SMTP_PORT")
        or os.getenv("ZOHO_SMTP_PORT")
        or os.getenv("SMTP_PORT")
        or "465"
    )
    try:
        port = int(port_raw)
    except ValueError:
        port = 465

    user = (
        os.getenv("FBA_SMTP_USER")
        or os.getenv("ZOHO_SMTP_USER")
        or os.getenv("SMTP_USER")
        or os.getenv("FBA_SENDER_EMAIL")
        or DEFAULT_SENDER
    )

    password = (
        os.getenv("FBA_SMTP_PASS")
        or os.getenv("FBA_SMTP_PASSWORD")
        or os.getenv("ZOHO_SMTP_PASSWORD")
        or os.getenv("ZOHO_SMTP_PASS")
        or os.getenv("ZOHO_PASSWORD")
        or os.getenv("SMTP_PASSWORD")
    )

    sender = os.getenv("FBA_SENDER_EMAIL") or user
    owner = os.getenv("FBA_OWNER_EMAIL") or DEFAULT_OWNER

    primary_host, fallback_hosts = resolve_smtp_hosts(user, configured_host)

    return {
        "host": primary_host,
        "configured_host": configured_host,
        "fallback_hosts": fallback_hosts,
        "port": port,
        "user": user,
        "password": password,
        "sender_email": sender,
        "owner_email": owner,
        "has_credentials": bool(user and password),
    }


def parse_mailbox(raw: str) -> Tuple[str, str]:
    """
    Extracts (display_name, email_address) safely even if display name contains
    unquoted commas or special characters.
    """
    if not raw:
        return "", ""
    raw = str(raw).strip()
    if "<" in raw and ">" in raw:
        start = raw.find("<")
        end = raw.rfind(">")
        addr = raw[start + 1 : end].strip()
        name = raw[:start].strip().strip('"\'')
        return name, addr
    name, addr = email.utils.parseaddr(raw)
    return name.strip('"\''), addr.strip()


def sanitize_sender_headers(
    msg: Message,
    authenticated_user: str,
    default_display_name: str = "NexusPulse FBA Engine",
) -> None:
    """
    Enforces strict MIME From-Header and Sender matching to prevent Zoho Mail Error 553
    ('Relaying disallowed as <address>').
    If the current From address does not match authenticated_user:
    - Moves original address to Reply-To (if Reply-To is unset)
    - Rewrites From using formataddr to ensure RFC 5322 compliance
    - Removes duplicate From headers
    - Sanitizes or deletes mismatched Sender and Return-Path headers
    """
    _, auth_user_addr = parse_mailbox(authenticated_user)
    auth_user_clean = (auth_user_addr if auth_user_addr else authenticated_user).strip("<> ")

    current_from = msg.get("From", "")
    display_name, current_email = parse_mailbox(current_from)

    needs_rewrite = False
    all_froms = msg.get_all("From", [])
    if len(all_froms) > 1:
        needs_rewrite = True
    elif not current_email or current_email.strip().lower() != auth_user_clean.lower():
        needs_rewrite = True

    if needs_rewrite:
        # Preserve original sender in Reply-To if not already explicitly configured
        if current_email and not msg.get("Reply-To"):
            msg["Reply-To"] = current_email

        eff_display_name = display_name if display_name else default_display_name
        del msg["From"]
        msg["From"] = email.utils.formataddr((eff_display_name, auth_user_clean))

    # Sanitize Sender header if present (Zoho validates Sender against authenticated mailbox)
    if msg.get("Sender"):
        s_name, s_addr = parse_mailbox(msg.get("Sender"))
        if s_addr and s_addr.strip().lower() != auth_user_clean.lower():
            del msg["Sender"]
            msg["Sender"] = email.utils.formataddr((s_name or display_name or default_display_name, auth_user_clean))

    # Strip client-side Return-Path if present (SMTP envelope sets this)
    if "Return-Path" in msg:
        del msg["Return-Path"]

    # Ensure Date and Message-ID headers are present
    if "Date" not in msg:
        msg["Date"] = email.utils.formatdate(localtime=True)
    if "Message-ID" not in msg:
        domain = auth_user_clean.split("@")[-1] if "@" in auth_user_clean else "nexuspulsetech.com"
        msg["Message-ID"] = email.utils.make_msgid(domain=domain)


def format_auth_error_message(user: str, host: str, port: int, exc: Exception) -> str:
    """
    Generates actionable instructions when Zoho rejects login credentials (code 535).
    """
    return (
        f"[Zoho SMTP Authentication Failed (535)] Account: '{user}' on {host}:{port}.\n"
        f"Details: {exc}\n\n"
        f"Root Cause:\n"
        f"  Zoho Mail accounts with Two-Factor Authentication (2FA/TFA) reject standard account\n"
        f"  login passwords over SMTP and require an Application-Specific Password (ASP).\n\n"
        f"How to resolve:\n"
        f"  1. Go to Zoho Accounts: https://accounts.zoho.in (or https://accounts.zoho.com)\n"
        f"  2. Click 'Security' in the left menu -> 'App Passwords'\n"
        f"  3. Click 'Generate New Password', enter name (e.g., 'FBA Audit Engine')\n"
        f"  4. Set the generated password in your environment or .env file (remove any spaces):\n"
        f"     FBA_SMTP_PASS=<16_digit_app_password>\n"
    )


def format_relay_error_message(user: str, from_addr: str, exc: Exception) -> str:
    """
    Generates actionable instructions when Zoho rejects sender address mismatch (code 553).
    """
    return (
        f"[Zoho SMTP Relaying Disallowed (553)] From: '{from_addr}' vs Auth: '{user}'.\n"
        f"Details: {exc}\n\n"
        f"Root Cause:\n"
        f"  Zoho Mail strictly blocks SMTP relaying when the MIME 'From' header or envelope\n"
        f"  sender does not match the authenticated mailbox '{user}'.\n\n"
        f"How to resolve:\n"
        f"  Set FBA_SENDER_EMAIL={user} or ensure the outgoing From header uses '{user}'.\n"
    )


def format_network_error_message(host: str, port: int, timeout: float, exc: Exception) -> str:
    """
    Generates actionable diagnosis when outbound connection to Zoho SMTP fails or times out.
    """
    is_timeout = isinstance(exc, (socket.timeout, TimeoutError)) or "timed out" in str(exc).lower()
    header = "[Zoho SMTP Network Timeout]" if is_timeout else f"[Zoho SMTP Connection Error: {type(exc).__name__}]"
    detail_msg = f"within {timeout}s" if is_timeout else f"({exc})"

    return (
        f"{header} Unable to connect to {host}:{port} {detail_msg}.\n"
        f"Details: {type(exc).__name__}: {exc}\n\n"
        f"Diagnosis:\n"
        f"  Outbound SMTP ports 465 (SSL) and 587 (TLS) are frequently blocked by local ISP or\n"
        f"  university/enterprise network firewalls (e.g. IIT Bombay campus WiFi/firewall).\n\n"
        f"Resolution & Safety Guarantee:\n"
        f"  - All outbound emails are safely archived as .eml receipts in your notifications outbox.\n"
        f"  - No data is lost. Live SMTP transmission will succeed when running on an unblocked\n"
        f"    network or on a 24/7 cloud runner (e.g. GitHub Actions runner or Cloud Run).\n"
    )


def send_smtp_message(
    msg: Message,
    host: Optional[str] = None,
    port: Optional[int] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    to_addrs: Optional[Union[str, List[str]]] = None,
    timeout: float = 10.0,
    auto_fallback: bool = True,
) -> Dict[str, Any]:
    """
    Transmits an RFC-compliant email message with automatic Zoho datacenter detection,
    dual-port SSL (465) / STARTTLS (587) fallback, strict sender header sanitization,
    and structured error diagnostics.
    """
    creds = get_smtp_credentials()
    eff_user = (user or creds["user"]).strip()
    eff_pass = (password if password is not None else creds["password"])
    if isinstance(eff_pass, str):
        eff_pass = eff_pass.strip()
    eff_port = int(port if port is not None else creds["port"])

    if not eff_user or not eff_pass:
        return {
            "success": False,
            "mode": "unconfigured",
            "host_used": None,
            "port_used": None,
            "user_used": eff_user,
            "error": "SMTP credentials not configured (FBA_SMTP_USER and FBA_SMTP_PASS required).",
            "guidance": "Set FBA_SMTP_USER and FBA_SMTP_PASS in .env or environment to enable live email delivery.",
        }

    # Strict From-Header alignment (Requirement 4)
    sanitize_sender_headers(msg, eff_user)

    # Determine candidate hosts and ports to attempt
    primary_host, fallback_hosts = resolve_smtp_hosts(eff_user, host or creds.get("configured_host"))
    hosts_to_try = [primary_host]
    if auto_fallback:
        for fb in fallback_hosts:
            if fb not in hosts_to_try:
                hosts_to_try.append(fb)

    ports_to_try = [eff_port]
    if auto_fallback:
        alt_port = 587 if eff_port == 465 else 465
        if alt_port not in ports_to_try:
            ports_to_try.append(alt_port)

    last_error: Optional[Exception] = None
    last_guidance: Optional[str] = None
    attempts_log: List[str] = []
    fatal_stop = False

    for h in hosts_to_try:
        if fatal_stop:
            break
        for p in ports_to_try:
            attempt_label = f"{h}:{p} ({'SSL' if p == 465 else 'STARTTLS'})"

            def _login_and_send(server_instance):
                server_instance.ehlo()
                if p != 465:
                    server_instance.starttls()
                    server_instance.ehlo()

                # Attempt login with eff_pass; if 535 and spaces present, retry stripped
                try:
                    server_instance.login(eff_user, eff_pass)
                except smtplib.SMTPAuthenticationError as auth_err:
                    if " " in eff_pass:
                        stripped_pass = eff_pass.replace(" ", "")
                        server_instance.login(eff_user, stripped_pass)
                    else:
                        raise auth_err

                if to_addrs:
                    server_instance.send_message(msg, from_addr=eff_user, to_addrs=to_addrs)
                else:
                    server_instance.send_message(msg, from_addr=eff_user)

            try:
                if p == 465:
                    with smtplib.SMTP_SSL(h, p, timeout=timeout) as server:
                        _login_and_send(server)
                else:
                    with smtplib.SMTP(h, p, timeout=timeout) as server:
                        _login_and_send(server)

                # Successful dispatch
                return {
                    "success": True,
                    "mode": "live_smtp",
                    "host_used": h,
                    "port_used": p,
                    "user_used": eff_user,
                    "error": None,
                    "guidance": f"Dispatched successfully via {attempt_label}",
                    "attempts": attempts_log,
                }

            except smtplib.SMTPAuthenticationError as e:
                last_error = e
                last_guidance = format_auth_error_message(eff_user, h, p, e)
                attempts_log.append(f"{attempt_label} -> AuthError(535)")
                # Fatal: Bad password / 2FA issue will fail across all ports & hosts in this datacenter
                fatal_stop = True
                break

            except smtplib.SMTPSenderRefused as e:
                last_error = e
                last_guidance = format_relay_error_message(eff_user, str(msg.get("From")), e)
                attempts_log.append(f"{attempt_label} -> SenderRefused({e.smtp_code})")
                fatal_stop = True
                break

            except smtplib.SMTPResponseException as e:
                last_error = e
                attempts_log.append(f"{attempt_label} -> SMTPError({e.smtp_code})")
                if e.smtp_code == 553:
                    last_guidance = format_relay_error_message(eff_user, str(msg.get("From")), e)
                    fatal_stop = True
                    break
                else:
                    last_guidance = f"Zoho SMTP responded with error {e.smtp_code}: {e.smtp_error}"

            except (socket.timeout, TimeoutError) as e:
                last_error = e
                last_guidance = format_network_error_message(h, p, timeout, e)
                attempts_log.append(f"{attempt_label} -> Timeout")
                continue

            except (ConnectionRefusedError, OSError) as e:
                last_error = e
                last_guidance = format_network_error_message(h, p, timeout, e)
                attempts_log.append(f"{attempt_label} -> ConnectionError: {e}")
                continue

            except smtplib.SMTPException as e:
                last_error = e
                last_guidance = f"Zoho SMTP protocol error on {attempt_label}: {type(e).__name__}: {e}"
                attempts_log.append(f"{attempt_label} -> SMTPException: {e}")
                continue

            except Exception as e:
                last_error = e
                last_guidance = f"Unexpected SMTP error on {attempt_label}: {type(e).__name__}: {e}"
                attempts_log.append(f"{attempt_label} -> {type(e).__name__}: {e}")
                continue

    return {
        "success": False,
        "mode": "smtp_error",
        "host_used": hosts_to_try[0] if hosts_to_try else None,
        "port_used": eff_port,
        "user_used": eff_user,
        "error": str(last_error) if last_error else "All SMTP connection attempts failed.",
        "guidance": last_guidance or "Check SMTP host, port, credentials, and network firewall.",
        "attempts": attempts_log,
    }
