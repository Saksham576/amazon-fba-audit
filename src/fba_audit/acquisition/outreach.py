"""
Automated Personalized Outreach Email Sequence Generator.
Generates high-converting, policy-backed, zero-risk email sequences
offering free Amazon FBA discrepancy audits under 15% performance contingency.
Quotes official Amazon Seller Central Policies G200379860 and G200213130.
"""

from datetime import datetime, timezone
from decimal import Decimal
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

from .leads import BrandLead, TargetCategory


DEFAULT_SENDER_NAME = "Viraj Tiwari"
DEFAULT_SENDER_EMAIL = "virajtiwari52@gmail.com"
DEFAULT_SENDER_ROLE = "Founder, Autonomous FBA Reimbursement Engine"
DEFAULT_CONTINGENCY_PERCENT = 15


class EmailMessage(BaseModel):
    step: int
    step_name: str
    delay_days: int
    subject: str
    text_content: str
    html_content: str
    sender_name: str
    sender_email: str
    recipient_name: str
    recipient_email: str
    policy_citations: List[str]


class OutreachSequence(BaseModel):
    brand_id: str
    brand_name: str
    recipient_email: str
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    emails: List[EmailMessage]

    def get_step(self, step: int) -> Optional[EmailMessage]:
        for em in self.emails:
            if em.step == step:
                return em
        return None


class OutreachGenerator:
    """
    Constructs multi-touch, policy-grounded cold outreach sequences for target FBA brands.
    """

    def __init__(
        self,
        sender_name: str = DEFAULT_SENDER_NAME,
        sender_email: str = DEFAULT_SENDER_EMAIL,
        sender_role: str = DEFAULT_SENDER_ROLE,
        contingency_percent: int = DEFAULT_CONTINGENCY_PERCENT,
        portal_url: str = "https://fba-audit.nexuspulse.io/intake",
    ):
        self.sender_name = sender_name
        self.sender_email = sender_email
        self.sender_role = sender_role
        self.contingency_percent = contingency_percent
        self.portal_url = portal_url

    def generate_sequence(self, lead: BrandLead) -> OutreachSequence:
        """
        Creates a high-converting 3-step outreach sequence tailored to the brand's metrics.
        """
        emails = [
            self._build_step_1(lead),
            self._build_step_2(lead),
            self._build_step_3(lead),
        ]
        return OutreachSequence(
            brand_id=lead.brand_id,
            brand_name=lead.brand_name,
            recipient_email=lead.decision_maker.email,
            emails=emails,
        )

    def _build_step_1(self, lead: BrandLead) -> EmailMessage:
        brand = lead.brand_name
        recipient_name = lead.decision_maker.name.split()[0] if lead.decision_maker.name else "there"
        est_discrepancy = f"${lead.estimated_annual_discrepancy_usd:,.2f}"
        est_volume = f"${lead.estimated_monthly_volume_usd:,.2f}"

        subject = f"Unclaimed FBA inventory discrepancy for {brand} (Policy G200379860)"

        text = f"""Hi {recipient_name},

I was reviewing {brand}'s Amazon storefront and estimated your monthly FBA volume at ~{est_volume} in {lead.category.value}.

Based on cross-referencing fulfillment center defect rates across 40+ seven-figure brands, Amazon fulfillment centers misplace, damage, or fail to reimburse between 1.5% and 3.1% of FBA throughput annually. For {brand}, that represents approximately {est_discrepancy} in uncredited capital.

Under Amazon's official FBA Lost and Damaged Inventory Reimbursement Policy (Policy G200379860) and Customer Returns Policy (Policy G200213130), sellers have a strict 60-day window to submit itemized dispute claims before rights to reimbursement permanently expire.

We run a deterministic, offline audit engine that crosswalks your 4 raw SP-API reports:
1. Inventory Ledger Detail (GET_LEDGER_DETAIL_VIEW_DATA)
2. Customer Returns (GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA)
3. Reimbursements (GET_FBA_REIMBURSEMENT_DATA)
4. Estimated FBA Fees (GET_FBA_ESTIMATED_FBA_FEES_TXT_DATA)

OUR ZERO-RISK OFFER:
- 100% Free Initial Audit: We calculate your exact recoverable dollar amount upfront.
- Performance Contingency Only: Exactly {self.contingency_percent}%, charged only after Amazon deposits cash or inventory credit into your Seller Central account.
- If we recover $0, you pay $0. Zero upfront retainers, zero monthly software fees.

Would you be open to running a confidential, 10-minute audit on your last 60 days of SP-API reports?

You can test our self-serve audit portal directly here: {self.portal_url}
Or reply directly to this email with "AUDIT" and I'll send over the secure upload link.

Best regards,

{self.sender_name}
{self.sender_role}
{self.sender_email}
Direct: +1 (512) 890-4210
"""

        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; line-height: 1.6; color: #1e293b; background-color: #f8fafc; margin: 0; padding: 20px; }}
