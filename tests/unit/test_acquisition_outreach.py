"""
Unit tests for automated personalized outreach email sequence generator (fba_audit.acquisition.outreach).
"""

from decimal import Decimal
from pathlib import Path
import pytest

from fba_audit.acquisition.leads import (
    BrandLead,
    DecisionMaker,
    StorefrontMetadata,
    TargetCategory,
)
from fba_audit.acquisition.outreach import (
    DEFAULT_CONTINGENCY_PERCENT,
    DEFAULT_SENDER_EMAIL,
    DEFAULT_SENDER_NAME,
    EmailMessage,
    OutreachGenerator,
    OutreachSequence,
)


@pytest.fixture
def sample_lead() -> BrandLead:
    return BrandLead(
        brand_id="LEAD-TEST-99",
        brand_name="Apex Kitchenware",
        category=TargetCategory.HOME_AND_KITCHEN,
        business_entity_name="Apex Culinary Brands LLC",
        storefront=StorefrontMetadata(
            storefront_url="https://amazon.com/stores/apexkitchen",
            seller_central_merchant_id="A2X9918204",
        ),
        decision_maker=DecisionMaker(
            name="Robert Vance",
            title="Co-Founder & COO",
            email="robert@apexkitchenware.com",
            phone="+1-555-888-0199",
        ),
        estimated_monthly_volume_usd=Decimal("250000.00"),
        estimated_monthly_units=8000,
        typical_discrepancy_rate=Decimal("0.022"),
    )


def test_outreach_generator_sequence_structure(sample_lead):
    gen = OutreachGenerator()
    seq = gen.generate_sequence(sample_lead)

    assert seq.brand_id == sample_lead.brand_id
    assert seq.brand_name == sample_lead.brand_name
    assert seq.recipient_email == sample_lead.decision_maker.email
    assert len(seq.emails) == 3

    step1 = seq.get_step(1)
    step2 = seq.get_step(2)
    step3 = seq.get_step(3)

    assert step1 is not None
    assert step2 is not None
    assert step3 is not None
    assert seq.get_step(99) is None


def test_outreach_step_1_policy_and_contingency(sample_lead):
    gen = OutreachGenerator(
        sender_name="Viraj Tiwari",
        sender_email="virajtiwari52@gmail.com",
        contingency_percent=15,
    )
    seq = gen.generate_sequence(sample_lead)
    step1 = seq.get_step(1)

    assert "Apex Kitchenware" in step1.subject
    assert "Policy G200379860" in step1.subject
    assert "G200379860" in step1.policy_citations
    assert "G200213130" in step1.policy_citations

    # Check body copy requirements
    assert "15%" in step1.text_content
    assert "Free Initial Audit" in step1.text_content or "100% Free" in step1.text_content
    assert "virajtiwari52@gmail.com" in step1.text_content
    assert "G200379860" in step1.text_content
    assert "G200213130" in step1.text_content

    # Check HTML output
    assert "<html>" in step1.html_content
    assert "15%" in step1.html_content
    assert "Apex Kitchenware" in step1.html_content


def test_outreach_step_2_customer_returns(sample_lead):
    gen = OutreachGenerator()
    seq = gen.generate_sequence(sample_lead)
    step2 = seq.get_step(2)

    assert "Policy G200213130" in step2.subject
    assert "45 days" in step2.text_content or "45-day" in step2.text_content
    assert "60 days" in step2.text_content
    assert "15%" in step2.text_content
    assert step2.delay_days == 3


def test_outreach_step_3_urgency_deadline(sample_lead):
    gen = OutreachGenerator()
    seq = gen.generate_sequence(sample_lead)
    step3 = seq.get_step(3)

    assert "60-day" in step3.subject.lower()
    assert "Apex Culinary Brands LLC" in step3.subject or "Apex Kitchenware" in step3.subject
    assert "forfeit" in step3.text_content.lower()
    assert "85%" in step3.text_content
    assert "15%" in step3.text_content
    assert step3.delay_days == 7


def test_outreach_export_to_directory(tmp_path: Path, sample_lead):
    gen = OutreachGenerator()
    seq = gen.generate_sequence(sample_lead)

    exported_files = gen.export_sequence_to_dir(seq, tmp_path)
    assert len(exported_files) == 6  # 3 .eml + 3 .json

    for f in exported_files:
        assert f.exists()
        assert f.stat().st_size > 0

    emls = [f for f in exported_files if f.suffix == ".eml"]
    assert len(emls) == 3
    sample_eml_text = emls[0].read_text(encoding="utf-8")
    assert "virajtiwari52@gmail.com" in sample_eml_text
    assert "robert@apexkitchenware.com" in sample_eml_text


def test_outreach_safe_first_name_handling():
    gen = OutreachGenerator()

    # Lead with empty / whitespace name
    lead_blank = BrandLead(
        brand_id="LEAD-BLANK",
        brand_name="Blank Name Co",
        category=TargetCategory.TOYS,
        business_entity_name="Blank LLC",
        storefront=StorefrontMetadata(storefront_url="https://amazon.com/stores/blank"),
        decision_maker=DecisionMaker(name="   ", email="info@blank.com"),
        estimated_monthly_volume_usd=Decimal("50000.00"),
        estimated_monthly_units=1000,
    )
    seq = gen.generate_sequence(lead_blank)
    assert "Hi there," in seq.emails[0].text_content

    # Lead with single name
    lead_single = BrandLead(
        brand_id="LEAD-SINGLE",
        brand_name="Cher Brand",
        category=TargetCategory.APPAREL,
        business_entity_name="Cher LLC",
        storefront=StorefrontMetadata(storefront_url="https://amazon.com/stores/cher"),
        decision_maker=DecisionMaker(name="Cher", email="cher@cherbrand.com"),
        estimated_monthly_volume_usd=Decimal("50000.00"),
        estimated_monthly_units=1000,
    )
    seq_single = gen.generate_sequence(lead_single)
    assert "Hi Cher," in seq_single.emails[0].text_content


def test_outreach_export_special_chars_brand(tmp_path: Path):
    gen = OutreachGenerator()
    lead_special = BrandLead(
        brand_id="LEAD-SPEC",
        brand_name='Acme / Global: "Toys" & More',
        category=TargetCategory.TOYS,
        business_entity_name="Acme Special LLC",
        storefront=StorefrontMetadata(storefront_url="https://amazon.com/stores/acme"),
        decision_maker=DecisionMaker(name="Alex Smith", email="alex@acme.com"),
        estimated_monthly_volume_usd=Decimal("60000.00"),
        estimated_monthly_units=1500,
    )
    seq = gen.generate_sequence(lead_special)
    exported = gen.export_sequence_to_dir(seq, tmp_path)
    assert len(exported) == 6
    for f in exported:
        assert f.exists()
        assert ":" not in f.parent.name
        assert "/" not in f.parent.name
        assert '"' not in f.parent.name
