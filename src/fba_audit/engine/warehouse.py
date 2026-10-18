"""
Warehouse Lost and Damaged inventory reconciliation engine.
"""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import hashlib
from typing import Dict, List, Optional

from ..models.claims import ClaimRecord
from ..models.enums import DiscrepancyType
from ..models.reports import LedgerDetailRecord, ReimbursementRecord
from .policy_registry import PolicyCitationRegistry


class WarehouseReconciler:
    """
    Reconciles warehouse operations inventory:
    Uncompensated Units = (Lost + Damaged) - (Found + Reimbursed + Disposed)
    Policy: G200379860 (60-day claim window)
    """

    def __init__(self, as_of_date: date):
        self.as_of_date = as_of_date

    def _compute_deterministic_id(self, key: str) -> str:
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]

    def reconcile(
        self,
        ledger_records: List[LedgerDetailRecord],
        reimbursement_records: Optional[List[ReimbursementRecord]] = None,
        sku_prices: Optional[Dict[str, Decimal]] = None,
    ) -> List[ClaimRecord]:
        if sku_prices is None:
            sku_prices = {}

        # Track external reimbursements by FNSKU
        reimbursed_counts: Dict[str, int] = defaultdict(int)
        if reimbursement_records:
            for r in reimbursement_records:
                if "lost" in r.reason.lower() or "damaged" in r.reason.lower() or not r.reason:
                    reimbursed_counts[r.fnsku] += r.quantity_reimbursed_total

        # Group ledger events by FNSKU
        by_fnsku: Dict[str, List[LedgerDetailRecord]] = defaultdict(list)
        for rec in ledger_records:
            by_fnsku[rec.fnsku].append(rec)

        claims: List[ClaimRecord] = []

        for fnsku, events in by_fnsku.items():
            lost = 0
            damaged = 0
            found = 0
            disposed = 0
            event_dates: List[date] = []
            fc = "ALL"
            asin = ""
            msku = ""

            for ev in events:
                et = ev.event_type.strip().lower()
                qty = abs(ev.quantity)
                if not asin and ev.asin:
                    asin = ev.asin
                if not msku and ev.msku:
                    msku = ev.msku
                if ev.fulfillment_center:
                    fc = ev.fulfillment_center

                if et == "lost":
                    lost += qty
                    event_dates.append(ev.date)
                elif et == "damaged":
                    damaged += qty
                    event_dates.append(ev.date)
                elif et == "found":
                    found += qty
                elif et == "disposed":
                    disposed += qty

            reimbursed = reimbursed_counts.get(fnsku, 0)
            uncompensated = (lost + damaged) - (found + reimbursed + disposed)

            if uncompensated <= 0:
                continue

            event_date = min(event_dates) if event_dates else (self.as_of_date - timedelta(days=20))
            elapsed_days = (self.as_of_date - event_date).days
            days_remaining = max(0, 60 - elapsed_days)
            is_expired = elapsed_days > 60

            price = sku_prices.get(fnsku, Decimal("19.99")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            claim_amount = (price * Decimal(uncompensated)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            key = f"WH:{fnsku}:{event_date}:{uncompensated}"
            claim_id = self._compute_deterministic_id(key)

            claim = ClaimRecord(
                claim_id=claim_id,
                fnsku=fnsku,
                msku=msku,
                asin=asin,
                order_id="",
                transaction_id=f"TX-WH-{claim_id[:8]}",
                event_date=event_date,
                discrepancy_type=DiscrepancyType.WAREHOUSE_LOST_DAMAGED.value,
                quantity=uncompensated,
                unit_price=price,
                claim_amount=claim_amount,
                currency="USD",
                policy_citation=PolicyCitationRegistry.POLICY_WAREHOUSE,
                policy_clause=PolicyCitationRegistry.CLAUSE_WAREHOUSE,
                claim_window_days=60,
                days_remaining=days_remaining,
                claim_status="EXPIRED" if is_expired else "ELIGIBLE",
                evidence_notes=(
                    f"Uncompensated balance: {lost} lost + {damaged} damaged - "
                    f"{found} found - {reimbursed} reimbursed - {disposed} disposed = {uncompensated} units"
                ),
                fulfillment_center=fc,
            )
            claims.append(claim)

        return claims
