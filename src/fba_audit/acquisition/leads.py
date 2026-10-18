"""
Amazon FBA Brand Finder and Lead Generator.
Models target private label brands in high-discrepancy categories:
Home & Kitchen, Electronics, Apparel, Toys, Pet Supplies.
"""

import csv
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
import json
from pathlib import Path
import random
from typing import Any, Dict, List, Optional, Set, Union
from pydantic import BaseModel, Field, field_validator


class TargetCategory(str, Enum):
    HOME_AND_KITCHEN = "Home & Kitchen"
    ELECTRONICS = "Electronics"
    APPAREL = "Apparel"
    TOYS = "Toys"
    PET_SUPPLIES = "Pet Supplies"


class LeadStatus(str, Enum):
    NEW = "NEW"
    CONTACTED = "CONTACTED"
    AUDIT_IN_PROGRESS = "AUDIT_IN_PROGRESS"
    AUTHORIZED = "AUTHORIZED"
    ONBOARDED = "ONBOARDED"
    DECLINED = "DECLINED"


# Industry benchmark discrepancy rates by category (lost, damaged, unreturned customer refunds)
CATEGORY_DISCREPANCY_BENCHMARKS: Dict[TargetCategory, Decimal] = {
    TargetCategory.HOME_AND_KITCHEN: Decimal("0.022"),  # 2.2% (bulky goods, warehouse drop damages)
    TargetCategory.ELECTRONICS: Decimal("0.025"),       # 2.5% (high-value lost items, serial misplacement)
    TargetCategory.APPAREL: Decimal("0.031"),           # 3.1% (highest return rate, unreturned FC holds)
    TargetCategory.TOYS: Decimal("0.019"),              # 1.9% (seasonal surges, Q4 receiving discrepancies)
    TargetCategory.PET_SUPPLIES: Decimal("0.021"),      # 2.1% (heavy/liquid item leaks, dimensional surcharges)
}


class DecisionMaker(BaseModel):
    name: str
    title: str = "Founder & CEO"
    email: str
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None


class StorefrontMetadata(BaseModel):
    storefront_url: str
    seller_central_merchant_id: Optional[str] = None
    marketplace_id: str = "ATVPDKIKX0DER"  # Amazon US
    rating: float = 4.8
    review_count: int = 1500
    active_asin_count: int = 35
    primary_fc_region: str = "US_WEST"


