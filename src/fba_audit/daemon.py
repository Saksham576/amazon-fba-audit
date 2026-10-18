"""
Autonomous Business Daemon for Amazon FBA Inventory Discrepancy & Reimbursement Audit.
Monitors inbound reports, performs deterministic audits, updates financial ledgers,
and dispatches payout alerts to the business owner (virajtiwari52@gmail.com).
"""

import argparse
from datetime import datetime, date
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Dict, List, Optional, Set, Tuple

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from .api import run_audit
from .mailer import PayoutMailer, OWNER_EMAIL
from .models import AuditResult, ClaimRecord


DEFAULT_INBOUND_DIR = Path("inbound_reports")
DEFAULT_OUTPUT_DIR = Path("audit_output")
DEFAULT_PAYOUTS_DIR = Path("payouts")
DEFAULT_LEDGER_FILE = DEFAULT_PAYOUTS_DIR / "payout_ledger.json"
CONTINGENCY_FEE_RATE = Decimal("0.15")  # 15% contingency fee


class AutonomousAuditDaemon:
    """
    100% autonomous reconciliation engine runner.
    """

    def __init__(
        self,
        inbound_dir: Optional[Path] = None,
        output_dir: Optional[Path] = None,
        payouts_dir: Optional[Path] = None,
    ):
        self.inbound_dir = Path(inbound_dir) if inbound_dir else DEFAULT_INBOUND_DIR
        self.output_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
        self.payouts_dir = Path(payouts_dir) if payouts_dir else DEFAULT_PAYOUTS_DIR
        self.ledger_file = self.payouts_dir / "payout_ledger.json"
        self.mailer = PayoutMailer(notifications_dir=self.payouts_dir / "notifications")

        self.inbound_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.payouts_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_inbound_readme()

    def _ensure_inbound_readme(self) -> None:
        readme_path = self.inbound_dir / "README.md"
        if not readme_path.exists():
            with open(readme_path, "w", encoding="utf-8") as f:
                f.write("""# Amazon SP-API Inbound Reports Directory

Drop raw Amazon Selling Partner API (SP-API) TSV/CSV reports here:
- `ledger*.tsv` -> GET_LEDGER_DETAIL_VIEW_DATA (warehouse inventory movements)
- `returns*.tsv` -> GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA (customer returns)
- `reimbursements*.tsv` -> GET_FBA_REIMBURSEMENT_DATA (Amazon reimbursement receipts)
- `fees*.tsv` -> GET_FBA_ESTIMATED_FBA_FEES_TXT_DATA (package dimensions & fee tiers)

The autonomous daemon monitors this directory, parses new reports,
reconciles discrepancies, generates dispute packages in /audit_output,
and emails payout notices (15% contingency) to virajtiwari52@gmail.com.
""")

    def load_ledger(self) -> Dict:
        if not self.ledger_file.exists():
            return {
                "business_name": "Autonomous Amazon FBA Audit & Reimbursement Engine",
                "owner_email": OWNER_EMAIL,
                "contingency_rate": float(CONTINGENCY_FEE_RATE),
                "total_recoverable_usd": 0.0,
                "total_earned_usd": 0.0,
                "total_collected_usd": 0.0,
                "processed_claim_hashes": [],
                "audit_runs": [],
            }
        try:
            with open(self.ledger_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {
                "business_name": "Autonomous Amazon FBA Audit & Reimbursement Engine",
                "owner_email": OWNER_EMAIL,
                "contingency_rate": float(CONTINGENCY_FEE_RATE),
                "total_recoverable_usd": 0.0,
                "total_earned_usd": 0.0,
                "total_collected_usd": 0.0,
                "processed_claim_hashes": [],
                "audit_runs": [],
            }

    def save_ledger(self, ledger_data: Dict) -> None:
        with open(self.ledger_file, "w", encoding="utf-8") as f:
            json.dump(ledger_data, f, indent=2)

    def _compute_claim_hash(self, claim: ClaimRecord) -> str:
        return claim.claim_id

    def discover_reports(self, target_dir: Optional[Path] = None) -> Tuple[Optional[Path], Optional[Path], Optional[Path], Optional[Path]]:
        directory = target_dir or self.inbound_dir
        ledger, returns, reimbursements, fees = None, None, None, None

        for file in sorted(directory.iterdir()):
            if file.is_file():
                name = file.name.lower()
                if "ledger" in name and not ledger:
                    ledger = file
                elif "return" in name and not returns:
                    returns = file
                elif "reimburse" in name and not reimbursements:
                    reimbursements = file
                elif ("fee" in name or "estimated" in name) and not fees:
                    fees = file

        return ledger, returns, reimbursements, fees

    def run_cycle(
        self,
        simulate_if_empty: bool = False,
        fixtures_dir: Optional[Path] = None,
        seller_id: str = "SELLER_ACCOUNT_PRIMARY",
    ) -> Dict:
        """
        Executes one full autonomous reconciliation cycle.
        Returns a dict summarizing the actions and payout results.
        """
        ledger_path, returns_path, reimb_path, fees_path = self.discover_reports()

        # If inbound is empty and simulate_if_empty is enabled, fallback to fixtures
        if not any([ledger_path, returns_path, reimb_path, fees_path]) and simulate_if_empty:
            fix_dir = fixtures_dir or Path("tests/fixtures")
            if fix_dir.exists():
                ledger_path, returns_path, reimb_path, fees_path = self.discover_reports(fix_dir)
                seller_id = f"{seller_id}_SIMULATION"

        if not any([ledger_path, returns_path, reimb_path, fees_path]):
            return {
                "status": "IDLE_NO_REPORTS",
                "message": f"No reports found in {self.inbound_dir.resolve()}. Drop SP-API files into inbound_reports/",
                "new_payout_cut": 0.0,
            }

        # Run the deterministic audit engine
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Executing audit engine for {seller_id}...")
        audit_res = run_audit(
            ledger_path=ledger_path,
            returns_path=returns_path,
            reimbursements_path=reimb_path,
            fees_path=fees_path,
            output_dir=self.output_dir,
        )

        ledger_data = self.load_ledger()
        previously_processed: Set[str] = set(ledger_data.get("processed_claim_hashes", []))

        # Detect new, unnotified eligible claims
        new_eligible_claims: List[ClaimRecord] = []
        new_eligible_amount = Decimal("0.00")
        new_claim_hashes: List[str] = []

        for claim in audit_res.claims:
            if claim.is_eligible and claim.estimated_amount > 0:
                chash = self._compute_claim_hash(claim)
                if chash not in previously_processed:
                    new_eligible_claims.append(claim)
                    new_eligible_amount += claim.estimated_amount
                    new_claim_hashes.append(chash)

        payout_due = (new_eligible_amount * CONTINGENCY_FEE_RATE).quantize(Decimal("0.01"))
        cycle_timestamp = datetime.now().isoformat()

        notification_meta = None
        if len(new_eligible_claims) > 0 and payout_due > 0:
            print(f"[PAYOUT READY] New actionable claims identified: ${payout_due:,.2f} fee from {len(new_eligible_claims)} claims!")
            print(f"   Dispatching alert to business owner at {OWNER_EMAIL}...")

            claims_csv = self.output_dir / "claims_batch.csv"
            dossier_html = self.output_dir / "audit_dossier.html"

            notification_meta = self.mailer.dispatch_payout_alert(
                seller_id=seller_id,
                total_claims_count=len(new_eligible_claims),
                eligible_amount=new_eligible_amount,
                payout_cut=payout_due,
                dossier_html_path=dossier_html,
                claims_csv_path=claims_csv,
            )

            # Update persistent ledger
            ledger_data["total_recoverable_usd"] = float(
                Decimal(str(ledger_data.get("total_recoverable_usd", 0.0))) + new_eligible_amount
            )
            ledger_data["total_earned_usd"] = float(
                Decimal(str(ledger_data.get("total_earned_usd", 0.0))) + payout_due
            )
            ledger_data["processed_claim_hashes"].extend(new_claim_hashes)

        # Log audit run history
        run_record = {
            "run_id": f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "timestamp": cycle_timestamp,
            "seller_id": seller_id,
            "total_claims": audit_res.summary.total_claims_count,
            "eligible_claims": audit_res.summary.total_eligible_count,
            "total_claim_amount": float(audit_res.summary.total_claim_amount),
            "eligible_amount": float(audit_res.summary.eligible_claim_amount),
            "new_claims_count": len(new_eligible_claims),
            "new_eligible_amount": float(new_eligible_amount),
            "payout_earned_usd": float(payout_due),
            "notification": notification_meta,
        }
        ledger_data.setdefault("audit_runs", []).append(run_record)
        self.save_ledger(ledger_data)

        return {
            "status": "COMPLETED",
            "run_id": run_record["run_id"],
            "seller_id": seller_id,
            "new_claims_count": len(new_eligible_claims),
            "new_eligible_amount": float(new_eligible_amount),
            "new_payout_cut": float(payout_due),
            "total_earned_usd": ledger_data["total_earned_usd"],
            "notification_meta": notification_meta,
        }

    def print_status(self) -> None:
        ledger = self.load_ledger()
        print("\n" + "=" * 60)
        print("[BUSINESS] AUTONOMOUS AMAZON FBA REIMBURSEMENT AUDIT ENGINE")
        print("=" * 60)
        print(f"Owner / Beneficiary: {ledger.get('owner_email', OWNER_EMAIL)}")
        print(f"Contingency Fee Rate: {ledger.get('contingency_rate', 0.15) * 100:.0f}%")
        print(f"Total Discrepancy Cash Recovered / Actionable: ${ledger.get('total_recoverable_usd', 0.0):,.2f}")
        print(f"Total Contingency Fees Earned: ${ledger.get('total_earned_usd', 0.0):,.2f}")
        print(f"Total Contingency Fees Collected: ${ledger.get('total_collected_usd', 0.0):,.2f}")
        print(f"Net Pending Collection: ${ledger.get('total_earned_usd', 0.0) - ledger.get('total_collected_usd', 0.0):,.2f}")
        print(f"Total Completed Audit Cycles: {len(ledger.get('audit_runs', []))}")
        print(f"Unique Claims Processed: {len(ledger.get('processed_claim_hashes', []))}")
        print(f"Inbound Reports Directory: {self.inbound_dir.resolve()}")
        print(f"Audit Deliverables Directory: {self.output_dir.resolve()}")
        print(f"Payout Notifications Directory: {self.payouts_dir.resolve() / 'notifications'}")
        print("=" * 60 + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="fba_daemon",
        description="Autonomous 24/7 Daemon for Amazon FBA Reimbursement Audit Business",
    )
    parser.add_argument("--once", action="store_true", help="Execute single audit cycle and exit")
    parser.add_argument("--loop", action="store_true", help="Run daemon continuously in background loop")
    parser.add_argument("--interval", type=int, default=3600, help="Interval in seconds between loop cycles (default: 3600s)")
    parser.add_argument("--simulate-if-empty", action="store_true", help="Fallback to test fixtures if inbound_reports is empty")
    parser.add_argument("--status", action="store_true", help="Display current business earnings and ledger stats")
    parser.add_argument("--seller", type=str, default="SELLER_PRIMARY", help="Seller account identifier")

    args = parser.parse_args()
    daemon = AutonomousAuditDaemon()

    if args.status:
        daemon.print_status()
        return 0

    if args.loop:
        print(f"[DAEMON] Starting Amazon FBA Autonomous Audit Daemon (Interval: {args.interval}s)...")
        daemon.print_status()
        try:
            while True:
                res = daemon.run_cycle(simulate_if_empty=args.simulate_if_empty, seller_id=args.seller)
                if res["new_payout_cut"] > 0:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Alert sent! ${res['new_payout_cut']:,.2f} ready for collection.")
                else:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Cycle check complete. {res.get('message', 'No new unnotified claims.')}")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nDaemon terminated by user.")
            return 0
    else:
        # Default: execute single cycle
        res = daemon.run_cycle(simulate_if_empty=args.simulate_if_empty, seller_id=args.seller)
        print(f"Cycle Result: {res['status']}")
        if res.get("new_payout_cut", 0) > 0:
            print(f"[PAYOUT] Payout Alert Dispatched: ${res['new_payout_cut']:,.2f}")
        daemon.print_status()
        return 0
        daemon.print_status()
        return 0


if __name__ == "__main__":
    sys.exit(main())
