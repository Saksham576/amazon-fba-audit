"""
Unit tests for Amazon FBA Brand Finder and Lead Generator (fba_audit.acquisition.leads).
"""

from decimal import Decimal
import json
from pathlib import Path
import pytest

from fba_audit.acquisition.leads import (
    BrandFinder,
    BrandLead,
    CATEGORY_DISCREPANCY_BENCHMARKS,
    CURATED_SEED_LEADS,
    DecisionMaker,
    LeadStatus,
    StorefrontMetadata,
    TargetCategory,
)


def test_target_categories_enum():
    cats = {c.value for c in TargetCategory}
    assert "Home & Kitchen" in cats
    assert "Electronics" in cats
    assert "Apparel" in cats
    assert "Toys" in cats
    assert "Pet Supplies" in cats


def test_curated_seed_leads_present():
    finder = BrandFinder()
    leads = finder.list_all()
    assert len(leads) >= 8

    categories_found = {l.category for l in leads}
    assert TargetCategory.HOME_AND_KITCHEN in categories_found
    assert TargetCategory.ELECTRONICS in categories_found
    assert TargetCategory.APPAREL in categories_found
    assert TargetCategory.TOYS in categories_found
    assert TargetCategory.PET_SUPPLIES in categories_found


def test_brand_lead_financial_calculations():
    lead = BrandLead(
        brand_id="LEAD-TEST-01",
        brand_name="Test Kitchenware",
        category=TargetCategory.HOME_AND_KITCHEN,
        business_entity_name="Test Kitchen LLC",
        storefront=StorefrontMetadata(
            storefront_url="https://amazon.com/stores/test",
            rating=4.8,
            review_count=1200,
            active_asin_count=20,
        ),
        decision_maker=DecisionMaker(
            name="Alice Smith",
            title="CEO",
            email="alice@testkitchen.com",
            phone="+1-555-0101",
        ),
        estimated_monthly_volume_usd=Decimal("100000.00"),
        estimated_monthly_units=4000,
        typical_discrepancy_rate=Decimal("0.02"),
    )

    # Annual volume: 100,000 * 12 = 1,200,000
    assert lead.estimated_annual_volume_usd == Decimal("1200000.00")
    # Discrepancy: 1,200,000 * 0.02 = 24,000
    assert lead.estimated_annual_discrepancy_usd == Decimal("24000.00")
    # 15% contingency fee: 24,000 * 0.15 = 3,600
    assert lead.estimated_contingency_fee_usd == Decimal("3600.00")


def test_brand_finder_filtering():
    finder = BrandFinder()

    # Filter by category
    electronics = finder.find_leads(categories=[TargetCategory.ELECTRONICS])
    assert len(electronics) >= 2
    for l in electronics:
        assert l.category == TargetCategory.ELECTRONICS

    # Filter by string category
    apparel = finder.find_leads(categories=["Apparel"])
    assert len(apparel) >= 2
    for l in apparel:
        assert l.category == TargetCategory.APPAREL

    # Filter by volume range
    high_volume = finder.find_leads(min_monthly_volume=Decimal("200000.00"))
    assert len(high_volume) > 0
    for l in high_volume:
        assert l.estimated_monthly_volume_usd >= Decimal("200000.00")

    # Filter by max volume
    low_volume = finder.find_leads(max_monthly_volume=Decimal("150000.00"))
    assert len(low_volume) > 0
    for l in low_volume:
        assert l.estimated_monthly_volume_usd <= Decimal("150000.00")

    # Filter by search query
    searched = finder.find_leads(query="Marcus Vance")
    assert len(searched) == 1
    assert searched[0].brand_name == "AuraKitchen Labs"

    # Search in notes
    searched_notes = finder.find_leads(query="G200379860")
    assert len(searched_notes) > 0


def test_synthetic_lead_generation():
    finder = BrandFinder()
    initial_count = len(finder.list_all())

    synths = finder.generate_synthetic_leads(count=5, category=TargetCategory.TOYS, seed=42)
    assert len(synths) == 5
    assert len(finder.list_all()) == initial_count + 5

    for lead in synths:
        assert lead.category == TargetCategory.TOYS
        assert lead.brand_id.startswith("SYNTH-TO-")
        assert lead.estimated_monthly_volume_usd > 0
        assert lead.decision_maker.email.endswith(".com")


def test_leads_csv_and_json_export_import(tmp_path: Path):
    finder = BrandFinder()
    leads = finder.find_leads(categories=[TargetCategory.PET_SUPPLIES])

    csv_path = tmp_path / "pets_leads.csv"
    finder.export_csv(leads, csv_path)
    assert csv_path.exists()
    content = csv_path.read_text(encoding="utf-8")
    assert "BarkHaven Goods" in content
    assert "Pet Supplies" in content

    json_path = tmp_path / "pets_leads.json"
    finder.export_json(leads, json_path)
    assert json_path.exists()

    reimported_finder = BrandFinder.import_json(json_path)
    reimported = reimported_finder.list_all()
    assert len(reimported) == len(leads)
    assert reimported[0].brand_id == leads[0].brand_id
    assert reimported[0].decision_maker.email == leads[0].decision_maker.email

    # Test CSV import
    csv_reimported_finder = BrandFinder.import_csv(csv_path)
    csv_reimported = csv_reimported_finder.list_all()
    assert len(csv_reimported) == len(leads)
    assert csv_reimported[0].brand_id == leads[0].brand_id
    assert csv_reimported[0].brand_name == leads[0].brand_name
    assert csv_reimported[0].category == TargetCategory.PET_SUPPLIES
    assert csv_reimported[0].decision_maker.email == leads[0].decision_maker.email


def test_lead_zero_discrepancy_rate():
    lead = BrandLead(
        brand_id="LEAD-ZERO",
        brand_name="Pristine Goods",
        category=TargetCategory.HOME_AND_KITCHEN,
        business_entity_name="Pristine Goods LLC",
        storefront=StorefrontMetadata(storefront_url="https://amazon.com/stores/pristine"),
        decision_maker=DecisionMaker(name="Pat Clean", email="pat@pristine.com"),
        estimated_monthly_volume_usd=Decimal("50000.00"),
        estimated_monthly_units=1000,
        typical_discrepancy_rate=Decimal("0.00"),
    )
    assert lead.estimated_annual_discrepancy_usd == Decimal("0.00")
    assert lead.estimated_contingency_fee_usd == Decimal("0.00")


def test_brand_finder_add_and_get():
    finder = BrandFinder(leads=[])
    assert len(finder.list_all()) == 0

    lead = BrandLead(
        brand_id="LEAD-CUSTOM",
        brand_name="Custom Brand",
        category=TargetCategory.ELECTRONICS,
        business_entity_name="Custom Brand LLC",
        storefront=StorefrontMetadata(storefront_url="https://amazon.com/stores/custom"),
        decision_maker=DecisionMaker(name="Jane Doe", email="jane@custom.com"),
        estimated_monthly_volume_usd=Decimal("80000.00"),
        estimated_monthly_units=2000,
    )
    finder.add_lead(lead)
    assert len(finder.list_all()) == 1
    assert finder.get_lead("LEAD-CUSTOM") is not None
    assert finder.get_lead("LEAD-CUSTOM").brand_name == "Custom Brand"
    assert finder.get_lead("NONEXISTENT") is None