class BrandLead(BaseModel):
    brand_id: str
    brand_name: str
    category: TargetCategory
    business_entity_name: str
    storefront: StorefrontMetadata
    decision_maker: DecisionMaker
    estimated_monthly_volume_usd: Decimal
    estimated_monthly_units: int
    typical_discrepancy_rate: Decimal = Decimal("0.02")
    status: LeadStatus = LeadStatus.NEW
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    notes: Optional[str] = None

    @field_validator("estimated_monthly_volume_usd", mode="before")
    @classmethod
    def coerce_monthly_volume(cls, v: Any) -> Decimal:
        if isinstance(v, (int, float, str)):
            return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return v

    @property
    def estimated_annual_volume_usd(self) -> Decimal:
        return (self.estimated_monthly_volume_usd * 12).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def estimated_annual_discrepancy_usd(self) -> Decimal:
        rate = self.typical_discrepancy_rate if self.typical_discrepancy_rate is not None else CATEGORY_DISCREPANCY_BENCHMARKS.get(self.category, Decimal("0.02"))
        return (self.estimated_annual_volume_usd * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def estimated_contingency_fee_usd(self) -> Decimal:
        # 15% standard performance contingency
        return (self.estimated_annual_discrepancy_usd * Decimal("0.15")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# High-converting vetted seed leads across the 5 high-discrepancy categories
CURATED_SEED_LEADS: List[Dict[str, Any]] = [
    # Home & Kitchen
    {
        "brand_id": "LEAD-HK-001",
        "brand_name": "AuraKitchen Labs",
        "category": TargetCategory.HOME_AND_KITCHEN,
        "business_entity_name": "Aura Living Innovations LLC",
        "storefront": {
            "storefront_url": "https://www.amazon.com/stores/AuraKitchenLabs",
            "seller_central_merchant_id": "A2V4KJ8711N90L",
            "marketplace_id": "ATVPDKIKX0DER",
            "rating": 4.7,
            "review_count": 4820,
            "active_asin_count": 48,
            "primary_fc_region": "US_EAST",
        },
        "decision_maker": {
            "name": "Marcus Vance",
            "title": "Co-Founder & VP of Supply Chain",
            "email": "marcus@aurakitchenlabs.com",
            "phone": "+1-512-555-0143",
            "linkedin_url": "https://www.linkedin.com/in/marcus-vance-fba",
        },
        "estimated_monthly_volume_usd": Decimal("185000.00"),
        "estimated_monthly_units": 6500,
        "typical_discrepancy_rate": Decimal("0.022"),
        "status": LeadStatus.NEW,
        "notes": "Ceramic cookware & insulated food containers. High probability of FC drop damage under Policy G200379860.",
    },
    {
        "brand_id": "LEAD-HK-002",
        "brand_name": "PureLoom Living",
        "category": TargetCategory.HOME_AND_KITCHEN,
        "business_entity_name": "PureLoom Home Textiles Inc",
        "storefront": {
            "storefront_url": "https://www.amazon.com/stores/PureLoomLiving",
            "seller_central_merchant_id": "A319KLP0841X2Y",
            "marketplace_id": "ATVPDKIKX0DER",
            "rating": 4.8,
            "review_count": 3210,
            "active_asin_count": 32,
            "primary_fc_region": "US_CENTRAL",
        },
        "decision_maker": {
            "name": "Sarah Lin",
            "title": "Founder & Head of Operations",
            "email": "sarah.lin@pureloomliving.com",
            "phone": "+1-415-555-0189",
            "linkedin_url": "https://www.linkedin.com/in/sarahlin-ecommerce",
        },
        "estimated_monthly_volume_usd": Decimal("120000.00"),
        "estimated_monthly_units": 3800,
        "typical_discrepancy_rate": Decimal("0.021"),
        "status": LeadStatus.NEW,
        "notes": "Organic bamboo sheet sets and duvet covers. Prone to packaging dimensional fee misclassifications.",
    },
    # Electronics
    {
        "brand_id": "LEAD-EL-001",
        "brand_name": "SoundPulse Audio",
        "category": TargetCategory.ELECTRONICS,
        "business_entity_name": "SoundPulse Technologies LLC",
        "storefront": {
            "storefront_url": "https://www.amazon.com/stores/SoundPulseAudio",
            "seller_central_merchant_id": "A1M8B9438902XX",
            "marketplace_id": "ATVPDKIKX0DER",
            "rating": 4.6,
            "review_count": 8900,
            "active_asin_count": 24,
            "primary_fc_region": "US_WEST",
        },
        "decision_maker": {
            "name": "David Sterling",
            "title": "Managing Director",
            "email": "david.sterling@soundpulse.tech",
            "phone": "+1-206-555-0122",
            "linkedin_url": "https://www.linkedin.com/in/david-sterling-audio",
        },
        "estimated_monthly_volume_usd": Decimal("340000.00"),
        "estimated_monthly_units": 7200,
        "typical_discrepancy_rate": Decimal("0.025"),
        "status": LeadStatus.NEW,
        "notes": "ANC Bluetooth headphones & DAC amplifiers. High value ($80-$140 ASP). Frequent uncredited warehouse misplaced units.",
    },
    {
        "brand_id": "LEAD-EL-002",
        "brand_name": "VoltCharge Pro",
        "category": TargetCategory.ELECTRONICS,
        "business_entity_name": "VoltCharge Power Systems Corp",
        "storefront": {
            "storefront_url": "https://www.amazon.com/stores/VoltChargePro",
            "seller_central_merchant_id": "A4N8012938AA41",
            "marketplace_id": "ATVPDKIKX0DER",
            "rating": 4.7,
            "review_count": 5400,
            "active_asin_count": 18,
            "primary_fc_region": "US_CENTRAL",
        },
        "decision_maker": {
            "name": "Elena Rostova",
            "title": "Chief Operating Officer",
            "email": "elena@voltchargepro.io",
            "phone": "+1-312-555-0177",
            "linkedin_url": "https://www.linkedin.com/in/elena-rostova-fba",
        },
        "estimated_monthly_volume_usd": Decimal("210000.00"),
        "estimated_monthly_units": 8400,
        "typical_discrepancy_rate": Decimal("0.024"),
        "status": LeadStatus.NEW,
        "notes": "GaN fast chargers and MagSafe power banks. Inbound carrier damage claims under Policy G200379860.",
    },
    # Apparel
    {
        "brand_id": "LEAD-AP-001",
        "brand_name": "NordicActive Wear",
        "category": TargetCategory.APPAREL,
        "business_entity_name": "NordicActive Performance Gear LLC",
        "storefront": {
            "storefront_url": "https://www.amazon.com/stores/NordicActiveWear",
            "seller_central_merchant_id": "A9K381029471BB",
            "marketplace_id": "ATVPDKIKX0DER",
            "rating": 4.5,
            "review_count": 6700,
            "active_asin_count": 86,
            "primary_fc_region": "US_EAST",
        },
        "decision_maker": {
            "name": "Henrik Lindqvist",
            "title": "Founder & CEO",
            "email": "henrik@nordicactivewear.com",
            "phone": "+1-646-555-0195",
            "linkedin_url": "https://www.linkedin.com/in/henrik-lindqvist-active",
        },
        "estimated_monthly_volume_usd": Decimal("260000.00"),
        "estimated_monthly_units": 9100,
        "typical_discrepancy_rate": Decimal("0.031"),
        "status": LeadStatus.NEW,
        "notes": "Thermal base layers & athletic compression wear. Massive customer return volume with unreturned units past 45 days (Policy G200213130).",
    },
    {
        "brand_id": "LEAD-AP-002",
        "brand_name": "ZenAthletica",
        "category": TargetCategory.APPAREL,
        "business_entity_name": "ZenAthletica Apparel Inc",
        "storefront": {
            "storefront_url": "https://www.amazon.com/stores/ZenAthletica",
            "seller_central_merchant_id": "A7V839104829CC",
            "marketplace_id": "ATVPDKIKX0DER",
            "rating": 4.7,
            "review_count": 4120,
            "active_asin_count": 54,
            "primary_fc_region": "US_WEST",
        },
        "decision_maker": {
            "name": "Jessica Taylor",
            "title": "VP of E-Commerce",
            "email": "jtaylor@zenathletica.com",
            "phone": "+1-310-555-0164",
            "linkedin_url": "https://www.linkedin.com/in/jessica-taylor-zen",
        },
        "estimated_monthly_volume_usd": Decimal("195000.00"),
        "estimated_monthly_units": 5800,
        "typical_discrepancy_rate": Decimal("0.029"),
        "status": LeadStatus.NEW,
        "notes": "Seamless yoga pants and sports bras. High return rate and uncredited inventory adjustments.",
    },
    # Toys
    {
        "brand_id": "LEAD-TY-001",
        "brand_name": "TinySparks Playworks",
        "category": TargetCategory.TOYS,
        "business_entity_name": "TinySparks Educational Toys LLC",
        "storefront": {
            "storefront_url": "https://www.amazon.com/stores/TinySparksPlayworks",
            "seller_central_merchant_id": "A3P982147102DD",
            "marketplace_id": "ATVPDKIKX0DER",
            "rating": 4.8,
            "review_count": 7800,
            "active_asin_count": 42,
            "primary_fc_region": "US_CENTRAL",
        },
        "decision_maker": {
            "name": "Arthur Pendelton",
            "title": "Co-Founder & President",
            "email": "arthur@tinysparksplay.com",
            "phone": "+1-617-555-0131",
            "linkedin_url": "https://www.linkedin.com/in/arthur-pendelton-toys",
        },
        "estimated_monthly_volume_usd": Decimal("160000.00"),
        "estimated_monthly_units": 6200,
        "typical_discrepancy_rate": Decimal("0.020"),
        "status": LeadStatus.NEW,
        "notes": "STEM robotics kits and wooden educational puzzles. Q4 holiday inbound receiving discrepancies.",
    },
    # Pet Supplies
    {
        "brand_id": "LEAD-PET-001",
        "brand_name": "BarkHaven Goods",
        "category": TargetCategory.PET_SUPPLIES,
        "business_entity_name": "BarkHaven Pet Nutrition & Gear LLC",
        "storefront": {
            "storefront_url": "https://www.amazon.com/stores/BarkHavenGoods",
            "seller_central_merchant_id": "A8X294810375EE",
            "marketplace_id": "ATVPDKIKX0DER",
            "rating": 4.9,
            "review_count": 11200,
            "active_asin_count": 28,
            "primary_fc_region": "US_WEST",
        },
        "decision_maker": {
            "name": "Rachel Thorne",
            "title": "Head of Operations & Logistics",
            "email": "rachel@barkhavengoods.com",
            "phone": "+1-503-555-0118",
            "linkedin_url": "https://www.linkedin.com/in/rachel-thorne-pets",
        },
        "estimated_monthly_volume_usd": Decimal("290000.00"),
        "estimated_monthly_units": 10500,
        "typical_discrepancy_rate": Decimal("0.021"),
        "status": LeadStatus.NEW,
        "notes": "Orthopedic memory foam dog beds and freeze-dried treats. Heavy package dimensional weight overcharge disputes under Policy G21213.",
    },
    {
        "brand_id": "LEAD-PET-002",
        "brand_name": "Pawsome Vitality",
        "category": TargetCategory.PET_SUPPLIES,
        "business_entity_name": "Pawsome Vitality Supplements Inc",
        "storefront": {
            "storefront_url": "https://www.amazon.com/stores/PawsomeVitality",
            "seller_central_merchant_id": "A5Z381920471FF",
            "marketplace_id": "ATVPDKIKX0DER",
            "rating": 4.7,
            "review_count": 4900,
            "active_asin_count": 16,
            "primary_fc_region": "US_CENTRAL",
        },
        "decision_maker": {
            "name": "Dr. Bradley Cooper",
            "title": "Founder & Chief Scientific Officer",
            "email": "bradley@pawsomevitality.com",
            "phone": "+1-303-555-0152",
            "linkedin_url": "https://www.linkedin.com/in/dr-bradley-cooper-vet",
        },
        "estimated_monthly_volume_usd": Decimal("145000.00"),
        "estimated_monthly_units": 4900,
        "typical_discrepancy_rate": Decimal("0.023"),
        "status": LeadStatus.NEW,
        "notes": "Probiotic chews and omega-3 oils. Liquid damage in FC transit.",
    },
]


class BrandFinder:
    """
    Search engine and synthesizer for Amazon FBA brand targets.
    Filters private label sellers by GMV, category, and recoverable fee upside.
    """

    def __init__(self, leads: Optional[List[BrandLead]] = None):
        self._leads: Dict[str, BrandLead] = {}
        if leads is not None:
            for lead in leads:
                self._leads[lead.brand_id] = lead
        else:
            self._load_curated_seed()

    def _load_curated_seed(self) -> None:
        for seed_data in CURATED_SEED_LEADS:
            lead = BrandLead(**seed_data)
            self._leads[lead.brand_id] = lead

    def add_lead(self, lead: BrandLead) -> None:
        self._leads[lead.brand_id] = lead

    def get_lead(self, brand_id: str) -> Optional[BrandLead]:
        return self._leads.get(brand_id)

    def list_all(self) -> List[BrandLead]:
        return list(self._leads.values())

    def find_leads(
        self,
        categories: Optional[List[Union[TargetCategory, str]]] = None,
        min_monthly_volume: Optional[Decimal] = None,
        max_monthly_volume: Optional[Decimal] = None,
        status: Optional[LeadStatus] = None,
        query: Optional[str] = None,
    ) -> List[BrandLead]:
        """
        Filters brand leads based on criteria with deterministic matching.
        """
        results: List[BrandLead] = []
        cat_set: Optional[Set[str]] = None
        if categories:
            cat_set = {c.value if isinstance(c, TargetCategory) else str(c) for c in categories}

        for lead in self._leads.values():
            if cat_set and lead.category.value not in cat_set:
                continue
            if min_monthly_volume is not None and lead.estimated_monthly_volume_usd < min_monthly_volume:
                continue
            if max_monthly_volume is not None and lead.estimated_monthly_volume_usd > max_monthly_volume:
                continue
            if status is not None and lead.status != status:
                continue
            if query:
                q = query.lower()
                matches = (
                    q in lead.brand_name.lower()
                    or q in lead.business_entity_name.lower()
                    or q in lead.decision_maker.name.lower()
                    or q in lead.decision_maker.email.lower()
                    or (lead.notes and q in lead.notes.lower())
                )
                if not matches:
                    continue
            results.append(lead)

        return results

    def generate_synthetic_leads(
        self,
        count: int = 5,
        category: Optional[Union[TargetCategory, str]] = None,
        seed: Optional[int] = None,
    ) -> List[BrandLead]:
        """
        Generates realistic synthetic brand leads for prospecting simulations.
        """
        if seed is not None:
            random.seed(seed)

        target_cats = (
            [TargetCategory(category) if isinstance(category, str) else category]
            if category
            else list(TargetCategory)
        )

        first_names = ["Alexander", "Beatrice", "Carlos", "Daphne", "Ethan", "Fiona", "Gabriel", "Hannah", "Ian", "Julia"]
        last_names = ["Morgan", "Chen", "Novak", "Patel", "Kowalski", "Dupont", "O'Connor", "Kim", "Santos", "Wright"]
        brand_prefixes = ["Apex", "Vital", "Summit", "Lumina", "Terra", "Nova", "Starlight", "Core", "Aura", "Prime"]
        brand_suffixes = ["Craft", "Works", "Lab", "Gear", "Living", "Tech", "Dynamics", "Supply", "Elements", "Pro"]

        cat_descriptors = {
            TargetCategory.HOME_AND_KITCHEN: "Kitchen",
            TargetCategory.ELECTRONICS: "Tech",
            TargetCategory.APPAREL: "Apparel",
            TargetCategory.TOYS: "Toys",
            TargetCategory.PET_SUPPLIES: "Pets",
        }

        synthetic_leads: List[BrandLead] = []
        for i in range(count):
            cat = random.choice(target_cats)
            cat_desc = cat_descriptors.get(cat, cat.name.capitalize())
            brand_name = f"{random.choice(brand_prefixes)}{random.choice(brand_suffixes)} {cat_desc}"
            fn = random.choice(first_names)
            ln = random.choice(last_names)
            domain = brand_name.lower().replace(" ", "").replace("&", "").replace("-", "") + ".com"
            monthly_vol = Decimal(random.randint(60, 450) * 1000)
            avg_price = Decimal(random.randint(18, 95))
            units = int(monthly_vol / avg_price)
            benchmark_rate = CATEGORY_DISCREPANCY_BENCHMARKS.get(cat, Decimal("0.02"))

            lead_id = f"SYNTH-{cat.name[:2]}-{1000 + len(self._leads) + i}"
            lead = BrandLead(
                brand_id=lead_id,
                brand_name=brand_name,
                category=cat,
                business_entity_name=f"{brand_name} Holdings LLC",
                storefront=StorefrontMetadata(
                    storefront_url=f"https://www.amazon.com/stores/{brand_name.replace(' ', '')}",
                    seller_central_merchant_id=f"A{random.randint(100000000000, 999999999999)}",
                    rating=round(random.uniform(4.3, 4.9), 1),
                    review_count=random.randint(800, 15000),
                    active_asin_count=random.randint(15, 90),
                ),
                decision_maker=DecisionMaker(
                    name=f"{fn} {ln}",
                    title="Founder & Managing Member",
                    email=f"{fn.lower()}.{ln.lower()}@{domain}",
                    phone=f"+1-{random.randint(200, 999)}-555-0{random.randint(100, 999)}",
                    linkedin_url=f"https://www.linkedin.com/in/{fn.lower()}-{ln.lower()}-fba",
                ),
                estimated_monthly_volume_usd=monthly_vol,
                estimated_monthly_units=units,
                typical_discrepancy_rate=benchmark_rate,
                status=LeadStatus.NEW,
                notes=f"Synthetic prospect generated in {cat.value} category.",
            )
            synthetic_leads.append(lead)
            self._leads[lead.brand_id] = lead

        return synthetic_leads

    def export_csv(self, leads: List[BrandLead], output_path: Union[str, Path]) -> Path:
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "brand_id",
                "brand_name",
                "category",
                "business_entity_name",
                "decision_maker_name",
                "decision_maker_title",
                "contact_email",
                "phone",
                "storefront_url",
                "estimated_monthly_volume_usd",
                "estimated_annual_discrepancy_usd",
                "estimated_contingency_fee_usd",
                "status",
                "notes",
            ])
            for l in leads:
                writer.writerow([
                    l.brand_id,
                    l.brand_name,
                    l.category.value,
                    l.business_entity_name,
                    l.decision_maker.name,
                    l.decision_maker.title,
                    l.decision_maker.email,
                    l.decision_maker.phone or "",
                    l.storefront.storefront_url,
                    f"{l.estimated_monthly_volume_usd:.2f}",
                    f"{l.estimated_annual_discrepancy_usd:.2f}",
                    f"{l.estimated_contingency_fee_usd:.2f}",
                    l.status.value,
                    l.notes or "",
                ])
        return p

    def export_json(self, leads: List[BrandLead], output_path: Union[str, Path]) -> Path:
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = [json.loads(l.model_dump_json()) for l in leads]
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return p

    @classmethod
    def import_json(cls, input_path: Union[str, Path]) -> "BrandFinder":
        p = Path(input_path)
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        leads = [BrandLead(**item) for item in data]
        return cls(leads=leads)

    @classmethod
    def import_csv(cls, input_path: Union[str, Path]) -> "BrandFinder":
        p = Path(input_path)
        leads: List[BrandLead] = []
        with open(p, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cat_val = row["category"]
                cat = None
                for c in TargetCategory:
                    if c.value.lower() == cat_val.lower() or c.name.lower() == cat_val.lower():
                        cat = c
                        break
                if not cat:
                    cat = TargetCategory.HOME_AND_KITCHEN

                lead = BrandLead(
                    brand_id=row["brand_id"],
                    brand_name=row["brand_name"],
                    category=cat,
                    business_entity_name=row["business_entity_name"],
                    storefront=StorefrontMetadata(
                        storefront_url=row.get("storefront_url") or f"https://www.amazon.com/stores/{row['brand_name'].replace(' ', '')}",
                    ),
                    decision_maker=DecisionMaker(
                        name=row["decision_maker_name"],
                        title=row.get("decision_maker_title") or "Founder",
                        email=row["contact_email"],
                        phone=row.get("phone") or None,
                    ),
                    estimated_monthly_volume_usd=Decimal(row["estimated_monthly_volume_usd"]),
                    estimated_monthly_units=max(1, int(Decimal(row.get("estimated_monthly_volume_usd", "100000")) / Decimal("30"))),
                    status=LeadStatus(row.get("status", "NEW")),
                    notes=row.get("notes") or None,
                )
                leads.append(lead)
        return cls(leads=leads)
