"""
Customer return reconciliation engine enforcing 45-day hold and 60-day claim window.
"""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import hashlib
from typing import Dict, List, Optional, Set

from ..models.claims import ClaimRecord
from ..models.enums import DiscrepancyType
from ..models.reports import CustomerReturnRecord, ReimbursementRecord
from .policy_registry import PolicyCitationRegistry


class CustomerReturnReconciler:
    """
    Reconciles customer refunds:
    Items refunded must be returned to an FC within 45 days.
    If unreturned after 45 days, seller has a 60-day window (up to day 105) to claim.
    Policy: G200213130
    """

    def __init__(self, as_of_date: date):
        self.as_of_date = as_of_date

    def _compute_deterministic_id(self, key: str) -> str:
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]

    def reconcile(
        self,
        returns_records: List[CustomerReturnRecord],
        reimbursement_records: Optional[List[ReimbursementRecord]] = None,
        sku_prices: Optional[Dict[str, Decimal]] = None,
    ) -> List[ClaimRecord]:
        if sku_prices is None:
            sku_prices = {}

        # Set of order IDs already reimbursed
        reimbursed_orders: Set[str] = set()
        if reimbursement_records:
            for r in reimbursement_records:
                if r.amazon_order_id:
                    reimbursed_orders.add(r.amazon_order_id)

        claims: List[ClaimRecord] = []

        for ret in returns_records:
            order_id = getattr(ret, "order_id", None) or getattr(ret, "amazon_order_id", "")
            if order_id in reimbursed_orders:
                continue

            refund_date = ret.return_date.date() if hasattr(ret.return_date, "date") else ret.return_date
            days_since_refund = (self.as_of_date - refund_date).days

            # Under 45 days, hold is still active (not yet claimable)
            if days_since_refund <= 45:
                continue

            # Check if physical return was received within 45 days
            status_val = getattr(ret, "status", None)
            if status_val and str(status_val).lower() in ("unit returned", "received", "returned"):
                continue

            days_remaining = max(0, 105 - days_since_refund)
            is_expired = days_since_refund > 105

            price = sku_prices.get(ret.fnsku, Decimal("19.99")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            claim_amount = (price * Decimal(ret.quantity)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            key = f"RET:{ret.order_id}:{ret.fnsku}:{refund_date}"
            claim_id = self._compute_deterministic_id(key)

            claim = ClaimRecord(
                claim_id=claim_id,
                fnsku=ret.fnsku,
                msku=ret.sku,
                asin=ret.asin,
                order_id=ret.order_id,
                transaction_id=f"TX-RET-{claim_id[:8]}",
                event_date=refund_date,
                discrepancy_type=DiscrepancyType.CUSTOMER_RETURN_NOT_RETURNED.value,
                quantity=ret.quantity,
                unit_price=price,
                claim_amount=claim_amount,
                currency="USD",
                policy_citation=PolicyCitationRegistry.POLICY_RETURNS,
                policy_clause=PolicyCitationRegistry.CLAUSE_RETURNS,
                claim_window_days=60,
                days_remaining=days_remaining,
                claim_status="EXPIRED" if is_expired else "ELIGIBLE",
                evidence_notes=(
                    f"Customer refunded on {refund_date.isoformat()}; physical unit not received at FC "
                    f"within 45 days ({days_since_refund} days elapsed)"
                ),
                fulfillment_center=ret.fulfillment_center_id or "IND1",
            )
            claims.append(claim)

        return claims
