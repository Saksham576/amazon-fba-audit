"""
Dimensional weight and fee overcharge reconciliation engine.
"""

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import hashlib
from typing import Any, Dict, List, Optional

from ..models.claims import ClaimRecord
from ..models.enums import DiscrepancyType
from ..models.reports import FeeEstimateRecord
from .policy_registry import PolicyCitationRegistry


def compute_size_tier(length: Decimal, width: Decimal, height: Decimal, weight: Decimal) -> str:
    """Computes Amazon FBA product size tier according to standard dimension boundaries."""
    dims = sorted([length, width, height], reverse=True)
    longest, median, shortest = dims[0], dims[1], dims[2]
    if longest <= Decimal("15.0") and median <= Decimal("12.0") and shortest <= Decimal("0.75") and weight <= Decimal("1.0"):
        return "Small Standard"
    elif longest <= Decimal("18.0") and median <= Decimal("14.0") and shortest <= Decimal("8.0") and weight <= Decimal("20.0"):
        return "Large Standard"
    elif longest <= Decimal("60.0") and (longest + 2 * (median + shortest)) <= Decimal("130.0") and weight <= Decimal("70.0"):
        return "Small Oversize"
    else:
        return "Medium Oversize"


def compute_dimensional_weight(length: Decimal, width: Decimal, height: Decimal) -> Decimal:
    """Computes dimensional weight in pounds using standard 139 divisor."""
    return ((length * width * height) / Decimal("139")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def compute_correct_fba_fee(length: Decimal, width: Decimal, height: Decimal, weight: Decimal) -> Decimal:
    """Computes correct Amazon FBA fulfillment fee based on physical dimensions and weight."""
    tier = compute_size_tier(length, width, height, weight)
    dim_w = compute_dimensional_weight(length, width, height)
    billable_w = max(weight, dim_w)

    if tier == "Small Standard":
        if billable_w <= Decimal("0.25"):
            return Decimal("3.22")
        elif billable_w <= Decimal("0.50"):
            return Decimal("3.40")
        elif billable_w <= Decimal("0.75"):
            return Decimal("3.58")
        else:
            return Decimal("3.77")
    elif tier == "Large Standard":
        if billable_w <= Decimal("0.25"):
            return Decimal("3.86")
        elif billable_w <= Decimal("0.50"):
            return Decimal("4.08")
        elif billable_w <= Decimal("0.75"):
            return Decimal("4.75")
        elif billable_w <= Decimal("1.00"):
            return Decimal("5.40")
        else:
            extra_half_lbs = ((billable_w - Decimal("1.0")) / Decimal("0.5")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            return Decimal("5.40") + (extra_half_lbs * Decimal("0.38"))
    elif tier == "Small Oversize":
        extra_lbs = max(Decimal("0"), billable_w - Decimal("1.0"))
        return Decimal("9.73") + (extra_lbs * Decimal("0.42"))
    else:
        extra_lbs = max(Decimal("0"), billable_w - Decimal("1.0"))
        return Decimal("19.05") + (extra_lbs * Decimal("0.42"))


class DimensionalOverchargeReconciler:
    """
    Reconciles fee estimates against catalog dimensions to detect Cubiscan measurement creep.
    Policy: G21213 (60-day claim window)
    """

    def __init__(self, as_of_date: date):
        self.as_of_date = as_of_date

    def _compute_deterministic_id(self, key: str) -> str:
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]

    def reconcile(
        self,
        fee_records: List[FeeEstimateRecord],
        catalog_specs: Optional[Dict[str, Dict[str, Any]]] = None,
        units_sold_map: Optional[Dict[str, int]] = None,
    ) -> List[ClaimRecord]:
        if catalog_specs is None:
            catalog_specs = {}
        if units_sold_map is None:
            units_sold_map = {}

        claims: List[ClaimRecord] = []

        for fee_rec in fee_records:
            fnsku = fee_rec.fnsku
            specs = catalog_specs.get(fnsku)
            if not specs:
                continue

            cat_l = Decimal(str(specs.get("length", "0.00")))
            cat_w = Decimal(str(specs.get("width", "0.00")))
            cat_h = Decimal(str(specs.get("height", "0.00")))
            cat_wt = Decimal(str(specs.get("weight", "0.00")))

            if cat_l == 0 or cat_w == 0 or cat_h == 0:
                continue

            correct_fee = compute_correct_fba_fee(cat_l, cat_w, cat_h, cat_wt)
            charged_fee = fee_rec.expected_fulfillment_fee_per_unit or fee_rec.estimated_fee_total

            delta = charged_fee - correct_fee
            if delta <= Decimal("0.00"):
                continue

            units_sold = units_sold_map.get(fnsku, specs.get("units_sold_90d", 100))
            total_overcharge = (delta * Decimal(units_sold)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            detection_date = self.as_of_date - timedelta(days=10)
            elapsed_days = (self.as_of_date - detection_date).days
            days_remaining = max(0, 60 - elapsed_days)
            is_expired = elapsed_days > 60

            key = f"DIM:{fnsku}:{charged_fee}:{correct_fee}:{units_sold}"
            claim_id = self._compute_deterministic_id(key)

            claim = ClaimRecord(
                claim_id=claim_id,
                fnsku=fnsku,
                msku=fee_rec.sku or specs.get("msku", ""),
                asin=fee_rec.asin or specs.get("asin", ""),
                order_id="",
                transaction_id=f"TX-DIM-{claim_id[:8]}",
                event_date=detection_date,
                discrepancy_type=DiscrepancyType.DIMENSIONAL_FEE_OVERCHARGE.value,
                quantity=units_sold,
                unit_price=delta,
                claim_amount=total_overcharge,
                currency="USD",
                policy_citation=PolicyCitationRegistry.POLICY_DIMENSIONS,
                policy_clause=PolicyCitationRegistry.CLAUSE_DIMENSIONS,
                claim_window_days=60,
                days_remaining=days_remaining,
                claim_status="EXPIRED" if is_expired else "ELIGIBLE",
                evidence_notes=(
                    f"Overcharged ${delta} per unit across {units_sold} units "
                    f"(Charged ${charged_fee} vs Correct ${correct_fee})"
                ),
                fulfillment_center="ALL",
            )
            claims.append(claim)

        return claims
