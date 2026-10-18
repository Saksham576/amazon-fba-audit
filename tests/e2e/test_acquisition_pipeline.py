"""
End-to-End (E2E) integration test for the Amazon FBA Seller Acquisition Pipeline.
Tests the entire lifecycle:
1. Lead Generation: Discover high-discrepancy private label target brands
2. Outreach Engine: Generate policy-backed 3-stage cold outreach sequence
3. Self-Serve Intake Portal: Ingest 4 raw SP-API reports and compute exact recoverable cash
4. Dispute Authorization: Sign 15% performance contingency agreement
5. Owner Alert & Deliverables: Dispatch payout notice to virajtiwari52@gmail.com and export dispute package
"""

from decimal import Decimal
import json
from pathlib import Path
import pytest

from fba_audit.acquisition.leads import (
    BrandFinder,
    BrandLead,
    TargetCategory,
)
from fba_audit.acquisition.outreach import (
    OutreachGenerator,
)
from fba_audit.acquisition.portal import (
    AuthorizationRequest,
    SellerIntakePortal,
)
from fba_audit.mailer import OWNER_EMAIL


@pytest.fixture
def fixtures_dir() -> Path:
    return Path("tests/fixtures")


def test_e2e_seller_acquisition_lifecycle(tmp_path: Path, fixtures_dir: Path):
    pipeline_dir = tmp_path / "pipeline"
    outreach_dir = pipeline_dir / "outreach"
    portal_dir = pipeline_dir / "portal"

    # =========================================================================
    # STAGE 1: Lead Discovery & Qualification
    # =========================================================================
    finder = BrandFinder()
    target_leads = finder.find_leads(
        categories=[TargetCategory.HOME_AND_KITCHEN],
        min_monthly_volume=Decimal("150000.00"),
    )
    assert len(target_leads) > 0
    target_lead: BrandLead = target_leads[0]

    assert target_lead.brand_name == "AuraKitchen Labs"
    assert target_lead.category == TargetCategory.HOME_AND_KITCHEN
    assert target_lead.estimated_annual_discrepancy_usd > Decimal("40000.00")
    assert target_lead.estimated_contingency_fee_usd > Decimal("6000.00")

    # =========================================================================
    # STAGE 2: Automated Personalized Outreach Sequence Generation
    # =========================================================================
    outreach_gen = OutreachGenerator(
        sender_name="Viraj Tiwari",
        sender_email="virajtiwari52@gmail.com",
        contingency_percent=15,
        portal_url="https://portal.nexuspulsetech.com/intake",
    )
    seq = outreach_gen.generate_sequence(target_lead)
    assert len(seq.emails) == 3

    # Verify Step 1 copy cites Policy G200379860 and zero-risk contingency
    s1 = seq.get_step(1)
    assert "AuraKitchen Labs" in s1.subject
    assert "Policy G200379860" in s1.subject
    assert "15%" in s1.text_content
    assert "G200379860" in s1.policy_citations
    assert "G200213130" in s1.policy_citations
    assert "virajtiwari52@gmail.com" in s1.text_content

    # Export outreach files
    exported = outreach_gen.export_sequence_to_dir(seq, outreach_dir)
    assert len(exported) == 6

    # =========================================================================
    # STAGE 3: Self-Serve Intake Portal Audit
    # =========================================================================
    portal = SellerIntakePortal(portal_dir=portal_dir)

    ledger_path = fixtures_dir / "ledger_detail_sample.tsv"
    returns_path = fixtures_dir / "customer_returns_sample.tsv"
    reimb_path = fixtures_dir / "reimbursements_sample.tsv"
    fees_path = fixtures_dir / "estimated_fees_sample.tsv"

    summary = portal.audit_from_files(
        ledger_path=ledger_path,
        returns_path=returns_path,
        reimbursements_path=reimb_path,
        fees_path=fees_path,
        seller_id=target_lead.brand_name,
    )

    assert summary.submission_id.startswith("SUB-")
    assert summary.total_recoverable_usd > 0
    assert summary.contingency_fee_usd > 0
    assert summary.seller_net_recovery_usd > 0
    assert summary.contingency_fee_usd == (summary.total_recoverable_usd * Decimal("0.15")).quantize(Decimal("0.01"))
    assert summary.seller_net_recovery_usd == (summary.total_recoverable_usd - summary.contingency_fee_usd).quantize(Decimal("0.01"))

    # =========================================================================
    # STAGE 4: Seller Dispute Authorization & Contingency Agreement Sign-Off
    # =========================================================================
    auth_request = AuthorizationRequest(
        submission_id=summary.submission_id,
        seller_id=target_lead.storefront.seller_central_merchant_id or "A2V4KJ8711N90L",
        brand_name=target_lead.brand_name,
        contact_email=target_lead.decision_maker.email,
        contact_name=target_lead.decision_maker.name,
        signature_name=target_lead.decision_maker.name,
        contingency_agreement_accepted=True,
    )

    auth_record = portal.authorize_dispute_processing(auth_request)

    assert auth_record.status == "AUTHORIZED"
    assert auth_record.brand_name == "AuraKitchen Labs"
    assert auth_record.contact_email == "marcus@aurakitchenlabs.com"
    assert auth_record.contingency_fee_usd == summary.contingency_fee_usd

    # =========================================================================
    # STAGE 5: Owner Alert & Dispute Deliverables Verification
    # =========================================================================
    # Verify deliverables generated in submission directory
    deliverables_path = Path(auth_record.deliverables_dir)
    assert (deliverables_path / "claims_batch.csv").exists()
    assert (deliverables_path / "claims_batch.json").exists()
    assert (deliverables_path / "audit_dossier.html").exists()

    # Verify payout notification alert saved in portal/notifications
    notifications_dir = portal_dir / "notifications"
    assert notifications_dir.exists()
    eml_files = list(notifications_dir.glob("*.eml"))
    json_files = list(notifications_dir.glob("*.json"))

    assert len(eml_files) >= 1
    assert len(json_files) >= 1

    latest_json = sorted(json_files)[-1]
    with open(latest_json, "r", encoding="utf-8") as f:
        meta = json.load(f)

    assert meta["recipient"] == OWNER_EMAIL
    assert meta["payout_cut"] == float(summary.contingency_fee_usd)
    assert meta["eligible_amount"] == float(summary.total_recoverable_usd)
    assert "AuraKitchen Labs" in meta["seller_id"]

    # Verify authorization is retrieved from persistent storage
    retrieved = portal.get_authorization(auth_record.authorization_id)
    assert retrieved is not None
    assert retrieved.authorization_id == auth_record.authorization_id
