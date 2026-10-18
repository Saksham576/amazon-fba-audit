"""
Autonomous CRM and Outreach Dispatcher for Amazon FBA Brand Acquisition.
Maintains persistent state for lead outreach, automates multi-touch email sequences,
and tracks conversion from cold lead to audited client.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import smtplib
from typing import Any, Dict, List, Optional, Tuple

from .leads import BrandFinder, BrandLead, LeadStatus
from .outreach import OutreachGenerator, EmailMessage, OutreachSequence
from ..mailer import OWNER_EMAIL, SENDER_EMAIL
from ..zoho_smtp import get_smtp_credentials, sanitize_sender_headers, send_smtp_message


DEFAULT_CRM_DIR = Path("payouts/crm")
DEFAULT_CRM_STATE = DEFAULT_CRM_DIR / "crm_state.json"
DEFAULT_OUTBOX_DIR = DEFAULT_CRM_DIR / "outbox"


class AutonomousCRM:
    """
    Manages cold brand outreach pipeline and autonomous touchpoint scheduling.
    """

    def __init__(
        self,
        crm_dir: Optional[Path] = None,
        state_file: Optional[Path] = None,
        outbox_dir: Optional[Path] = None,
    ):
        self.crm_dir = Path(crm_dir) if crm_dir else DEFAULT_CRM_DIR
        self.state_file = Path(state_file) if state_file else (self.crm_dir / "crm_state.json")
        self.outbox_dir = Path(outbox_dir) if outbox_dir else (self.crm_dir / "outbox")
        self.generator = OutreachGenerator()

        self.crm_dir.mkdir(parents=True, exist_ok=True)
        self.outbox_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_state_initialized()

    def _ensure_state_initialized(self) -> None:
        if not self.state_file.exists():
            finder = BrandFinder()
            leads = finder.list_all()
            initial_state = {
                "version": "1.0",
                "last_run": None,
                "total_leads": len(leads),
                "active_pipeline_count": len(leads),
                "total_dispatched_touches": 0,
                "leads": {},
            }
            for lead in leads:
                initial_state["leads"][lead.brand_id] = {
                    "brand_id": lead.brand_id,
                    "brand_name": lead.brand_name,
                    "category": lead.category.value,
                    "decision_maker_name": lead.decision_maker.name,
                    "decision_maker_email": lead.decision_maker.email,
                    "estimated_monthly_volume_usd": float(lead.estimated_monthly_volume_usd),
                    "estimated_annual_discrepancy_usd": float(lead.estimated_annual_discrepancy_usd),
                    "potential_15_fee_usd": float(lead.estimated_contingency_fee_usd),
                    "current_step": 0,  # 0 = not yet contacted
                    "status": "NEW",
                    "history": [],
                    "next_touch_due": datetime.now(timezone.utc).isoformat(),
                }
            self.save_state(initial_state)

    def load_state(self) -> Dict[str, Any]:
        with open(self.state_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_state(self, state: Dict[str, Any]) -> None:
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

    def get_due_outreach_leads(self, as_of: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """
        Returns list of lead dicts whose next touchpoint is due.
        """
        now = as_of or datetime.now(timezone.utc)
        state = self.load_state()
        due: List[Dict[str, Any]] = []

        for lead_id, info in state["leads"].items():
            if info["status"] in ["REPLIED", "ONBOARDED", "DECLINED"]:
                continue
            if info["current_step"] >= 3:
                continue
            if info["current_step"] == 0:
                due.append(info)
                continue

            due_str = info.get("next_touch_due")
            if not due_str:
                due.append(info)
                continue

            try:
                due_dt = datetime.fromisoformat(due_str)
                if due_dt <= now:
                    due.append(info)
            except Exception:
                due.append(info)

        return due

    def dispatch_due_touches(
        self,
        max_batch_size: int = 10,
        as_of: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Processes pending outreach touchpoints, formats emails,
        and transmits or archives outbox receipts.
        """
        now = as_of or datetime.now(timezone.utc)
        state = self.load_state()
        due_leads = self.get_due_outreach_leads(now)[:max_batch_size]
        finder = BrandFinder()
        dispatched_records = []

        creds = get_smtp_credentials()
        eff_user = creds["user"] or SENDER_EMAIL
        batch_smtp_broken_reason: Optional[str] = None
        batch_smtp_broken_diagnostic: Optional[str] = None

        for lead_info in due_leads:
            brand_id = lead_info["brand_id"]
            lead = finder.get_lead(brand_id)
            if not lead:
                continue

            next_step = lead_info["current_step"] + 1
            if next_step > 3:
                continue

            seq = self.generator.generate_sequence(lead)
            email_msg = seq.get_step(next_step)
            if not email_msg:
                continue

            # Format MIME message
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            msg = MIMEMultipart("alternative")
            msg["Subject"] = email_msg.subject
            msg["From"] = f"{email_msg.sender_name} <{eff_user}>"
            msg["To"] = email_msg.recipient_email
            msg["Reply-To"] = email_msg.sender_email
            msg.attach(MIMEText(email_msg.text_content, "plain", "utf-8"))
            msg.attach(MIMEText(email_msg.html_content, "html", "utf-8"))

            # Strictly sanitize headers so From matches authenticated mailbox to prevent Zoho 553 error
            sanitize_sender_headers(msg, authenticated_user=eff_user, default_display_name=email_msg.sender_name)

            timestamp_str = now.strftime("%Y%m%d_%H%M%S")
            eml_filename = f"outreach_{brand_id}_step_{next_step}_{timestamp_str}.eml"
            eml_path = self.outbox_dir / eml_filename
            with open(eml_path, "w", encoding="utf-8") as f:
                f.write(msg.as_string())

            live_sent = False
            smtp_err = None
            smtp_diag = None
            host_used = None
            port_used = None

            if creds["has_credentials"]:
                if batch_smtp_broken_reason:
                    smtp_err = f"Skipped live delivery: prior connection in batch failed ({batch_smtp_broken_reason})"
                    smtp_diag = batch_smtp_broken_diagnostic
                else:
                    send_res = send_smtp_message(msg, timeout=10.0, auto_fallback=True)
                    live_sent = send_res["success"]
                    smtp_err = send_res["error"]
                    smtp_diag = send_res.get("guidance")
                    host_used = send_res.get("host_used")
                    port_used = send_res.get("port_used")

                    if not live_sent and smtp_err:
                        # Short circuit on network timeout / firewall block or auth failure to avoid cascading hangs
                        err_str = str(smtp_err).lower()
                        if "timed out" in err_str or "timeout" in err_str or "535" in err_str or "authentication failed" in err_str:
                            batch_smtp_broken_reason = smtp_err
                            batch_smtp_broken_diagnostic = smtp_diag

            # Update lead state
            delay_days = 3 if next_step < 3 else 0
            next_due_dt = now + timedelta(days=delay_days) if delay_days > 0 else None

            touch_record = {
                "step": next_step,
                "dispatched_at": now.isoformat(),
                "subject": email_msg.subject,
                "recipient": email_msg.recipient_email,
                "eml_file": str(eml_path),
                "live_smtp_sent": live_sent,
                "smtp_error": smtp_err,
                "smtp_diagnostic": smtp_diag,
                "host_used": host_used,
                "port_used": port_used,
            }

            target_lead = state["leads"].get(brand_id, lead_info)
            target_lead["current_step"] = next_step
            target_lead["status"] = f"STEP_{next_step}_CONTACTED"
            target_lead["next_touch_due"] = next_due_dt.isoformat() if next_due_dt else None
            target_lead.setdefault("history", []).append(touch_record)
            state["leads"][brand_id] = target_lead
            state["total_dispatched_touches"] = state.get("total_dispatched_touches", 0) + 1

            dispatched_records.append(touch_record)

        state["last_run"] = now.isoformat()
        self.save_state(state)
        return dispatched_records

    def print_pipeline_dashboard(self) -> None:
        state = self.load_state()
        print("\n" + "=" * 70)
        print("🎯 AUTONOMOUS FBA BRAND ACQUISITION & OUTREACH CRM")
        print("=" * 70)
        print(f"Total Prospect Brands: {len(state['leads'])}")
        print(f"Total Dispatched Email Touches: {state.get('total_dispatched_touches', 0)}")
        print(f"Last Pipeline Run: {state.get('last_run') or 'Never'}")
        print("-" * 70)
        print(f"{'Brand Name':<22} | {'Category':<15} | {'Step':<6} | {'Status':<16} | {'Upside'}")
        print("-" * 70)
        for lid, info in state["leads"].items():
            print(f"{info['brand_name'][:22]:<22} | {info['category'][:15]:<15} | {info['current_step']:<6} | {info['status']:<16} | ${info['estimated_annual_discrepancy_usd']:,.0f}")
        print("=" * 70 + "\n")
