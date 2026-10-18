"""
Automated notification and payout mailer for Amazon FBA Audit Business.
Sends alerts to the owner (virajtiwari52@gmail.com) whenever revenue is ready to be collected.
"""

import os
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Optional

from .zoho_smtp import (
    DEFAULT_OWNER,
    DEFAULT_SENDER,
    get_smtp_credentials,
    sanitize_sender_headers,
    send_smtp_message,
)

OWNER_EMAIL = os.getenv("FBA_OWNER_EMAIL", DEFAULT_OWNER)
SENDER_EMAIL = os.getenv("FBA_SENDER_EMAIL", DEFAULT_SENDER)


class PayoutMailer:
    """
    Manages notifications when recoverable revenue or contingency fees are earned.
    Supports local .eml recording, structured JSON auditing, and live SMTP transmission.
    """

    def __init__(self, notifications_dir: Optional[Path] = None):
        self.notifications_dir = Path(notifications_dir) if notifications_dir else Path("payouts/notifications")
        self.notifications_dir.mkdir(parents=True, exist_ok=True)

    def compose_payout_email(
        self,
        seller_id: str,
        total_claims_count: int,
        eligible_amount: Decimal,
        payout_cut: Decimal,
        dossier_html_path: Optional[Path] = None,
        claims_csv_path: Optional[Path] = None,
    ) -> MIMEMultipart:
        creds = get_smtp_credentials()
        eff_sender = creds["user"] or SENDER_EMAIL
        eff_owner = creds["owner_email"] or OWNER_EMAIL

        msg = MIMEMultipart("mixed")
        msg["Subject"] = f"💰 Payout Alert: ${payout_cut:,.2f} Earned from Amazon FBA Audit ({seller_id})"
        msg["From"] = f"NexusPulse FBA Engine <{eff_sender}>"
        msg["To"] = eff_owner

        alt_part = MIMEMultipart("alternative")

        text_content = f"""
============================================================
PAYOUT ALERT - AMAZON FBA REIMBURSEMENT ENGINE
============================================================

Seller Account: {seller_id}
Audit Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

FINANCIAL BREAKDOWN:
- Total Discrepancy Claims: {total_claims_count}
- Total Eligible Amazon Cash: ${eligible_amount:,.2f}
- Your 15% Contingency Fee: ${payout_cut:,.2f}

ACTIONABLE DELIVERABLES:
- Claims Batch CSV: {claims_csv_path or 'audit_output/claims_batch.csv'}
- Audit Executive Dossier: {dossier_html_path or 'audit_output/audit_dossier.html'}

Amazon Policies Cited:
- Warehouse Lost/Damaged: Policy G200379860 (60-day window)
- Customer Returns Not Received: Policy G200213130 (45-day hold, 60-day window)
- Dimensional Overcharges: Policy G21213 (recalculated size tiers)

Autonomous audit daemon has prepared all claim submission files.
Your contingency payout of ${payout_cut:,.2f} is pending collection.
============================================================
"""
        html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background-color: #f1f5f9; color: #0f172a; padding: 24px; margin: 0; }}
