"""
GitHub Actions Step Summary and Payout Report Generator.
Formats autonomous audit cycle results, ledger metrics, and payout alerts
for display in $GITHUB_STEP_SUMMARY.
"""

import glob
import json
import os
from pathlib import Path
import sys
from typing import List, Optional


def generate_github_step_summary(
    payouts_dir: Optional[Path] = None,
    summary_path: Optional[str] = None,
) -> str:
    p_dir = Path(payouts_dir) if payouts_dir else Path("payouts")
    ledger_path = p_dir / "payout_ledger.json"
    notifications = sorted(glob.glob(str(p_dir / "notifications" / "*.json")))

    lines: List[str] = []
    lines.append("## 💰 Cloud Autonomous FBA Audit & Payout Report")
    lines.append("**Beneficiary Owner:** `virajtiwari52@gmail.com`")
    lines.append("**Governing Policies:** Amazon Help Hub G200379860, G200213130, G21213\n")

    if ledger_path.exists():
        try:
            with open(ledger_path, "r", encoding="utf-8") as f:
                ld = json.load(f)
            lines.append("### Payout Ledger Status")
            lines.append(f"- **Total Recoverable Identified:** ${ld.get('total_recoverable_usd', 0.0):,.2f}")
            lines.append(f"- **Total Contingency Fees (15%):** ${ld.get('total_earned_usd', 0.0):,.2f}")
            lines.append(f"- **Total Audited Cycles:** {len(ld.get('audit_runs', []))}")
            lines.append(f"- **Unique Claim Hashes Processed:** {len(ld.get('processed_claim_hashes', []))}\n")
        except Exception as e:
            lines.append(f"*(Could not read ledger: {e})*\n")

    if notifications:
        latest = notifications[-1]
        try:
            with open(latest, "r", encoding="utf-8") as f:
                nd = json.load(f)
            lines.append("### Latest Payout Notification Alert")
            lines.append(f"- **Recipient:** `{nd.get('recipient', 'virajtiwari52@gmail.com')}`")
            lines.append(f"- **Actionable Claims:** {nd.get('total_claims', 0)}")
            lines.append(f"- **Net Payout Fee:** ${nd.get('payout_cut', 0.0):,.2f}")
            lines.append(f"- **SMTP Delivery:** {'Transmitted via Live SMTP' if nd.get('smtp_sent') else 'Recorded to .eml file in artifacts'}")
            lines.append(f"- **EML File Record:** `{nd.get('eml_path', 'N/A')}`")
        except Exception as e:
            lines.append(f"*(Could not read latest notification: {e})*")
    else:
        lines.append("*(No new unnotified claims generated in this cycle)*")

    output_text = "\n".join(lines) + "\n"

    target_summary = summary_path or os.environ.get("GITHUB_STEP_SUMMARY")
    if target_summary:
        try:
            with open(target_summary, "a", encoding="utf-8") as f:
                f.write(output_text)
        except Exception:
            pass

    return output_text


def main() -> int:
    output_text = generate_github_step_summary()
    print(output_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
