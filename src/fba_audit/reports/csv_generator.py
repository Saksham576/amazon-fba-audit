"""
Itemized CSV claim batch exporter conforming to Seller Central dispute format.
"""

import csv
from pathlib import Path
from typing import List, Union

from ..models.claims import ClaimRecord

CSV_HEADERS = [
    "claim_id",
    "fnsku",
    "msku",
    "asin",
    "order_id",
    "transaction_id",
    "event_date",
    "discrepancy_type",
    "quantity",
    "unit_price",
    "claim_amount",
    "currency",
    "policy_citation",
    "policy_clause",
    "claim_window_days",
    "days_remaining",
    "claim_status",
    "evidence_notes",
    "fulfillment_center",
]


def export_claim_batch_csv(claims: List[ClaimRecord], output_path: Union[str, Path]) -> Path:
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    with open(p, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADERS)
        for c in claims:
            writer.writerow([
                c.claim_id,
                c.fnsku,
                c.msku,
                c.asin,
                c.order_id,
                c.transaction_id,
                c.event_date.isoformat(),
                c.discrepancy_type,
                c.quantity,
                str(c.unit_price),
                str(c.claim_amount),
                c.currency,
                c.policy_citation,
                c.policy_clause,
                c.claim_window_days,
                c.days_remaining,
                c.claim_status,
                c.evidence_notes,
                c.fulfillment_center,
            ])
    return p