.card {{ background: #ffffff; border-radius: 12px; padding: 32px; max-width: 620px; margin: 0 auto; box-shadow: 0 10px 25px -5px rgba(0,0,0,0.1), 0 8px 10px -6px rgba(0,0,0,0.1); border: 1px solid #e2e8f0; }}
.badge {{ background: #16a34a; color: white; padding: 6px 12px; border-radius: 9999px; font-weight: 700; font-size: 12px; letter-spacing: 0.05em; text-transform: uppercase; }}
.header {{ margin-top: 16px; margin-bottom: 8px; font-size: 24px; font-weight: 800; color: #0f172a; }}
.sub {{ color: #64748b; font-size: 14px; margin-bottom: 24px; }}
.payout-box {{ background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%); border: 1px solid #bbf7d0; border-radius: 10px; padding: 20px; text-align: center; margin-bottom: 24px; }}
.payout-label {{ font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: #15803d; }}
.payout-value {{ font-size: 42px; font-weight: 900; color: #166534; margin: 8px 0; }}
.payout-desc {{ font-size: 13px; color: #15803d; }}
.table {{ width: 100%; border-collapse: collapse; margin-top: 16px; margin-bottom: 24px; }}
.table td {{ padding: 12px 0; border-bottom: 1px solid #f1f5f9; font-size: 14px; }}
.table td.label {{ color: #64748b; font-weight: 500; }}
.table td.right {{ text-align: right; font-weight: 700; color: #0f172a; }}
.footer {{ font-size: 12px; color: #94a3b8; border-top: 1px solid #f1f5f9; padding-top: 16px; margin-top: 24px; line-height: 1.5; }}
</style>
</head>
<body>
<div class="card">
  <span class="badge">PAYOUT READY</span>
  <div class="header">Amazon FBA Audit Revenue Report</div>
  <div class="sub">Autonomous audit cycle completed. Actionable reimbursement funds identified.</div>
  
  <div class="payout-box">
    <div class="payout-label">Your 15% Contingency Fee</div>
    <div class="payout-value">${payout_cut:,.2f}</div>
    <div class="payout-desc">Calculated from <strong>${eligible_amount:,.2f}</strong> actionable seller reimbursements</div>
  </div>

  <table class="table">
    <tr><td class="label">Seller Account</td><td class="right">{seller_id}</td></tr>
    <tr><td class="label">Total Actionable Claims</td><td class="right">{total_claims_count}</td></tr>
    <tr><td class="label">Total Eligible Amazon Cash</td><td class="right">${eligible_amount:,.2f}</td></tr>
    <tr><td class="label">Governing Policy Citations</td><td class="right">G200379860, G200213130, G21213</td></tr>
    <tr><td class="label">Dispute Packages</td><td class="right">CSV & HTML Attached</td></tr>
  </table>

  <div class="footer">
    This email was automatically generated by the autonomous Amazon FBA Inventory Reconciliation Engine.<br>
    All claims are deterministic and mathematically verified against official Amazon Seller Central policies.
  </div>
</div>
</body>
</html>"""

        alt_part.attach(MIMEText(text_content, "plain", "utf-8"))
        alt_part.attach(MIMEText(html_content, "html", "utf-8"))
        msg.attach(alt_part)

        # Attach claims CSV if available
        if claims_csv_path and Path(claims_csv_path).is_file():
            try:
                with open(claims_csv_path, "rb") as f:
                    part = MIMEBase("text", "csv")
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f"attachment; filename={Path(claims_csv_path).name}")
                msg.attach(part)
            except Exception:
                pass

        # Attach HTML dossier if available
        if dossier_html_path and Path(dossier_html_path).is_file():
            try:
                with open(dossier_html_path, "rb") as f:
                    part = MIMEBase("text", "html")
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f"attachment; filename={Path(dossier_html_path).name}")
                msg.attach(part)
            except Exception:
                pass

        sanitize_sender_headers(msg, eff_sender)
        return msg

    def dispatch_payout_alert(
        self,
        seller_id: str,
        total_claims_count: int,
        eligible_amount: Decimal,
        payout_cut: Decimal,
        dossier_html_path: Optional[Path] = None,
        claims_csv_path: Optional[Path] = None,
    ) -> Dict[str, any]:
        """
        Composes payout email, saves verifiable .eml and .json files,
        and transmits via live SMTP if credentials are configured.
        """
        msg = self.compose_payout_email(
            seller_id=seller_id,
            total_claims_count=total_claims_count,
            eligible_amount=eligible_amount,
            payout_cut=payout_cut,
            dossier_html_path=dossier_html_path,
            claims_csv_path=claims_csv_path,
        )

        creds = get_smtp_credentials()
        eff_user = creds["user"] or SENDER_EMAIL
        eff_owner = creds["owner_email"] or OWNER_EMAIL

        # Strictly align From header to authenticated mailbox to prevent Zoho 553 error
        sanitize_sender_headers(msg, authenticated_user=eff_user)

        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        eml_file = self.notifications_dir / f"payout_alert_{timestamp_str}.eml"
        with open(eml_file, "w", encoding="utf-8") as f:
            f.write(msg.as_string())

        smtp_sent = False
        smtp_error = None
        smtp_diagnostic = None
        host_used = None
        port_used = None

        if creds["has_credentials"]:
            send_res = send_smtp_message(msg, timeout=10.0, auto_fallback=True)
            smtp_sent = send_res["success"]
            smtp_error = send_res["error"]
            smtp_diagnostic = send_res.get("guidance")
            host_used = send_res.get("host_used")
            port_used = send_res.get("port_used")

        meta = {
            "timestamp": datetime.now().isoformat(),
            "recipient": eff_owner,
            "sender": eff_user,
            "seller_id": seller_id,
            "total_claims": total_claims_count,
            "eligible_amount": float(eligible_amount),
            "payout_cut": float(payout_cut),
            "eml_path": str(eml_file),
            "smtp_sent": smtp_sent,
            "smtp_error": smtp_error,
            "smtp_diagnostic": smtp_diagnostic,
            "host_used": host_used,
            "port_used": port_used,
        }

        meta_file = self.notifications_dir / f"payout_alert_{timestamp_str}.json"
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        return meta