.container {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; padding: 32px; }}
.badge {{ display: inline-block; background: #2563eb; color: #ffffff; font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 4px; text-transform: uppercase; letter-spacing: 0.05em; }}
.stat-card {{ background: #eff6ff; border-left: 4px solid #2563eb; padding: 16px; margin: 20px 0; border-radius: 0 6px 6px 0; }}
.stat-val {{ font-size: 28px; font-weight: 800; color: #1d4ed8; }}
.stat-desc {{ font-size: 13px; color: #475569; }}
.cta-button {{ display: inline-block; background: #16a34a; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: 700; margin-top: 16px; }}
.footer {{ font-size: 12px; color: #94a3b8; margin-top: 32px; border-top: 1px solid #e2e8f0; padding-top: 16px; }}
</style>
</head>
<body>
<div class="container">
  <span class="badge">Amazon FBA Policy Audit</span>
  <p>Hi {recipient_name},</p>
  <p>I was reviewing <strong>{brand}</strong>'s Amazon storefront and estimated your monthly volume at ~<strong>{est_volume}</strong> in {lead.category.value}.</p>
  
  <div class="stat-card">
    <div class="stat-desc">Estimated Unclaimed Amazon Discrepancies for {brand}:</div>
    <div class="stat-val">{est_discrepancy}</div>
    <div class="stat-desc">Governed by Amazon Policies <strong>G200379860</strong> & <strong>G200213130</strong></div>
  </div>

  <p>Under Amazon's <strong>60-day policy rule</strong>, any lost warehouse inventory or unreturned customer refund not claimed within 60 days is permanently forfeited to Amazon.</p>

  <p><strong>Our Zero-Risk Proposition:</strong></p>
  <ul>
    <li><strong>100% Free Audit:</strong> We identify your exact recoverable amount before you commit.</li>
    <li><strong>{self.contingency_percent}% Contingency Only:</strong> Zero retainers. You pay only after cash is credited to your Seller Central balance.</li>
    <li><strong>Zero Risk:</strong> If we recover $0, you pay $0.</li>
  </ul>

  <p><a href="{self.portal_url}" class="cta-button">Run Free 60-Day Audit &rarr;</a></p>

  <div class="footer">
    <strong>{self.sender_name}</strong> &bull; {self.sender_role}<br>
    {self.sender_email} &bull; Citations: Amazon Help Hub Policy G200379860, G200213130
  </div>
</div>
</body>
</html>"""

        return EmailMessage(
            step=1,
            step_name="Initial Audit Pitch & Policy Notice",
            delay_days=0,
            subject=subject,
            text_content=text,
            html_content=html,
            sender_name=self.sender_name,
            sender_email=self.sender_email,
            recipient_name=lead.decision_maker.name,
            recipient_email=lead.decision_maker.email,
            policy_citations=["G200379860", "G200213130"],
        )

    def _build_step_2(self, lead: BrandLead) -> EmailMessage:
        brand = lead.brand_name
        recipient_name = lead.decision_maker.name.split()[0] if lead.decision_maker.name else "there"

        subject = f"Re: Policy G200213130: 45-day unreturned customer refund audit for {brand}"

        text = f"""Hi {recipient_name},

Following up on my note regarding {brand}. Many private label brands assume Amazon's automated reimbursement system catches everything. In reality, customer return discrepancies are where the largest leaks occur.

HERE IS HOW POLICY G200213130 WORKS:
1. When a buyer initiates a return, Amazon immediately deducts the full refund amount from your seller account.
2. The customer is given 45 days to physically return the merchandise to an Amazon Fulfillment Center.
3. If the unit never arrives after 45 days, Amazon's policy mandates an automatic reimbursement to you.
4. HOWEVER: Amazon's internal batch jobs fail to reimburse up to 28% of unreturned units.
5. You have only 60 days following the 45-day hold period to file an itemized dispute claim. After that, the money belongs to Amazon forever.

Our deterministic engine reconciles your raw GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA against GET_LEDGER_DETAIL_VIEW_DATA to pinpoint every single unreturned unit down to the exact Order ID and LPN tracking number.

Zero risk, zero upfront fees. Our fee is strictly {self.contingency_percent}% upon cash recovery.

Are you available for a brief 5-minute call this Thursday or Friday to review sample dispute documentation?
Or you can inspect your numbers instantly via our intake portal: {self.portal_url}

Best regards,

{self.sender_name}
{self.sender_role}
{self.sender_email}
"""

        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; line-height: 1.6; color: #1e293b; background-color: #f8fafc; margin: 0; padding: 20px; }}
.container {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; padding: 32px; }}
.step-box {{ background: #f1f5f9; padding: 16px; border-radius: 6px; margin: 16px 0; font-size: 14px; }}
.policy-tag {{ background: #0f172a; color: #ffffff; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 11px; }}
.cta-button {{ display: inline-block; background: #2563eb; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: 700; margin-top: 16px; }}
.footer {{ font-size: 12px; color: #94a3b8; margin-top: 32px; border-top: 1px solid #e2e8f0; padding-top: 16px; }}
</style>
</head>
<body>
<div class="container">
  <p>Hi {recipient_name},</p>
  <p>Following up on my note regarding <strong>{brand}</strong>. Many sellers assume Amazon catches all discrepancies automatically. In reality, customer returns represent the single largest uncredited loss.</p>
  
  <div class="step-box">
    <strong>How Amazon Policy <span class="policy-tag">G200213130</span> Works:</strong><br>
    &bull; Customer refunded &rarr; Amazon charges your account immediately.<br>
    &bull; 45-day window for customer to return goods to FC.<br>
    &bull; If unreturned &rarr; Amazon must reimburse. Automated systems miss up to 28% of cases.<br>
    &bull; Sellers have <strong>60 days</strong> after the 45-day hold to claim reimbursement.
  </div>

  <p>Our deterministic engine matches every unreturned item with exact Order IDs, LPN codes, and timestamp logs ready for 1-click submission.</p>

  <p>Remember: <strong>{self.contingency_percent}% performance contingency only</strong>. If Amazon doesn't pay, you owe nothing.</p>

  <p><a href="{self.portal_url}" class="cta-button">Audit Your Returns Free &rarr;</a></p>

  <div class="footer">
    <strong>{self.sender_name}</strong> &bull; {self.sender_role}<br>
    {self.sender_email} &bull; Policy Reference: G200213130
  </div>
</div>
</body>
</html>"""

        return EmailMessage(
            step=2,
            step_name="Policy G200213130 Deep Dive & Return Reconciler",
            delay_days=3,
            subject=subject,
            text_content=text,
            html_content=html,
            sender_name=self.sender_name,
            sender_email=self.sender_email,
            recipient_name=lead.decision_maker.name,
            recipient_email=lead.decision_maker.email,
            policy_citations=["G200213130"],
        )

    def _build_step_3(self, lead: BrandLead) -> EmailMessage:
        brand = lead.brand_name
        recipient_name = lead.decision_maker.name.split()[0] if lead.decision_maker.name else "there"
        est_discrepancy = f"${lead.estimated_annual_discrepancy_usd:,.2f}"

        subject = f"60-day policy expiration deadline for {brand} ({lead.business_entity_name})"

        text = f"""Hi {recipient_name},

Final quick note regarding {brand}. Under Amazon's updated reimbursement policies, any warehouse inventory loss or unreturned customer refund that crosses 60 days without an open case is permanently non-recoverable.

Every single week, an estimated ${(lead.estimated_annual_discrepancy_usd / Decimal('52')):,.2f} in rightful seller capital permanently rolls over the 60-day cliff and is forfeited to Amazon.

SUMMARY OF OUR AUDIT:
- Zero cost to run the initial audit.
- Zero risk: 15% contingency fee, collected strictly AFTER Amazon pays you.
- You retain 85% of recovered capital that would otherwise be permanently lost.
- Itemized CSV ready for Seller Central case submission.

If you would like us to audit your account before this month's 60-day window closes:
1. Upload your 4 raw SP-API reports securely at: {self.portal_url}
2. Or reply "PROCEED" and we'll handle the report extraction guidance for your team.

If the timing isn't right, no problem at all and I wish {brand} continued success.

Best regards,

{self.sender_name}
{self.sender_role}
{self.sender_email}
"""

        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; line-height: 1.6; color: #1e293b; background-color: #f8fafc; margin: 0; padding: 20px; }}
.container {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; padding: 32px; }}
.urgent-card {{ background: #fff1f2; border: 1px solid #fecdd3; border-radius: 6px; padding: 18px; margin: 18px 0; color: #9f1239; }}
.urgent-title {{ font-weight: 800; font-size: 15px; margin-bottom: 6px; }}
.cta-button {{ display: inline-block; background: #e11d48; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: 700; margin-top: 16px; }}
.footer {{ font-size: 12px; color: #94a3b8; margin-top: 32px; border-top: 1px solid #e2e8f0; padding-top: 16px; }}
</style>
</head>
<body>
<div class="container">
  <p>Hi {recipient_name},</p>
  <p>Final quick note regarding <strong>{brand}</strong>.</p>
  
  <div class="urgent-card">
    <div class="urgent-title">60-Day Claim Expiration Warning</div>
    Under Amazon Policies <strong>G200379860</strong> and <strong>G200213130</strong>, claims must be logged within 60 days. Every week of delay permanently forfeits an estimated <strong>${(lead.estimated_annual_discrepancy_usd / Decimal('52')):,.2f}</strong> of {brand}'s earnings.
  </div>

  <p><strong>Our Zero-Risk Contingency Model:</strong></p>
  <ul>
    <li>Free preliminary audit &mdash; know your numbers before deciding.</li>
    <li>{self.contingency_percent}% fee only upon cash/inventory credited to your balance.</li>
    <li>You keep 85% of funds otherwise lost forever.</li>
  </ul>

  <p><a href="{self.portal_url}" class="cta-button">Lock In Your 60-Day Audit &rarr;</a></p>

  <div class="footer">
    <strong>{self.sender_name}</strong> &bull; {self.sender_role}<br>
    {self.sender_email} &bull; Policy Statutes: G200379860, G200213130
  </div>
</div>
</body>
</html>"""

        return EmailMessage(
            step=3,
            step_name="60-Day Statute of Limitations Urgency",
            delay_days=7,
            subject=subject,
            text_content=text,
            html_content=html,
            sender_name=self.sender_name,
            sender_email=self.sender_email,
            recipient_name=lead.decision_maker.name,
            recipient_email=lead.decision_maker.email,
            policy_citations=["G200379860", "G200213130"],
        )

    def export_sequence_to_dir(self, sequence: OutreachSequence, dir_path: Union[str, Path]) -> List[Path]:
        """
        Exports all emails in a sequence as individual .eml and .json files.
        """
        out_dir = Path(dir_path) / sequence.brand_name.lower().replace(" ", "_")
        out_dir.mkdir(parents=True, exist_ok=True)
        paths: List[Path] = []

        for email in sequence.emails:
            file_base = f"step_{email.step}_{email.step_name.lower().replace(' ', '_')}"
            eml_file = out_dir / f"{file_base}.eml"

            msg = MIMEMultipart("alternative")
            msg["Subject"] = email.subject
            msg["From"] = f"{email.sender_name} <{email.sender_email}>"
            msg["To"] = f"{email.recipient_name} <{email.recipient_email}>"
            msg.attach(MIMEText(email.text_content, "plain", "utf-8"))
            msg.attach(MIMEText(email.html_content, "html", "utf-8"))

            with open(eml_file, "w", encoding="utf-8") as f:
                f.write(msg.as_string())
            paths.append(eml_file)

            json_file = out_dir / f"{file_base}.json"
            with open(json_file, "w", encoding="utf-8") as f:
                f.write(email.model_dump_json(indent=2))
            paths.append(json_file)

        return paths
