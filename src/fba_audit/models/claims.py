"""Claims and Executive Summary Domain Models for Amazon FBA Audits.

Defines ClaimRecord with deterministic UUID5 identification, CategoryBreakdown,
AuditSummary, and AuditResult models.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Union
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from fba_audit.models.enums import ClaimStatus, DiscrepancyType

CENT = Decimal("0.01")
NAMESPACE_FBA_AUDIT = uuid.NAMESPACE_DNS  # RFC 4122 DNS namespace


def generate_claim_id(
    fnsku: str,
    identifier: Optional[str],
    discrepancy_type: Union[DiscrepancyType, str],
    event_date: Union[date, datetime],
) -> str:
    """Generate deterministic RFC 4122 UUID5 string for a claim record.

    Guarantees reproducible claim IDs across re-runs without database lookups.
    """
    clean_id = (identifier or "NO_REF").strip()
    dt_str = event_date.isoformat() if hasattr(event_date, "isoformat") else str(event_date)
    dtype_str = discrepancy_type.value if hasattr(discrepancy_type, "value") else str(discrepancy_type)
    key = f"fba-audit:{fnsku.strip()}:{clean_id}:{dtype_str}:{dt_str}"
    return str(uuid.uuid5(NAMESPACE_FBA_AUDIT, key))


class ClaimRecord(BaseModel):
    """Immutable domain representation of an itemized FBA reimbursement claim.

    Conforms directly to the 19-column Seller Central export specification.
    """
    model_config = ConfigDict(frozen=True, extra="ignore", arbitrary_types_allowed=True)

    claim_id: str = Field(description="Deterministic RFC 4122 UUID5 identifier")
    fnsku: str = Field(description="Amazon Fulfillment Network SKU")
    msku: str = Field(default="", description="Merchant SKU")
    asin: str = Field(default="", description="Amazon Standard Identification Number")
    transaction_id: Optional[str] = Field(
        default="",
        description="Warehouse transaction or inventory movement reference ID"
    )
    order_id: Optional[str] = Field(
        default="",
        description="Customer order ID (for customer return discrepancies)"
    )
    event_date: date = Field(description="Date the discrepancy event occurred")
    discrepancy_type: Union[DiscrepancyType, str] = Field(
        description="Categorical discrepancy classification"
    )
    discrepancy_quantity: int = Field(
        default=1,
        description="Verified net unresolved units"
    )
    unit_reimbursement_estimate: Decimal = Field(
        default=Decimal("0.00"),
        description="Estimated fair reimbursement value per unit in Decimal currency"
    )
    total_reimbursement_estimate: Decimal = Field(
        default=Decimal("0.00"),
        description="Total verified claim value in Decimal currency"
    )
    currency: str = Field(default="USD", description="ISO 4217 currency code")
    policy_citation: str = Field(default="", description="Authoritative Amazon policy title or ID")
    policy_clause: str = Field(default="", description="Exact policy section / clause reference")
    claim_window_days: int = Field(default=60, description="Governing policy filing window in days")
    claim_expiration_date: Optional[date] = Field(
        default=None,
        description="Date after which claim is barred by policy"
    )
    days_until_expiration: int = Field(
        default=60,
        description="Filing days remaining relative to audit date"
    )
    claim_status: Union[ClaimStatus, str] = Field(
        default=ClaimStatus.ELIGIBLE,
        description="Actionable filing status of claim"
    )
    evidence_notes: str = Field(
        default="",
        description="Structured plain-text audit narrative with crosswalk proofs"
    )
    fulfillment_center: Optional[str] = Field(
        default="ALL",
        description="FC code or ALL"
    )

    @model_validator(mode="before")
    @classmethod
    def handle_compat_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Compatibility with quantity vs discrepancy_quantity
            if "discrepancy_quantity" not in data and "quantity" in data:
                data["discrepancy_quantity"] = data["quantity"]
            elif "quantity" not in data and "discrepancy_quantity" in data:
                data["quantity"] = data["discrepancy_quantity"]

            # Compatibility with unit_price vs unit_reimbursement_estimate
            if "unit_reimbursement_estimate" not in data and "unit_price" in data:
                data["unit_reimbursement_estimate"] = data["unit_price"]

            # Compatibility with claim_amount vs total_reimbursement_estimate
            if "total_reimbursement_estimate" not in data and "claim_amount" in data:
                data["total_reimbursement_estimate"] = data["claim_amount"]
            elif "total_reimbursement_estimate" in data and "claim_amount" not in data:
                data["claim_amount"] = data["total_reimbursement_estimate"]

            # Compatibility with days_remaining vs days_until_expiration
            if "days_until_expiration" not in data and "days_remaining" in data:
                data["days_until_expiration"] = data["days_remaining"]

            # If claim_expiration_date is missing, compute from event_date + window_days
            if not data.get("claim_expiration_date") and "event_date" in data:
                ed = data["event_date"]
                win = data.get("claim_window_days", 60)
                if isinstance(ed, date):
                    data["claim_expiration_date"] = ed + timedelta(days=win)

            # Ensure total_reimbursement_estimate is computed if zero
            qty = data.get("discrepancy_quantity") or data.get("quantity") or 1
            unit_est = data.get("unit_reimbursement_estimate") or data.get("unit_price")
            tot_est = data.get("total_reimbursement_estimate") or data.get("claim_amount")
            if (not tot_est or tot_est == Decimal("0.00")) and unit_est:
                if not isinstance(unit_est, Decimal):
                    unit_est = Decimal(str(unit_est))
                data["total_reimbursement_estimate"] = (unit_est * Decimal(qty)).quantize(CENT, rounding=ROUND_HALF_UP)
                data["claim_amount"] = data["total_reimbursement_estimate"]
        return data

    @property
    def quantity(self) -> int:
        return self.discrepancy_quantity

    @property
    def unit_price(self) -> Decimal:
        return self.unit_reimbursement_estimate

    @property
    def claim_amount(self) -> Decimal:
        return self.total_reimbursement_estimate

    @property
    def days_remaining(self) -> int:
        return self.days_until_expiration

    @property
    def is_eligible(self) -> bool:
        status_val = self.claim_status.value if hasattr(self.claim_status, "value") else str(self.claim_status)
        return status_val.upper() == "ELIGIBLE"

    @property
    def estimated_amount(self) -> Decimal:
        return self.total_reimbursement_estimate

    def to_19_col_dict(self) -> Dict[str, str]:
        """Format claim record as 19-column dictionary for Seller Central dispute upload."""
        exp_date_str = self.claim_expiration_date.isoformat() if self.claim_expiration_date else ""
        dtype_str = self.discrepancy_type.value if hasattr(self.discrepancy_type, "value") else str(self.discrepancy_type)
        status_str = self.claim_status.value if hasattr(self.claim_status, "value") else str(self.claim_status)

        return {
            "claim_id": self.claim_id,
            "fnsku": self.fnsku,
            "msku": self.msku,
            "asin": self.asin,
            "transaction_id": self.transaction_id or "",
            "order_id": self.order_id or "",
            "event_date": self.event_date.isoformat(),
            "discrepancy_type": dtype_str,
            "quantity": str(self.discrepancy_quantity),
            "unit_price": f"{self.unit_reimbursement_estimate:.2f}",
            "claim_amount": f"{self.total_reimbursement_estimate:.2f}",
            "currency": self.currency,
            "policy_citation": self.policy_citation,
            "policy_clause": self.policy_clause,
            "claim_window_days": str(self.claim_window_days),
            "claim_expiration_date": exp_date_str,
            "days_until_expiration": str(self.days_until_expiration),
            "claim_status": status_str,
            "evidence_notes": self.evidence_notes,
        }

    @classmethod
    def create(
        cls,
        fnsku: str,
        msku: str,
        asin: str,
        event_date: date,
        discrepancy_type: Union[DiscrepancyType, str],
        discrepancy_quantity: int,
        unit_reimbursement_estimate: Decimal,
        policy_citation: str,
        policy_clause: str,
        claim_window_days: int,
        claim_expiration_date: date,
        days_until_expiration: int,
        claim_status: Union[ClaimStatus, str],
        evidence_notes: str,
        transaction_id: Optional[str] = None,
        order_id: Optional[str] = None,
        currency: str = "USD",
        fulfillment_center: str = "ALL",
    ) -> "ClaimRecord":
        """Factory method computing deterministic claim_id and total reimbursement."""
        identifier = order_id or transaction_id
        cid = generate_claim_id(fnsku, identifier, discrepancy_type, event_date)
        total_estimate = (unit_reimbursement_estimate * Decimal(discrepancy_quantity)).quantize(
            CENT, rounding=ROUND_HALF_UP
        )
        return cls(
            claim_id=cid,
            fnsku=fnsku,
            msku=msku,
            asin=asin,
            transaction_id=transaction_id or "",
            order_id=order_id or "",
            event_date=event_date,
            discrepancy_type=discrepancy_type,
            discrepancy_quantity=discrepancy_quantity,
            unit_reimbursement_estimate=unit_reimbursement_estimate.quantize(CENT, rounding=ROUND_HALF_UP),
            total_reimbursement_estimate=total_estimate,
            currency=currency,
            policy_citation=policy_citation,
            policy_clause=policy_clause,
            claim_window_days=claim_window_days,
            claim_expiration_date=claim_expiration_date,
            days_until_expiration=days_until_expiration,
            claim_status=claim_status,
            evidence_notes=evidence_notes,
            fulfillment_center=fulfillment_center,
        )


class CategoryBreakdown(BaseModel):
    """Aggregate statistics for a specific category of discrepancy."""
    model_config = ConfigDict(frozen=True)

    discrepancy_type: Union[DiscrepancyType, str]
    total_claims: int
    total_units: int
    total_amount: Decimal
    currency: str = "USD"


class AuditSummary(BaseModel):
    """Executive high-level summary of reconciled audit findings."""
    model_config = ConfigDict(frozen=True, extra="ignore")

    audit_id: Optional[str] = Field(default=None, description="Unique audit run identifier")
    as_of_date: date = Field(description="Effective evaluation date for claim window calculations")
    generated_at: Optional[datetime] = Field(default=None, description="Timestamp when audit summary was computed")
    total_claims_count: int = Field(default=0, description="Total claim records count")
    total_claims: int = Field(default=0, description="Alias for total_claims_count")
    total_eligible_count: int = Field(default=0, description="Count of eligible claims")
    total_expired_count: int = Field(default=0, description="Count of expired claims")
    total_discrepancy_units: int = Field(default=0, description="Total unresolved units identified")
    total_claim_amount: Decimal = Field(default=Decimal("0.00"), description="Total monetary claim amount")
    total_verified_amount: Decimal = Field(default=Decimal("0.00"), description="Total verified amount")
    total_discrepancy_amount: Decimal = Field(default=Decimal("0.00"), description="Total discrepancy amount")
    currency: str = Field(default="USD", description="Currency code")
    eligible_claim_amount: Decimal = Field(default=Decimal("0.00"), description="Monetary sum eligible for filing")
    eligible_now_amount: Decimal = Field(default=Decimal("0.00"), description="Monetary sum immediately actionable")
    expired_claim_amount: Decimal = Field(default=Decimal("0.00"), description="Monetary sum expired")
    expired_amount: Decimal = Field(default=Decimal("0.00"), description="Expired amount")
    pending_return_amount: Decimal = Field(default=Decimal("0.00"), description="Monetary sum under return transit hold")
    amount_by_discrepancy_type: Dict[str, Decimal] = Field(default_factory=dict)
    units_by_discrepancy_type: Dict[str, int] = Field(default_factory=dict)
    category_breakdowns: List[CategoryBreakdown] = Field(default_factory=list)
    top_affected_skus: List[Dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def sync_compat_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Sync total_claims and total_claims_count
            if "total_claims_count" in data and "total_claims" not in data:
                data["total_claims"] = data["total_claims_count"]
            elif "total_claims" in data and "total_claims_count" not in data:
                data["total_claims_count"] = data["total_claims"]

            # Sync amounts
            tot = data.get("total_claim_amount") or data.get("total_verified_amount") or data.get("total_discrepancy_amount") or Decimal("0.00")
            data["total_claim_amount"] = tot
            data["total_verified_amount"] = tot
            data["total_discrepancy_amount"] = tot

            el = data.get("eligible_claim_amount") or data.get("eligible_now_amount") or Decimal("0.00")
            data["eligible_claim_amount"] = el
            data["eligible_now_amount"] = el

            ex = data.get("expired_claim_amount") or data.get("expired_amount") or Decimal("0.00")
            data["expired_claim_amount"] = ex
            data["expired_amount"] = ex
        return data


class AuditResult(BaseModel):
    """Aggregate result object containing claims and executive summary."""
    model_config = ConfigDict(frozen=True, extra="ignore")

    reconciled_at: datetime
    as_of_date: Optional[date] = None
    claims: List[ClaimRecord]
    summary: AuditSummary
