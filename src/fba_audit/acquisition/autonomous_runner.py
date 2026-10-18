"""
Autonomous Business Executive Runner for Amazon FBA Reimbursement Engine.
Unifies lead prospecting, cold outreach dispatch, report audit reconciliation,
financial ledger maintenance, and owner payout alerts in a single autonomous pipeline.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from .crm import AutonomousCRM
from ..daemon import AutonomousAuditDaemon, CONTINGENCY_FEE_RATE
from ..mailer import OWNER_EMAIL


def run_autonomous_business_cycle(
    max_outreach_batch: int = 5,
    simulate_audit: bool = True,
    seller_id: str = "PRIMARY_AUTONOMOUS_PIPELINE",
) -> Dict[str, Any]:
    """
    Executes the full automated business cycle:
    1. Dispatches due marketing & outreach touchpoints to prospective brands.
    2. Runs the inventory reconciliation audit engine.
    3. Updates CRM and financial ledgers.
    4. Triggers payout alert notifications if money is ready for collection.
    """
    now = datetime.now(timezone.utc)
    print("=" * 70)
    print(f"🚀 [AUTONOMOUS ENGINE] Business Execution Cycle Started: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 70)

    # 1. Autonomous Outreach Pipeline
    crm = AutonomousCRM()
    print("\n[STEP 1/3] Executing Autonomous CRM Brand Outreach...")
    dispatched_touches = crm.dispatch_due_touches(max_batch_size=max_outreach_batch, as_of=now)
    print(f"-> Dispatched {len(dispatched_touches)} personalized outreach touchpoints.")
    for d in dispatched_touches:
        print(f"   • Step {d['step']} -> {d['recipient']} ({d['subject'][:45]}...)")

    # 2. Autonomous Audit & Reconciliation Pipeline
    print("\n[STEP 2/3] Executing Amazon Inventory Discrepancy Reconciliation...")
    daemon = AutonomousAuditDaemon()
    audit_res = daemon.run_cycle(simulate_if_empty=simulate_audit, seller_id=seller_id)
    print(f"-> Audit Cycle Status: {audit_res['status']}")
    print(f"-> Actionable Discrepancy Cash: ${audit_res.get('new_eligible_amount', 0.0):,.2f}")
    print(f"-> Your 15% Contingency Fee: ${audit_res.get('new_payout_cut', 0.0):,.2f}")

    # 3. Print Dashboards
    print("\n[STEP 3/3] Financial & Pipeline Executive Summary:")
    daemon.print_status()
    crm.print_pipeline_dashboard()

    # Step Summary for GitHub Actions or Terminal
    summary_md = f"""# 🚀 Autonomous Amazon FBA Business Cycle Report

**Execution Time**: `{now.strftime('%Y-%m-%d %H:%M:%S UTC')}`  
**Beneficiary**: `{OWNER_EMAIL}`  

### 📈 Marketing & Outreach Engine
- **Active Target Brands**: `{len(crm.load_state()['leads'])}`
- **Touches Dispatched This Run**: `{len(dispatched_touches)}`
- **Total Historical Outreach Touches**: `{crm.load_state().get('total_dispatched_touches', 0)}`

### 💰 Audit & Payout Engine
- **Audit Cycle Status**: `{audit_res['status']}`
- **New Recoverable Cash Identified**: `${audit_res.get('new_eligible_amount', 0.0):,.2f}`
- **New Contingency Fee Earned (15%)**: `${audit_res.get('new_payout_cut', 0.0):,.2f}`
- **Total Accumulated Payouts**: `${audit_res.get('total_earned_usd', 0.0):,.2f}`

*All claims are mathematically reconciled against Amazon Policies G200379860 and G200213130.*
"""

    summary_file = Path("payouts/last_cycle_summary.md")
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(summary_md)

    github_step_summary = os.getenv("GITHUB_STEP_SUMMARY")
    if github_step_summary:
        with open(github_step_summary, "a", encoding="utf-8") as f:
            f.write("\n" + summary_md + "\n")

    return {
        "timestamp": now.isoformat(),
        "dispatched_touches_count": len(dispatched_touches),
        "audit_result": audit_res,
        "summary_markdown_path": str(summary_file),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="fba_autonomous_runner",
        description="Run unified 100% autonomous Amazon FBA audit business cycle",
    )
    parser.add_argument("--batch-size", type=int, default=5, help="Max cold outreach emails to dispatch per run")
    parser.add_argument("--simulate-audit", action="store_true", default=True, help="Simulate audit if inbound reports empty")
    parser.add_argument("--seller", type=str, default="PRIMARY_AUTONOMOUS_PIPELINE", help="Seller identifier")

    args = parser.parse_args()
    run_autonomous_business_cycle(
        max_outreach_batch=args.batch_size,
        simulate_audit=args.simulate_audit,
        seller_id=args.seller,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
