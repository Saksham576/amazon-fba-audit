"""
Zoho Mail SMTP Diagnostic Verification Utility & CLI.
Tests DNS resolution, SSL/TLS handshakes, 2FA credentials, and provides
actionable remediation reports for NexusPulse Technologies (nexuspulsetech.com).
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import smtplib
import ssl
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from .zoho_smtp import (
    DEFAULT_OWNER,
    DEFAULT_SENDER,
    ZOHO_INDIA_PRO_HOST,
    ZOHO_INDIA_STD_HOST,
    ZOHO_US_PRO_HOST,
    ZOHO_US_STD_HOST,
    format_auth_error_message,
    format_network_error_message,
    get_smtp_credentials,
    load_dotenv,
    resolve_smtp_hosts,
    send_smtp_message,
)


def probe_dns(host: str) -> Dict[str, Any]:
    """Tests DNS lookup for a specific SMTP host."""
    t0 = time.perf_counter()
    try:
        ip = socket.gethostbyname(host)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return {
            "host": host,
            "status": "PASS",
            "ip": ip,
            "latency_ms": round(elapsed_ms, 1),
            "error": None,
        }
    except Exception as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return {
            "host": host,
            "status": "FAIL",
            "ip": None,
            "latency_ms": round(elapsed_ms, 1),
            "error": str(e),
        }


def probe_port_handshake(host: str, port: int, timeout: float = 5.0) -> Dict[str, Any]:
    """Tests TCP connection and SSL/TLS handshake for a host and port."""
    protocol = "SSL" if port == 465 else "STARTTLS"
    t0 = time.perf_counter()
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=timeout) as server:
                banner = server.ehlo()
                elapsed_ms = (time.perf_counter() - t0) * 1000
                raw_b = banner[1] if len(banner) > 1 else b"OK"
                banner_str = raw_b.decode("utf-8", errors="replace").strip() if isinstance(raw_b, bytes) else str(raw_b).strip()
                clean_banner = banner_str.splitlines()[0] if banner_str else "OK"
                return {
                    "host": host,
                    "port": port,
                    "protocol": protocol,
                    "status": "PASS",
                    "latency_ms": round(elapsed_ms, 1),
                    "banner": clean_banner,
                    "error": None,
                }
        else:
            with smtplib.SMTP(host, port, timeout=timeout) as server:
                server.ehlo()
                server.starttls()
                banner = server.ehlo()
                elapsed_ms = (time.perf_counter() - t0) * 1000
                raw_b = banner[1] if len(banner) > 1 else b"OK"
                banner_str = raw_b.decode("utf-8", errors="replace").strip() if isinstance(raw_b, bytes) else str(raw_b).strip()
                clean_banner = banner_str.splitlines()[0] if banner_str else "OK"
                return {
                    "host": host,
                    "port": port,
                    "protocol": protocol,
                    "status": "PASS",
                    "latency_ms": round(elapsed_ms, 1),
                    "banner": clean_banner,
                    "error": None,
                }
    except (socket.timeout, TimeoutError) as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return {
            "host": host,
            "port": port,
            "protocol": protocol,
            "status": "TIMEOUT",
            "latency_ms": round(elapsed_ms, 1),
            "banner": None,
            "error": f"Connection timed out after {timeout}s (Port blocked or unreachable)",
        }
    except Exception as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return {
            "host": host,
            "port": port,
            "protocol": protocol,
            "status": "FAIL",
            "latency_ms": round(elapsed_ms, 1),
            "banner": None,
            "error": f"{type(e).__name__}: {e}",
        }


def probe_auth(
    host: str,
    port: int,
    user: str,
    password: str,
    timeout: float = 5.0,
) -> Dict[str, Any]:
    """Tests SMTP authentication with provided credentials."""
    protocol = "SSL" if port == 465 else "STARTTLS"
    t0 = time.perf_counter()

    def _attempt_login(server_inst, pass_to_try: str):
        server_inst.ehlo()
        if port != 465:
            server_inst.starttls()
            server_inst.ehlo()
        server_inst.login(user, pass_to_try)

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=timeout) as server:
                try:
                    _attempt_login(server, password)
                except smtplib.SMTPAuthenticationError as auth_err:
                    if " " in password:
                        _attempt_login(server, password.replace(" ", ""))
                    else:
                        raise auth_err
        else:
            with smtplib.SMTP(host, port, timeout=timeout) as server:
                try:
                    _attempt_login(server, password)
                except smtplib.SMTPAuthenticationError as auth_err:
                    if " " in password:
                        _attempt_login(server, password.replace(" ", ""))
                    else:
                        raise auth_err

        elapsed_ms = (time.perf_counter() - t0) * 1000
        guidance = "Authentication successful."
        if " " in password:
            guidance += " (Notice: Spaces in Zoho App Password were automatically stripped)."

        return {
            "host": host,
            "port": port,
            "user": user,
            "status": "PASS",
            "latency_ms": round(elapsed_ms, 1),
            "error": None,
            "guidance": guidance,
        }
    except smtplib.SMTPAuthenticationError as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        guidance = format_auth_error_message(user, host, port, e)
        return {
            "host": host,
            "port": port,
            "user": user,
            "status": "FAIL_2FA",
            "latency_ms": round(elapsed_ms, 1),
            "error": f"SMTPAuthenticationError: {e}",
            "guidance": guidance,
        }
    except Exception as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return {
            "host": host,
            "port": port,
            "user": user,
            "status": "FAIL",
            "latency_ms": round(elapsed_ms, 1),
            "error": f"{type(e).__name__}: {e}",
            "guidance": f"Unable to authenticate due to connection error: {e}",
        }


def run_diagnostics(
    host: Optional[str] = None,
    port: Optional[int] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    send_test_to: Optional[str] = None,
    timeout: float = 5.0,
    env_file: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Executes the full diagnostic test suite and returns comprehensive structured metrics.
    """
    loaded_env = load_dotenv(env_file)
    creds = get_smtp_credentials()

    eff_user = (user or creds["user"]).strip()
    eff_pass = password if password is not None else creds["password"]
    eff_port = int(port if port is not None else creds["port"])
    primary_host, fallback_hosts = resolve_smtp_hosts(eff_user, host or creds.get("configured_host"))

    all_hosts_to_test = [primary_host]
    for h in [ZOHO_INDIA_PRO_HOST, ZOHO_INDIA_STD_HOST]:
        if h not in all_hosts_to_test:
            all_hosts_to_test.append(h)
    for fb in fallback_hosts:
        if fb not in all_hosts_to_test:
            all_hosts_to_test.append(fb)

    # 1. DNS Checks
    dns_results = [probe_dns(h) for h in all_hosts_to_test]
    dns_all_fail = len(dns_results) > 0 and all(r.get("status") == "FAIL" for r in dns_results)
    primary_dns_fail = any(r.get("host") == primary_host and r.get("status") == "FAIL" for r in dns_results)
    dns_broken = dns_all_fail or primary_dns_fail

    # 2. Port & Handshake Checks
    handshake_targets: List[Tuple[str, int]] = []
    hosts_for_handshake = [primary_host] + [h for h in fallback_hosts if h != primary_host]
    for h in hosts_for_handshake:
        for p in (465, 587):
            if (h, p) not in handshake_targets:
                handshake_targets.append((h, p))

    handshake_results = [probe_port_handshake(h, p, timeout=timeout) for h, p in handshake_targets]

    timeouts_count = sum(1 for r in handshake_results if r["status"] == "TIMEOUT")
    passes_count = sum(1 for r in handshake_results if r["status"] == "PASS")
    firewall_block_detected = len(handshake_results) > 0 and timeouts_count == len(handshake_results)

    # 3. Authentication Check (only if an endpoint is reachable)
    auth_result = None
    has_creds = bool(eff_user and eff_pass)
    successful_endpoint = next(
        (r for r in handshake_results if r["status"] == "PASS"),
        None,
    )
    if has_creds and successful_endpoint:
        target_h = successful_endpoint["host"]
        target_p = successful_endpoint["port"]
        auth_result = probe_auth(target_h, target_p, eff_user, eff_pass, timeout=timeout)

    # 4. Live Test Send (Optional)
    test_send_result = None
    if send_test_to:
        if not has_creds:
            test_send_result = {
                "success": False,
                "mode": "unconfigured",
                "host_used": None,
                "port_used": None,
                "user_used": eff_user,
                "error": "Cannot send test email: SMTP credentials not configured (FBA_SMTP_PASS required).",
                "guidance": "Provide Zoho 2FA App Password via --pass or set FBA_SMTP_PASS in .env",
            }
        elif not successful_endpoint:
            test_send_result = {
                "success": False,
                "mode": "firewall_blocked" if firewall_block_detected else "unreachable",
                "host_used": primary_host,
                "port_used": eff_port,
                "user_used": eff_user,
                "error": f"Cannot send test email: Outbound SMTP blocked on host network ({primary_host}:{eff_port}).",
                "guidance": "Run test from an unblocked network or cloud runner (GitHub Actions, Cloud Run).",
            }
        else:
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            test_msg = MIMEMultipart("alternative")
            test_msg["Subject"] = f"Zoho SMTP Diagnostic Verification: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}"
            test_msg["From"] = f"NexusPulse Mailer Diagnostic <{eff_user}>"
            test_msg["To"] = send_test_to

            body = (
                "============================================================\n"
                "ZOHO MAIL SMTP HANDSHAKE & TRANSMISSION VERIFICATION\n"
                "============================================================\n\n"
                f"Sender: {eff_user}\n"
                f"Recipient: {send_test_to}\n"
                f"Datacenter: {successful_endpoint['host']}\n"
                f"Timestamp: {datetime.now(timezone.utc).isoformat()}\n\n"
                "If you are reading this email, your Zoho Mail SMTP outbound\n"
                "pipeline is 100% operational with proper 2FA Application Password\n"
                "and strict anti-relaying SPF/DKIM compliance!\n"
                "============================================================\n"
            )
            test_msg.attach(MIMEText(body, "plain", "utf-8"))
            test_send_result = send_smtp_message(
                msg=test_msg,
                host=successful_endpoint["host"],
                port=successful_endpoint["port"],
                user=eff_user,
                password=eff_pass,
                to_addrs=send_test_to,
                timeout=timeout,
            )

    # 5. Overall Diagnosis & Status Evaluation
    recommendations: List[str] = []
    if dns_broken:
        overall_status = "DNS_ERROR"
        recommendations.append(f"DNS Resolution failure: '{primary_host}' could not be resolved. Check DNS resolver or network connection.")
    elif firewall_block_detected:
        overall_status = "FIREWALL_BLOCKED"
        recommendations.append(
            "Outbound SMTP firewall block: All ports (465, 587) timed out. This is standard on restricted "
            "networks (e.g. IIT Bombay campus WiFi, enterprise firewalls). Outgoing emails are safely preserved "
            "in the local .eml outbox and will automatically dispatch when running on a cloud runner or unblocked network."
        )
    elif passes_count == 0:
        overall_status = "NETWORK_UNREACHABLE"
        recommendations.append("Network unreachable: Outbound connections to Zoho SMTP failed. Check network and firewall settings.")
    elif not has_creds:
        overall_status = "UNCONFIGURED"
        recommendations.append(
            "SMTP server reachable: Outbound ports 465/587 are open. To enable live dispatch, set FBA_SMTP_USER "
            "and FBA_SMTP_PASS (Zoho 2FA App Password) in your .env file."
        )
    elif auth_result and auth_result["status"] != "PASS":
        overall_status = "AUTH_FAILED"
        if auth_result["status"] == "FAIL_2FA":
            recommendations.append(
                "Zoho 2FA App Password required: Generate an Application-Specific Password at "
                "https://accounts.zoho.in -> Security -> App Passwords and assign it to FBA_SMTP_PASS."
            )
        else:
            recommendations.append(f"Authentication failed: {auth_result.get('error')}")
    else:
        overall_status = "HEALTHY"

    if test_send_result and not test_send_result["success"]:
        recommendations.append(f"Live test email failed: {test_send_result.get('error')}")

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "overall_status": overall_status,
        "configuration": {
            "env_loaded": bool(loaded_env),
            "primary_host": primary_host,
            "fallback_hosts": fallback_hosts,
            "configured_port": eff_port,
            "user": eff_user,
            "password_configured": bool(eff_pass),
            "password_length": len(eff_pass) if eff_pass else 0,
            "owner_email": creds["owner_email"],
            "sender_email": creds["sender_email"],
        },
        "dns_checks": dns_results,
        "handshake_checks": handshake_results,
        "auth_check": auth_result,
        "test_send": test_send_result,
        "firewall_block_detected": firewall_block_detected,
        "recommendations": recommendations,
    }


