"""
tests/generators/ground_truth_oracle.py

Independent, closed-form state-machine oracle computing exact verified discrepancies,
policy citations, and eligible claim windows against Amazon SP-API report data:
  - Warehouse Lost/Damaged: (Lost + Damaged) - (Found + Reimbursed + Disposed)
  - Customer Returns: Refunded orders without FC return receipt after 45-60 days
  - Dimensional Overcharge: Physical catalog specifications vs Amazon Cubiscan billing tier
  - Precision and Recall validation helpers (100% precision, 100% recall, $0.00 drift)
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import hashlib
from typing import Any, Dict, List, Optional, Tuple, Set


@dataclass
class OracleExpectedClaim:
    claim_id: str
    fnsku: str
    msku: str
    asin: str
    order_id: str
    transaction_id: str
    event_date: date
    discrepancy_type: str
    quantity: int
    unit_price: Decimal
    claim_amount: Decimal
    currency: str
    policy_citation: str
    policy_clause: str
    claim_window_days: int
    days_remaining: int
    claim_status: str
    evidence_notes: str
    fulfillment_center: str


@dataclass
class OracleVerificationResult:
    precision: float
    recall: float
    dollar_delta: Decimal
    matched_count: int
    expected_count: int
    actual_count: int
    false_positives: List[Any]
    false_negatives: List[Any]
    is_perfect_match: bool


class GroundTruthOracle:
    """
    Closed-form mathematical oracle that independently processes simulated
    or real SP-API ledgers to produce the ground-truth claim set.
    """

    POLICY_WAREHOUSE = "G200379860"
    CLAUSE_WAREHOUSE = "FBA inventory reimbursement policy: Fulfillment center operations claims"

    POLICY_RETURNS = "G200213130"
    CLAUSE_RETURNS = "Customer return claims policy G200213130"

    POLICY_DIMENSIONS = "G21213"
    CLAUSE_DIMENSIONS = "FBA weight and dimension overcharge policy"

    def __init__(self, as_of_date: date = date(2026, 9, 29)):
        self.as_of_date = as_of_date
        self.expected_claims: List[OracleExpectedClaim] = []

    def compute_deterministic_id(self, key: str) -> str:
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]

    def evaluate_warehouse_inventory(
        self,
        sku_info: Dict[str, Any],
        lost_units: int,
        damaged_units: int,
        found_units: int,
        reimbursed_units: int,
        disposed_units: int = 0,
        event_date: Optional[date] = None,
        fc: str = "PHX3"
    ) -> Optional[OracleExpectedClaim]:
        """
        Crosswalk: (Lost + Damaged) - (Found + Reimbursed + Disposed).
        """
        if event_date is None:
            event_date = self.as_of_date - timedelta(days=20)

        uncompensated = (lost_units + damaged_units) - (found_units + reimbursed_units + disposed_units)
        if uncompensated <= 0:
            return None

        # Check claim window: 60 days under 2024-2025 Seller Central rules
        elapsed_days = (self.as_of_date - event_date).days
        days_remaining = max(0, 60 - elapsed_days)
        is_expired = elapsed_days > 60

        price = Decimal(str(sku_info.get("unit_price", "19.99"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        claim_amount = (price * Decimal(uncompensated)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        key = f"WH:{sku_info['fnsku']}:{event_date}:{uncompensated}"
        claim_id = self.compute_deterministic_id(key)

        claim = OracleExpectedClaim(
            claim_id=claim_id,
            fnsku=sku_info["fnsku"],
            msku=sku_info.get("msku", ""),
            asin=sku_info.get("asin", ""),
            order_id="",
            transaction_id=f"TX-WH-{claim_id[:8]}",
            event_date=event_date,
            discrepancy_type="WAREHOUSE_LOST_DAMAGED",
            quantity=uncompensated,
            unit_price=price,
            claim_amount=claim_amount,
            currency="USD",
            policy_citation=self.POLICY_WAREHOUSE,
            policy_clause=self.CLAUSE_WAREHOUSE,
            claim_window_days=60,
            days_remaining=days_remaining,
            claim_status="EXPIRED" if is_expired else "ELIGIBLE",
            evidence_notes=f"Uncompensated balance: {lost_units} lost + {damaged_units} damaged - {found_units} found - {reimbursed_units} reimbursed - {disposed_units} disposed = {uncompensated} units",
            fulfillment_center=fc
        )
        self.expected_claims.append(claim)
        return claim

    def evaluate_customer_return(
        self,
        sku_info: Dict[str, Any],
        order_id: str,
        refund_date: date,
        return_receipt_date: Optional[date] = None,
        quantity: int = 1,
        is_reimbursed: bool = False,
        fc: str = "IND1"
    ) -> Optional[OracleExpectedClaim]:
        """
        Evaluates unreturned customer refunds against the 45-day waiting window.
        """
        # If already reimbursed or returned within 45 days, no discrepancy
        if is_reimbursed:
            return None

        if return_receipt_date is not None:
            days_to_return = (return_receipt_date - refund_date).days
            if days_to_return <= 45:
                return None

        # Calculate elapsed days since refund
        days_since_refund = (self.as_of_date - refund_date).days
        if days_since_refund <= 45:
            # 45-day grace period is still active, not claimable yet
            return None

        # Eligible after 45 days up to 105 days (60 days claim window)
        days_remaining = max(0, 105 - days_since_refund)
        is_expired = days_since_refund > 105

        price = Decimal(str(sku_info.get("unit_price", "19.99"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        claim_amount = (price * Decimal(quantity)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        key = f"RET:{order_id}:{sku_info['fnsku']}:{refund_date}"
        claim_id = self.compute_deterministic_id(key)

        claim = OracleExpectedClaim(
            claim_id=claim_id,
            fnsku=sku_info["fnsku"],
            msku=sku_info.get("msku", ""),
            asin=sku_info.get("asin", ""),
            order_id=order_id,
            transaction_id=f"TX-RET-{claim_id[:8]}",
            event_date=refund_date,
            discrepancy_type="CUSTOMER_RETURN_NOT_RETURNED",
            quantity=quantity,
            unit_price=price,
            claim_amount=claim_amount,
            currency="USD",
            policy_citation=self.POLICY_RETURNS,
            policy_clause=self.CLAUSE_RETURNS,
            claim_window_days=60,
            days_remaining=days_remaining,
            claim_status="EXPIRED" if is_expired else "ELIGIBLE",
            evidence_notes=f"Customer refunded on {refund_date.isoformat()}; physical unit not received at FC within 45 days ({days_since_refund} days elapsed)",
            fulfillment_center=fc
        )
        self.expected_claims.append(claim)
        return claim

    def evaluate_dimensional_overcharge(
        self,
        sku_info: Dict[str, Any],
        charged_fee_per_unit: Decimal,
        correct_fee_per_unit: Decimal,
        units_sold: int,
        detection_date: Optional[date] = None,
        fc: str = "ALL"
    ) -> Optional[OracleExpectedClaim]:
        """
        Evaluates size tier and dimensional weight overcharge deltas.
        """
        if detection_date is None:
            detection_date = self.as_of_date - timedelta(days=10)

        delta = charged_fee_per_unit - correct_fee_per_unit
        if delta <= Decimal("0.00"):
            return None

        total_overcharge = (delta * Decimal(units_sold)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        elapsed_days = (self.as_of_date - detection_date).days
        days_remaining = max(0, 60 - elapsed_days)
        is_expired = elapsed_days > 60

        key = f"DIM:{sku_info['fnsku']}:{charged_fee_per_unit}:{correct_fee_per_unit}:{units_sold}"
        claim_id = self.compute_deterministic_id(key)

        claim = OracleExpectedClaim(
            claim_id=claim_id,
            fnsku=sku_info["fnsku"],
            msku=sku_info.get("msku", ""),
            asin=sku_info.get("asin", ""),
            order_id="",
            transaction_id=f"TX-DIM-{claim_id[:8]}",
            event_date=detection_date,
            discrepancy_type="DIMENSIONAL_FEE_OVERCHARGE",
            quantity=units_sold,
            unit_price=delta,
            claim_amount=total_overcharge,
            currency="USD",
            policy_citation=self.POLICY_DIMENSIONS,
            policy_clause=self.CLAUSE_DIMENSIONS,
            claim_window_days=60,
            days_remaining=days_remaining,
            claim_status="EXPIRED" if is_expired else "ELIGIBLE",
            evidence_notes=f"Overcharged ${delta} per unit across {units_sold} units (Charged ${charged_fee_per_unit} vs Correct ${correct_fee_per_unit})",
            fulfillment_center=fc
        )
        self.expected_claims.append(claim)
        return claim

    def get_summary_kpis(self) -> Dict[str, Any]:
        total_amount = sum((c.claim_amount for c in self.expected_claims), Decimal("0.00"))
        total_units = sum(c.quantity for c in self.expected_claims)
        eligible_claims = [c for c in self.expected_claims if c.claim_status == "ELIGIBLE"]
        expired_claims = [c for c in self.expected_claims if c.claim_status == "EXPIRED"]

        by_type: Dict[str, Dict[str, Any]] = {}
        for c in self.expected_claims:
            if c.discrepancy_type not in by_type:
                by_type[c.discrepancy_type] = {"count": 0, "units": 0, "amount": Decimal("0.00")}
            by_type[c.discrepancy_type]["count"] += 1
            by_type[c.discrepancy_type]["units"] += c.quantity
            by_type[c.discrepancy_type]["amount"] += c.claim_amount

        return {
            "total_claims": len(self.expected_claims),
            "eligible_claims": len(eligible_claims),
            "expired_claims": len(expired_claims),
            "total_units": total_units,
            "total_amount": total_amount,
            "breakdown_by_type": by_type
        }

    def verify_engine_claims(self, engine_claims: List[Any]) -> OracleVerificationResult:
        """
        Validates engine claims against oracle claims:
          - Precision: matches / engine_count
          - Recall: matches / expected_count
          - Dollar Delta: |actual_total - expected_total|
        """
        expected_lookup: Dict[str, OracleExpectedClaim] = {}
        for exp in self.expected_claims:
            # Match signature: (fnsku, discrepancy_type, quantity, order_id)
            sig = f"{exp.fnsku}:{exp.discrepancy_type}:{exp.quantity}:{exp.order_id}"
            expected_lookup[sig] = exp

        matched = 0
        false_positives = []
        actual_total = Decimal("0.00")
        expected_total = sum((c.claim_amount for c in self.expected_claims), Decimal("0.00"))

        seen_sigs: Set[str] = set()

        for c in engine_claims:
            # Handle both object attributes and dict keys
            fnsku = getattr(c, "fnsku", None) or (c.get("fnsku") if isinstance(c, dict) else "")
            discrepancy_type = getattr(c, "discrepancy_type", None) or (c.get("discrepancy_type") if isinstance(c, dict) else "")
            quantity = getattr(c, "quantity", None) or (c.get("quantity") if isinstance(c, dict) else 0)
            order_id = getattr(c, "order_id", None) or (c.get("order_id") if isinstance(c, dict) else "")
            amount = getattr(c, "claim_amount", None) or (c.get("claim_amount") if isinstance(c, dict) else Decimal("0.00"))
            if not isinstance(amount, Decimal):
                amount = Decimal(str(amount))
            actual_total += amount

            sig = f"{fnsku}:{discrepancy_type}:{quantity}:{order_id}"
            if sig in expected_lookup and sig not in seen_sigs:
                matched += 1
                seen_sigs.add(sig)
            else:
                false_positives.append(c)

        false_negatives = [exp for sig, exp in expected_lookup.items() if sig not in seen_sigs]

        actual_count = len(engine_claims)
        expected_count = len(self.expected_claims)

        precision = (matched / actual_count) if actual_count > 0 else (1.0 if expected_count == 0 else 0.0)
        recall = (matched / expected_count) if expected_count > 0 else 1.0
        dollar_delta = abs(actual_total - expected_total)

        is_perfect = (precision == 1.0) and (recall == 1.0) and (dollar_delta == Decimal("0.00"))

        return OracleVerificationResult(
            precision=precision,
            recall=recall,
            dollar_delta=dollar_delta,
            matched_count=matched,
            expected_count=expected_count,
            actual_count=actual_count,
            false_positives=false_positives,
            false_negatives=false_negatives,
            is_perfect_match=is_perfect
        )
