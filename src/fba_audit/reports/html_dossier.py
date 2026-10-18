"""
Standalone, self-contained HTML Executive Audit Dossier generator (zero external CDN dependencies).
"""

from pathlib import Path
from typing import Union

from ..models.claims import AuditResult


def generate_html_dossier(result: AuditResult, output_path: Union[str, Path]) -> Path:
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    s = result.summary

    breakdown_rows = ""
    for dt, amt in s.amount_by_discrepancy_type.items():
        units = s.units_by_discrepancy_type.get(dt, 0)
        breakdown_rows += f"""
        <tr>
            <td><code>{dt}</code></td>
            <td style="text-align: right;">{units:,}</td>
            <td style="text-align: right; font-weight: bold; color: #16a34a;">${amt:,.2f}</td>
        </tr>
        """

    claim_rows = ""
    for c in result.claims:
        badge_color = "#16a34a" if c.claim_status == "ELIGIBLE" else "#dc2626"
        claim_rows += f"""
        <tr>
            <td><code>{c.claim_id[:10]}</code></td>
            <td><strong>{c.fnsku}</strong><br><small style="color: #64748b;">{c.msku}</small></td>
            <td>{c.event_date.isoformat()}</td>
            <td><small>{c.discrepancy_type}</small></td>
            <td style="text-align: right;">{c.quantity}</td>
            <td style="text-align: right; font-weight: bold;">${c.claim_amount:.2f}</td>
            <td><span style="background-color: {badge_color}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;">{c.claim_status}</span></td>
            <td style="text-align: right;">{c.days_remaining}d</td>
            <td><span style="font-family: monospace; font-size: 12px;">{c.policy_citation}</span></td>
        </tr>
        """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Amazon FBA Audit Executive Dossier</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: #f8fafc;
            color: #0f172a;
            margin: 0;
            padding: 32px 16px;
        }}
        .container {{
            max-width: 1100px;
            margin: 0 auto;
            background: #ffffff;
            border-radius: 12px;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
            padding: 32px;
        }}
        .header {{
            border-bottom: 2px solid #e2e8f0;
            padding-bottom: 20px;
            margin-bottom: 24px;
        }}
        .header h1 {{
            margin: 0 0 8px 0;
            color: #0f172a;
            font-size: 26px;
        }}
        .header p {{
            margin: 0;
            color: #64748b;
            font-size: 14px;
        }}
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 16px;
            margin-bottom: 28px;
        }}
        .kpi-card {{
            background: #f1f5f9;
            padding: 16px;
            border-radius: 8px;
            border-left: 4px solid #3b82f6;
        }}
        .kpi-card.green {{ border-left-color: #16a34a; }}
        .kpi-card.red {{ border-left-color: #dc2626; }}
        .kpi-title {{
            font-size: 12px;
            font-weight: 600;
            color: #64748b;
            text-transform: uppercase;
            margin-bottom: 6px;
        }}
        .kpi-value {{
            font-size: 24px;
            font-weight: 700;
            color: #0f172a;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 16px;
            margin-bottom: 32px;
            font-size: 13px;
        }}
        th, td {{
            padding: 10px 12px;
            text-align: left;
            border-bottom: 1px solid #e2e8f0;
        }}
        th {{
            background-color: #f8fafc;
            color: #475569;
            font-weight: 600;
            font-size: 12px;
            text-transform: uppercase;
        }}
        tr:hover {{ background-color: #f8fafc; }}
        code {{
            background: #f1f5f9;
            padding: 2px 4px;
            border-radius: 4px;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Amazon FBA Inventory Discrepancy & Reimbursement Audit</h1>
            <p>Audit As-Of Date: <strong>{s.as_of_date.isoformat()}</strong> | Reconciled: <strong>{result.reconciled_at.strftime('%Y-%m-%d %H:%M:%S')}</strong></p>
        </div>

        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="kpi-title">Total Discrepancies</div>
                <div class="kpi-value">${s.total_claim_amount:,.2f}</div>
                <div style="font-size: 12px; color: #64748b; margin-top: 4px;">{s.total_discrepancy_units:,} units across {s.total_claims_count} claims</div>
            </div>
            <div class="kpi-card green">
                <div class="kpi-title">Actionable Eligible Claims</div>
                <div class="kpi-value" style="color: #16a34a;">${s.eligible_claim_amount:,.2f}</div>
                <div style="font-size: 12px; color: #64748b; margin-top: 4px;">{s.total_eligible_count} claims ready to file</div>
            </div>
            <div class="kpi-card red">
                <div class="kpi-title">Expired / Forfeited</div>
                <div class="kpi-value" style="color: #dc2626;">${s.expired_claim_amount:,.2f}</div>
                <div style="font-size: 12px; color: #64748b; margin-top: 4px;">{s.total_expired_count} claims past 60-day window</div>
            </div>
        </div>

        <h3>Discrepancy Breakdown by Category</h3>
        <table>
            <thead>
                <tr>
                    <th>Category</th>
                    <th style="text-align: right;">Units</th>
                    <th style="text-align: right;">Recoverable Cash</th>
                </tr>
            </thead>
            <tbody>
                {breakdown_rows}
            </tbody>
        </table>

        <h3>Itemized Claim Evidence Binder</h3>
        <table>
            <thead>
                <tr>
                    <th>Claim ID</th>
                    <th>FNSKU / SKU</th>
                    <th>Event Date</th>
                    <th>Discrepancy Type</th>
                    <th style="text-align: right;">Qty</th>
                    <th style="text-align: right;">Amount</th>
                    <th>Status</th>
                    <th style="text-align: right;">Days Left</th>
                    <th>Policy Citation</th>
                </tr>
            </thead>
            <tbody>
                {claim_rows}
            </tbody>
        </table>
    </div>
</body>
</html>
"""
    with open(p, "w", encoding="utf-8") as f:
        f.write(html)
    return p