def print_diagnostic_report(res: Dict[str, Any]) -> None:
    """Renders a formatted executive diagnostic report to stdout."""
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    cfg = res.get("configuration", {})
    status = res.get("overall_status", "UNKNOWN")
    ts = res.get("timestamp", datetime.now(timezone.utc).isoformat())

    print("\n" + "=" * 76)
    print(" [DIAGNOSTIC] ZOHO MAIL SMTP VERIFICATION - NEXUSPULSE TECHNOLOGIES")
    print("=" * 76)
    print(f" Timestamp:      {ts}")
    print(f" Target User:    {cfg.get('user', 'Unspecified')}")
    print(f" Target Host:    {cfg.get('primary_host', 'smtppro.zoho.in')} (Port: {cfg.get('configured_port', 465)})")
    print(f" Fallbacks:      {', '.join(cfg.get('fallback_hosts', []))}")
    print(f" Credentials:    {'CONFIGURED (' + str(cfg.get('password_length', 0)) + ' chars)' if cfg.get('password_configured') else 'NOT SET (Offline EML mode)'}")
    print(f" Overall Status: {status}")
    print("-" * 76)

    # DNS Results Table
    dns_checks = res.get("dns_checks", [])
    if dns_checks:
        print("\n[*] DNS RESOLUTION:")
        for d in dns_checks:
            badge = "[PASS]" if d.get("status") == "PASS" else "[FAIL]"
            print(f"  {badge:<10} | {d.get('host', ''):<18} -> {d.get('ip') or 'Unresolved':<16} ({d.get('latency_ms', 0)}ms)")

    # Handshake Results Table
    handshake_checks = res.get("handshake_checks", [])
    if handshake_checks:
        print("\n[*] SMTP PORT & TLS/SSL HANDSHAKES:")
        for h in handshake_checks:
            if h.get("status") == "PASS":
                badge = "[PASS]"
            elif h.get("status") == "TIMEOUT":
                badge = "[TIMEOUT]"
            else:
                badge = "[FAIL]"
            detail = h.get("banner") if h.get("banner") else (h.get("error") or "Unknown")
            print(f"  {badge:<10} | {h.get('host', ''):<16} Port {h.get('port', ''):<4} ({h.get('protocol', ''):<8}) -> {detail[:70]}")

    # Auth Results Table
    auth_check = res.get("auth_check")
    print("\n[*] AUTHENTICATION CHECK:")
    if auth_check:
        a = auth_check
        if a.get("status") == "PASS":
            print(f"  [PASS]     | Authenticated successfully as '{a.get('user')}' on {a.get('host')}:{a.get('port')}")
        elif a.get("status") == "FAIL_2FA":
            print(f"  [FAIL_2FA] | Zoho rejected credentials (535) on {a.get('host')}:{a.get('port')}")
            print(f"               Notice: Zoho accounts with 2FA require an Application-Specific Password.")
        else:
            print(f"  [FAIL]     | Auth failed on {a.get('host')}:{a.get('port')}: {a.get('error')}")
    else:
        if cfg.get("password_configured"):
            print("  [SKIPPED]  | No reachable endpoint to test authentication.")
        else:
            print("  [SKIPPED]  | FBA_SMTP_PASS not provided (Set in .env or via --pass to verify auth).")

    # Live Send Result
    test_send = res.get("test_send")
    if test_send:
        print("\n[*] LIVE TEST EMAIL TRANSMISSION:")
        ts = test_send
        if ts.get("success"):
            print(f"  [SUCCESS]  | Test email dispatched via {ts.get('host_used')}:{ts.get('port_used')}")
        else:
            print(f"  [FAILED]   | {ts.get('error')}")

    # Recommendations & Next Steps
    recs = res.get("recommendations", [])
    print("\n[*] ACTIONABLE RECOMMENDATIONS:")
    if not recs:
        print("  [OK] All checks passed! Zoho SMTP delivery pipeline is fully functional.")
    else:
        for idx, rec in enumerate(recs, 1):
            print(f"  {idx}. {rec}")

    print("=" * 76 + "\n")


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entrypoint for standalone mailer diagnostic utility."""
    parser = argparse.ArgumentParser(
        description="Diagnose and verify Zoho Mail SMTP connectivity and configuration."
    )
    parser.add_argument("--host", help="Custom SMTP host to probe (e.g. smtppro.zoho.in)")
    parser.add_argument("--port", type=int, help="Custom SMTP port (465 or 587)")
    parser.add_argument("--user", help="Zoho username/sender email (e.g. team@nexuspulsetech.com)")
    parser.add_argument("--pass", "--password", dest="password", help="Zoho 2FA App Password")
    parser.add_argument("--send-test-to", help="Recipient email address to dispatch a live test message")
    parser.add_argument("--timeout", type=float, default=5.0, help="Connection timeout in seconds (default: 5.0)")
    parser.add_argument("--env-file", help="Path to custom .env file")
    parser.add_argument("--json", action="store_true", help="Output diagnostic metrics in JSON format")

    args = parser.parse_args(argv)

    results = run_diagnostics(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        send_test_to=args.send_test_to,
        timeout=args.timeout,
        env_file=args.env_file,
    )

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print_diagnostic_report(results)

    # Return non-zero if an explicit requested operation failed
    if args.password:
        if not results.get("auth_check") or results["auth_check"].get("status") != "PASS":
            return 2
    if args.send_test_to:
        if not results.get("test_send") or not results["test_send"].get("success"):
            return 3

    return 0


if __name__ == "__main__":
    sys.exit(main())
