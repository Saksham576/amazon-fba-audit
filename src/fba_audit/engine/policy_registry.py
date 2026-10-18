"""
Authoritative registry of Amazon FBA Reimbursement Policies and claim window rules.
"""

from typing import Dict, Optional
from ..models.policies import PolicyCitation, POLICY_REGISTRY, get_policy_citation
from ..models.enums import PolicyCode, DiscrepancyType


class PolicyCitationRegistry:
    """
    Registry providing official policy citations, clauses, and filing deadlines.
    Based on official Amazon Seller Central Reimbursement Policy (2024-2025).
    """

    POLICY_WAREHOUSE = "G200379860"
    CLAUSE_WAREHOUSE = "FBA inventory reimbursement policy: Fulfillment center operations claims"
    URL_WAREHOUSE = "https://sellercentral.amazon.com/help/hub/reference/G200379860"

    POLICY_RETURNS = "G200213130"
    CLAUSE_RETURNS = "Customer return claims policy G200213130"
    URL_RETURNS = "https://sellercentral.amazon.com/help/hub/reference/G200213130"

    POLICY_DIMENSIONS = "G21213"
    CLAUSE_DIMENSIONS = "FBA weight and dimension overcharge policy"
    URL_DIMENSIONS = "https://sellercentral.amazon.com/help/hub/reference/G21213"

    POLICY_INBOUND = "G200453320"
    CLAUSE_INBOUND = "FBA lost and damaged inventory reimbursement policy: Inbound shipment claims"
    URL_INBOUND = "https://sellercentral.amazon.com/help/hub/reference/G200453320"

    @classmethod
    def get_citation(cls, code: str) -> Optional[PolicyCitation]:
        for p in POLICY_REGISTRY.values():
            if p.help_hub_id == code or p.code.value == code:
                return p
        return None

    @classmethod
    def for_discrepancy(cls, discrepancy_type: DiscrepancyType) -> PolicyCitation:
        return get_policy_citation(discrepancy_type)
