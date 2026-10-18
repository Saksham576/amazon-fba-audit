"""
Amazon FBA Seller Acquisition Pipeline.
Includes:
- leads: Target brand finder and lead generator
- outreach: Policy-grounded multi-touch cold email sequence generator
- portal: Self-serve web intake portal & dispute authorization API
"""

from .leads import (
    CATEGORY_DISCREPANCY_BENCHMARKS,
    CURATED_SEED_LEADS,
    BrandFinder,
    BrandLead,
    DecisionMaker,
    LeadStatus,
    StorefrontMetadata,
    TargetCategory,
)
from .outreach import (
    DEFAULT_CONTINGENCY_PERCENT,
    DEFAULT_SENDER_EMAIL,
    DEFAULT_SENDER_NAME,
    EmailMessage,
    OutreachGenerator,
    OutreachSequence,
)
from .portal import (
    AuthorizationRecord,
    AuthorizationRequest,
    IntakeAuditSummary,
    SellerIntakePortal,
    start_portal_server,
)

__all__ = [
    # Leads
    "TargetCategory",
    "LeadStatus",
    "CATEGORY_DISCREPANCY_BENCHMARKS",
    "DecisionMaker",
    "StorefrontMetadata",
    "BrandLead",
    "BrandFinder",
    "CURATED_SEED_LEADS",
    # Outreach
    "EmailMessage",
    "OutreachSequence",
    "OutreachGenerator",
    "DEFAULT_SENDER_NAME",
    "DEFAULT_SENDER_EMAIL",
    "DEFAULT_CONTINGENCY_PERCENT",
    # Portal
    "IntakeAuditSummary",
    "AuthorizationRequest",
    "AuthorizationRecord",
    "SellerIntakePortal",
    "start_portal_server",
]
