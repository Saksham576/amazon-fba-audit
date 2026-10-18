"""
Markdown Executive Audit Dossier generator.
"""

from pathlib import Path
from typing import Union

from ..models.claims import AuditResult


def generate_markdown_dossier(result: AuditResult, output_path: Union[str, Path]) -> Path:
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    s = result.summary
    lines = [
        "# Amazon FBA Inventory Discrepancy & Reimbursement Audit Dossier",
        "",
        f"**Audit As-Of Date**: {s.as_of_date.isoformat()}  ",
        f"**Reconciled At**: {result.reconciled_at.strftime('%Y-%m-%d %H:%M:%S')}  ",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        "| Metric | Value |",
        "|:---|---:|",
        f"| **Total Verified Discrepancies** | **${s.total_claim_amount:,.2f}** ({s.total_discrepancy_units:,} units) |",
        f"| **Actionable Eligible Claims** | **${s.eligible_claim_amount:,.2f}** ({s.total_eligible_count:,} claims) |",
        f"| **Expired / Forfeited Claims** | ${s.expired_claim_amount:,.2f} ({s.total_expired_count:,} claims) |",
        "",
        "### Discrepancy Breakdown by Category",
        "",
        "| Category | Units | Recoverable Amount |",
        "|:---|---:|---:|",
    ]

    for dt, amt in s.amount_by_discrepancy_type.items():
        units = s.units_by_discrepancy_type.get(dt, 0)
        lines.append(f"| `{dt}` | {units:,} | ${amt:,.2f} |")

    lines.extend([
        "",
        "---",
        "",
        "## Itemized Claim Evidence Binder",
        "",
        "| Claim ID | SKU / FNSKU | Event Date | Type | Qty | Claim ($) | Status | Days Left | Policy |",
        "|:---|:---|:---|:---|---:|---:|:---|---:|:---|",
    ])

    for c in result.claims:
        lines.append(
            f"| `{c.claim_id[:10]}` | `{c.fnsku}` | {c.event_date.isoformat()} | {c.discrepancy_type} | "
            f"{c.quantity} | ${c.claim_amount:.2f} | **{c.claim_status}** | {c.days_remaining}d | `{c.policy_citation}` |"
        )

    lines.append("")

    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return p
