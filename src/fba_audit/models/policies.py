"""Authoritative Policy Citations and Claim Window Calculation Models.

Encodes Amazon Seller Central Help Hub references (G200213130, G200379860,
G200453320, G21213) and calculates strict temporal claim boundaries.
"""

from datetime import date, timedelta
from typing import Dict, List, Union
from pydantic import BaseModel, ConfigDict, Field

from fba_audit.models.enums import ClaimStatus, DiscrepancyType, PolicyCode


class PolicyCitation(BaseModel):
    """Authoritative citation mapping for an Amazon reimbursement policy."""
    model_config = ConfigDict(frozen=True)

    code: PolicyCode = Field(description="Internal policy code enum")
    name: str = Field(description="Official policy title in Seller Central")
    help_hub_id: str = Field(description="Authoritative Seller Central Help Hub ID (e.g. G200213130)")
    url: str = Field(description="Direct URL to Seller Central Help documentation")
    clause_reference: str = Field(description="Specific clause text and rule section")
    governing_claim_types: List[DiscrepancyType] = Field(description="Applicable discrepancy categories")
    liable_party: str = Field(description="Entity responsible for reimbursement: Amazon, Carrier, Customer")
    standard_window_days: int = Field(description="Filing window duration in days")


class ClaimWindow(BaseModel):
    """Calculated temporal claim validity window relative to evaluation date."""
    model_config = ConfigDict(frozen=True)

    event_date: date = Field(description="Date the underlying transaction occurred")
    as_of_date: date = Field(description="Audit evaluation date (clock fixture)")
    window_days: int = Field(description="Total allowed filing window in days")
    hold_days: int = Field(default=0, description="Mandatory waiting period (e.g. 45 days for returns)")
    status: ClaimStatus = Field(description="Resulting claim status")
    expiration_date: date = Field(description="Absolute expiration date of claim")
    days_until_expiration: int = Field(description="Remaining days before claim is permanently barred")

    @classmethod
    def evaluate(
        cls,
        event_date: date,
        as_of_date: date,
        window_days: int = 60,
        hold_days: int = 0,
    ) -> "ClaimWindow":
        """Compute exact claim expiration date, remaining days, and status."""
        days_elapsed = (as_of_date - event_date).days
        expiration_date = event_date + timedelta(days=window_days)
        days_until_expiration = (expiration_date - as_of_date).days

        if days_elapsed < hold_days:
            status = ClaimStatus.PENDING_RETURN_WINDOW
        elif days_elapsed <= window_days:
            status = ClaimStatus.ELIGIBLE_NOW
        else:
            status = ClaimStatus.EXPIRED

        return cls(
            event_date=event_date,
            as_of_date=as_of_date,
            window_days=window_days,
            hold_days=hold_days,
            status=status,
            expiration_date=expiration_date,
            days_until_expiration=days_until_expiration,
        )


# Master Policy Citation Registry
POLICY_REGISTRY: Dict[PolicyCode, PolicyCitation] = {
    PolicyCode.POL_FBA_OPS: PolicyCitation(
        code=PolicyCode.POL_FBA_OPS,
        name="FBA inventory reimbursement policy: Fulfillment center operations claims",
        help_hub_id="G200213130",
        url="https://sellercentral.amazon.com/help/hub/reference/G200213130",
        clause_reference="Fulfillment center lost and damaged inventory policy clause",
        governing_claim_types=[
            DiscrepancyType.WAREHOUSE_LOST,
            DiscrepancyType.WAREHOUSE_DAMAGED,
            DiscrepancyType.WAREHOUSE_LOST_DAMAGED,
        ],
        liable_party="Amazon",
        standard_window_days=60,
    ),
    PolicyCode.POL_FBA_RET: PolicyCitation(
        code=PolicyCode.POL_FBA_RET,
        name="Customer return claims policy",
        help_hub_id="G200379860",
        url="https://sellercentral.amazon.com/help/hub/reference/G200379860",
        clause_reference="Policy G200213130 / G200379860 - Customer Return Reimbursement",
        governing_claim_types=[
            DiscrepancyType.CUSTOMER_RETURN_NOT_RECEIVED,
            DiscrepancyType.CARRIER_DAMAGED_RETURN,
            DiscrepancyType.CUSTOMER_RETURN_NOT_RETURNED,
        ],
        liable_party="Amazon / Return Carrier",
        standard_window_days=60,
    ),
    PolicyCode.POL_FBA_INB: PolicyCitation(
        code=PolicyCode.POL_FBA_INB,
        name="FBA claims policy: Inbound shipment claims",
        help_hub_id="G200453320",
        url="https://sellercentral.amazon.com/help/hub/reference/G200453320",
        clause_reference="Inbound shipment receiving discrepancy and loss policy",
        governing_claim_types=[
            DiscrepancyType.INBOUND_RECEIVING_DISCREPANCY,
        ],
        liable_party="Amazon / Partnered Carrier",
        standard_window_days=270,
    ),
    PolicyCode.POL_FBA_DIM: PolicyCitation(
        code=PolicyCode.POL_FBA_DIM,
        name="FBA Fee Reimbursement Policy: Weight and Dimensions",
        help_hub_id="G21213",
        url="https://sellercentral.amazon.com/help/hub/reference/G21213",
        clause_reference="Policy G21213 - FBA fulfillment fee overcharge remeasurement",
        governing_claim_types=[
            DiscrepancyType.DIMENSIONAL_WEIGHT_OVERCHARGE,
            DiscrepancyType.SIZE_TIER_OVERCHARGE,
            DiscrepancyType.DIMENSIONAL_FEE_OVERCHARGE,
        ],
        liable_party="Amazon",
        standard_window_days=90,
    ),
    PolicyCode.POL_FBA_REM: PolicyCitation(
        code=PolicyCode.POL_FBA_REM,
        name="FBA removal order claims policy",
        help_hub_id="G200213130",
        url="https://sellercentral.amazon.com/help/hub/reference/G200213130",
        clause_reference="Removal order lost or damaged in transit clause",
        governing_claim_types=[],
        liable_party="Amazon / Removal Carrier",
        standard_window_days=60,
    ),
}


def get_policy_citation(discrepancy_type: Union[DiscrepancyType, str]) -> PolicyCitation:
    """Retrieve authoritative policy citation for a discrepancy category."""
    disc_val = discrepancy_type.value if hasattr(discrepancy_type, "value") else str(discrepancy_type)
    for citation in POLICY_REGISTRY.values():
        for ct in citation.governing_claim_types:
            if ct.value == disc_val or ct == discrepancy_type:
                return citation
    # Default fallback to master policy G200213130
    return POLICY_REGISTRY[PolicyCode.POL_FBA_OPS]
