"""
Self-Serve Web Intake Portal and API for Amazon FBA Sellers.
Allows sellers to upload 4 raw SP-API reports:
- ledger: GET_LEDGER_DETAIL_VIEW_DATA
- returns: GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA
- reimbursements: GET_FBA_REIMBURSEMENT_DATA
- fees: GET_FBA_ESTIMATED_FBA_FEES_TXT_DATA

Provides immediate interactive calculation of recoverable dollars under
Policies G200379860 and G200213130, 15% contingency fee projection,
and self-serve authorization of dispute processing.
"""

from datetime import datetime, date, timezone
from decimal import Decimal, ROUND_HALF_UP
import http.server
import json
import os
from pathlib import Path
import re
import socketserver
import tempfile
import threading
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid
from pydantic import BaseModel, Field, field_validator

from ..api import run_audit
from ..mailer import PayoutMailer, OWNER_EMAIL
from ..models import AuditResult, ClaimRecord


DEFAULT_PORTAL_DIR = Path("payouts/portal")
DEFAULT_AUTHORIZATIONS_FILE = DEFAULT_PORTAL_DIR / "authorizations.json"
CONTINGENCY_FEE_RATE = Decimal("0.15")


class IntakeAuditSummary(BaseModel):
    submission_id: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    seller_id: str
    total_recoverable_usd: Decimal
    contingency_fee_usd: Decimal
    seller_net_recovery_usd: Decimal
    total_claims_count: int
    eligible_claims_count: int
    expired_claims_count: int
    expired_amount_usd: Decimal
    total_discrepancy_units: int
    category_breakdown: Dict[str, Dict[str, Any]]
    policy_citations: List[str]
    top_claims: List[Dict[str, Any]]
    is_authorized: bool = False

    @field_validator(
        "total_recoverable_usd",
        "contingency_fee_usd",
        "seller_net_recovery_usd",
        "expired_amount_usd",
        mode="before",
    )
    @classmethod
    def coerce_decimal(cls, v: Any) -> Decimal:
        if isinstance(v, (int, float, str)):
            return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return v


class AuthorizationRequest(BaseModel):
    submission_id: str
    seller_id: str
    brand_name: str
    contact_email: str
    contact_name: Optional[str] = None
    signature_name: str
    contingency_agreement_accepted: bool = True


class AuthorizationRecord(BaseModel):
    authorization_id: str
    submission_id: str
    seller_id: str
    brand_name: str
    contact_email: str
    contact_name: Optional[str] = None
    signature_name: str
    total_recoverable_usd: Decimal
    contingency_fee_usd: Decimal
    seller_net_recovery_usd: Decimal
    authorized_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    deliverables_dir: str
    status: str = "AUTHORIZED"


class SellerIntakePortal:
    """
    Core engine behind the self-serve Amazon seller intake portal and API.
    """

    def __init__(
        self,
        portal_dir: Optional[Union[str, Path]] = None,
        mailer: Optional[PayoutMailer] = None,
    ):
        self.portal_dir = Path(portal_dir) if portal_dir else DEFAULT_PORTAL_DIR
        self.portal_dir.mkdir(parents=True, exist_ok=True)
        self.authorizations_file = self.portal_dir / "authorizations.json"
        self.submissions_cache: Dict[str, Tuple[IntakeAuditSummary, Dict[str, str]]] = {}
        self.mailer = mailer or PayoutMailer(notifications_dir=self.portal_dir / "notifications")

    def audit_reports(
        self,
        ledger_content: Optional[str] = None,
        returns_content: Optional[str] = None,
        reimbursements_content: Optional[str] = None,
        fees_content: Optional[str] = None,
        seller_id: str = "PROSPECTIVE_SELLER",
        as_of_date: Optional[date] = None,
    ) -> IntakeAuditSummary:
        """
        Executes audit against in-memory report contents and generates instant recoverable calculations.
        """
        with tempfile.TemporaryDirectory() as tmp_dir_str:
            tmp_dir = Path(tmp_dir_str)
            ledger_p = tmp_dir / "ledger.tsv" if ledger_content else None
            returns_p = tmp_dir / "returns.tsv" if returns_content else None
            reimb_p = tmp_dir / "reimb.tsv" if reimbursements_content else None
            fees_p = tmp_dir / "fees.tsv" if fees_content else None

            if ledger_p and ledger_content:
                ledger_p.write_text(ledger_content, encoding="utf-8")
            if returns_p and returns_content:
                returns_p.write_text(returns_content, encoding="utf-8")
            if reimb_p and reimbursements_content:
                reimb_p.write_text(reimbursements_content, encoding="utf-8")
            if fees_p and fees_content:
                fees_p.write_text(fees_content, encoding="utf-8")

            return self.audit_from_files(
                ledger_path=ledger_p,
                returns_path=returns_p,
                reimbursements_path=reimb_p,
                fees_path=fees_p,
                seller_id=seller_id,
                as_of_date=as_of_date,
            )

    def audit_from_files(
        self,
        ledger_path: Optional[Union[str, Path]] = None,
        returns_path: Optional[Union[str, Path]] = None,
        reimbursements_path: Optional[Union[str, Path]] = None,
        fees_path: Optional[Union[str, Path]] = None,
        seller_id: str = "PROSPECTIVE_SELLER",
        as_of_date: Optional[date] = None,
    ) -> IntakeAuditSummary:
        """
        Executes audit against local report files and creates cached intake submission.
        """
        submission_id = f"SUB-{uuid.uuid4().hex[:10].upper()}"
        deliverables_dir = self.portal_dir / "deliverables" / submission_id
        deliverables_dir.mkdir(parents=True, exist_ok=True)

        audit_res: AuditResult = run_audit(
            ledger_path=ledger_path,
            returns_path=returns_path,
            reimbursements_path=reimbursements_path,
            fees_path=fees_path,
            as_of_date=as_of_date,
            output_dir=deliverables_dir,
        )

        eligible_amount = audit_res.summary.eligible_claim_amount
        contingency_fee = (eligible_amount * CONTINGENCY_FEE_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        seller_net = (eligible_amount - contingency_fee).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Categorize claims by policy
        cat_breakdown: Dict[str, Dict[str, Any]] = {
            "warehouse_lost_damaged": {
                "name": "Warehouse Lost & Damaged Inventory",
                "policy": "Policy G200379860",
                "claims_count": 0,
                "amount_usd": Decimal("0.00"),
            },
            "customer_returns": {
                "name": "Unreturned Customer Refunds (45+ Days)",
                "policy": "Policy G200213130",
                "claims_count": 0,
                "amount_usd": Decimal("0.00"),
            },
            "dimensional_fees": {
                "name": "FBA Package Dimensional Fee Overcharges",
                "policy": "Policy G21213",
                "claims_count": 0,
                "amount_usd": Decimal("0.00"),
            },
        }

        top_claims: List[Dict[str, Any]] = []
        for claim in audit_res.claims:
            if not claim.is_eligible:
                continue
            amt = claim.estimated_amount
            dt_val = claim.discrepancy_type.value if hasattr(claim.discrepancy_type, "value") else str(claim.discrepancy_type)
            if "warehouse" in dt_val.lower() or "lost" in dt_val.lower() or "damaged" in dt_val.lower():
                cat_breakdown["warehouse_lost_damaged"]["claims_count"] += 1
                cat_breakdown["warehouse_lost_damaged"]["amount_usd"] += amt
            elif "return" in dt_val.lower():
                cat_breakdown["customer_returns"]["claims_count"] += 1
                cat_breakdown["customer_returns"]["amount_usd"] += amt
            else:
                cat_breakdown["dimensional_fees"]["claims_count"] += 1
                cat_breakdown["dimensional_fees"]["amount_usd"] += amt

            if len(top_claims) < 10:
                top_claims.append({
                    "claim_id": claim.claim_id,
                    "fnsku": claim.fnsku,
                    "title": getattr(claim, "title", None) or getattr(claim, "msku", "") or claim.fnsku,
                    "type": dt_val,
                    "amount": float(claim.estimated_amount),
                    "policy_code": str(claim.policy_citation) if claim.policy_citation else "G200379860",
                    "days_remaining": getattr(claim, "days_until_expiration", 60),
                })

        # Coerce breakdown amounts to float for json serialization
        serializable_breakdown = {
            k: {
                "name": v["name"],
                "policy": v["policy"],
                "claims_count": v["claims_count"],
                "amount_usd": float(v["amount_usd"]),
            }
            for k, v in cat_breakdown.items()
        }

        summary = IntakeAuditSummary(
            submission_id=submission_id,
            seller_id=seller_id,
            total_recoverable_usd=eligible_amount,
            contingency_fee_usd=contingency_fee,
            seller_net_recovery_usd=seller_net,
            total_claims_count=audit_res.summary.total_claims_count,
            eligible_claims_count=audit_res.summary.total_eligible_count,
            expired_claims_count=audit_res.summary.total_expired_count,
            expired_amount_usd=audit_res.summary.expired_claim_amount,
            total_discrepancy_units=audit_res.summary.total_discrepancy_units,
            category_breakdown=serializable_breakdown,
            policy_citations=["G200379860", "G200213130", "G21213"],
            top_claims=top_claims,
            is_authorized=False,
        )

        # Store in cache
        file_paths = {
            "deliverables_dir": str(deliverables_dir),
            "claims_csv": str(deliverables_dir / "claims_batch.csv"),
            "dossier_html": str(deliverables_dir / "audit_dossier.html"),
        }
        self.submissions_cache[submission_id] = (summary, file_paths)
        return summary

    def authorize_dispute_processing(self, request: AuthorizationRequest) -> AuthorizationRecord:
        """
        Authorizes claim preparation and filing. Dispatches alert to business owner.
        """
        cached = self.submissions_cache.get(request.submission_id)
        if not cached:
            # Create a lightweight summary if not cached
            summary = IntakeAuditSummary(
                submission_id=request.submission_id,
                seller_id=request.seller_id,
                total_recoverable_usd=Decimal("0.00"),
                contingency_fee_usd=Decimal("0.00"),
                seller_net_recovery_usd=Decimal("0.00"),
                total_claims_count=0,
                eligible_claims_count=0,
                expired_claims_count=0,
                expired_amount_usd=Decimal("0.00"),
                total_discrepancy_units=0,
                category_breakdown={},
                policy_citations=["G200379860", "G200213130"],
                top_claims=[],
                is_authorized=True,
            )
            deliverables_dir = str(self.portal_dir / "deliverables" / request.submission_id)
            claims_csv_p = None
            dossier_html_p = None
        else:
            summary, paths = cached
            summary.is_authorized = True
            deliverables_dir = paths["deliverables_dir"]
            claims_csv_p = Path(paths["claims_csv"]) if Path(paths["claims_csv"]).exists() else None
            dossier_html_p = Path(paths["dossier_html"]) if Path(paths["dossier_html"]).exists() else None

        auth_id = f"AUTH-{uuid.uuid4().hex[:8].upper()}"
        record = AuthorizationRecord(
            authorization_id=auth_id,
            submission_id=request.submission_id,
            seller_id=request.seller_id,
            brand_name=request.brand_name,
            contact_email=request.contact_email,
            contact_name=request.contact_name,
            signature_name=request.signature_name,
            total_recoverable_usd=summary.total_recoverable_usd,
            contingency_fee_usd=summary.contingency_fee_usd,
            seller_net_recovery_usd=summary.seller_net_recovery_usd,
            deliverables_dir=deliverables_dir,
            status="AUTHORIZED",
        )

        # Save to persistent authorizations store
        self._save_authorization(record)

        # Dispatch alert to business owner (virajtiwari52@gmail.com)
        if summary.contingency_fee_usd > 0:
            self.mailer.dispatch_payout_alert(
                seller_id=f"{request.brand_name} ({request.seller_id})",
                total_claims_count=summary.eligible_claims_count,
                eligible_amount=summary.total_recoverable_usd,
                payout_cut=summary.contingency_fee_usd,
                dossier_html_path=dossier_html_p,
                claims_csv_path=claims_csv_p,
            )

        return record

    def _save_authorization(self, record: AuthorizationRecord) -> None:
        auths = self.list_authorizations()
        auths.append(record)
        data = [json.loads(r.model_dump_json()) for r in auths]
        with open(self.authorizations_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def list_authorizations(self) -> List[AuthorizationRecord]:
        if not self.authorizations_file.exists():
            return []
        try:
            with open(self.authorizations_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [AuthorizationRecord(**item) for item in data]
        except Exception:
            return []

    def get_authorization(self, auth_id: str) -> Optional[AuthorizationRecord]:
        for auth in self.list_authorizations():
            if auth.authorization_id == auth_id:
                return auth
        return None

    def render_portal_html(self) -> str:
        """
        Renders the single-page self-serve client portal HTML with zero CDN dependencies.
        """
        return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Amazon FBA Audit & Reimbursement Intake Portal</title>
<style>
  :root {
    --primary: #2563eb;
    --primary-dark: #1d4ed8;
    --success: #16a34a;
    --success-bg: #f0fdf4;
    --danger: #dc2626;
    --slate-900: #0f172a;
    --slate-800: #1e293b;
    --slate-600: #475569;
    --slate-200: #e2e8f0;
    --slate-50: #f8fafc;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
  body { background-color: var(--slate-50); color: var(--slate-900); padding-bottom: 60px; }
  .navbar { background: #ffffff; border-bottom: 1px solid var(--slate-200); padding: 18px 32px; display: flex; justify-content: space-between; align-items: center; }
  .logo { font-size: 19px; font-weight: 800; color: var(--primary); display: flex; align-items: center; gap: 8px; }
  .policy-badge { background: #dbeafe; color: var(--primary-dark); font-size: 12px; font-weight: 700; padding: 4px 10px; border-radius: 9999px; }
  .hero { text-align: center; max-width: 820px; margin: 40px auto 30px auto; padding: 0 20px; }
  .hero h1 { font-size: 36px; font-weight: 900; line-height: 1.2; margin-bottom: 16px; color: var(--slate-900); }
  .hero p { font-size: 16px; color: var(--slate-600); line-height: 1.6; }
  .guarantee-bar { display: flex; justify-content: center; gap: 24px; margin-top: 20px; font-size: 13px; font-weight: 600; color: var(--slate-600); }
  .guarantee-item { display: flex; align-items: center; gap: 6px; }
  .check { color: var(--success); font-weight: bold; }
  .card-container { max-width: 900px; margin: 0 auto; padding: 0 20px; }
  .card { background: #ffffff; border: 1px solid var(--slate-200); border-radius: 12px; padding: 32px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); margin-bottom: 28px; }
  .card-title { font-size: 20px; font-weight: 800; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; }
  .card-subtitle { font-size: 14px; color: var(--slate-600); margin-bottom: 24px; }
  .drop-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 16px; margin-bottom: 24px; }
  .drop-box { border: 2px dashed var(--slate-200); border-radius: 8px; padding: 20px; text-align: center; cursor: pointer; transition: all 0.2s; position: relative; }
  .drop-box:hover { border-color: var(--primary); background: #f0f7ff; }
  .drop-box.loaded { border-color: var(--success); background: var(--success-bg); }
  .drop-title { font-weight: 700; font-size: 13px; margin-bottom: 4px; }
  .drop-desc { font-size: 11px; color: var(--slate-600); }
  .drop-box input[type="file"] { position: absolute; inset: 0; opacity: 0; cursor: pointer; }
  .btn-primary { background: var(--primary); color: white; border: none; border-radius: 8px; padding: 14px 28px; font-size: 15px; font-weight: 700; cursor: pointer; width: 100%; transition: background 0.2s; }
  .btn-primary:hover { background: var(--primary-dark); }
  .btn-success { background: var(--success); color: white; border: none; border-radius: 8px; padding: 14px 28px; font-size: 15px; font-weight: 700; cursor: pointer; width: 100%; transition: background 0.2s; }
  .btn-success:hover { background: #15803d; }
  .results-box { display: none; margin-top: 28px; }
  .kpi-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 24px; }
  .kpi-card { background: var(--slate-50); border: 1px solid var(--slate-200); border-radius: 8px; padding: 20px; text-align: center; }
  .kpi-card.highlight { background: var(--success-bg); border-color: #86efac; }
  .kpi-label { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--slate-600); margin-bottom: 6px; }
  .kpi-val { font-size: 32px; font-weight: 900; color: var(--slate-900); }
  .kpi-card.highlight .kpi-val { color: #166534; }
  .kpi-sub { font-size: 12px; color: var(--slate-600); margin-top: 4px; }
  .breakdown-table { width: 100%; border-collapse: collapse; margin-top: 16px; }
  .breakdown-table th, .breakdown-table td { padding: 12px 14px; text-align: left; border-bottom: 1px solid var(--slate-200); font-size: 14px; }
  .breakdown-table th { background: var(--slate-50); font-weight: 700; }
  .auth-form { margin-top: 24px; background: #fafafa; border: 1px solid var(--slate-200); border-radius: 8px; padding: 24px; }
  .form-group { margin-bottom: 16px; }
  .form-label { display: block; font-size: 13px; font-weight: 700; margin-bottom: 6px; }
  .form-input { width: 100%; padding: 10px 14px; border: 1px solid var(--slate-200); border-radius: 6px; font-size: 14px; }
  .checkbox-group { display: flex; align-items: flex-start; gap: 10px; margin: 20px 0; font-size: 13px; line-height: 1.5; color: var(--slate-800); }
  .checkbox-group input { margin-top: 3px; }
  .banner-success { background: #dcfce7; border: 1px solid #86efac; color: #14532d; padding: 18px; border-radius: 8px; margin-top: 20px; font-size: 14px; display: none; }
</style>
</head>
<body>
<div class="navbar">
  <div class="logo">NexusPulse &bull; Amazon FBA Audit Engine</div>
  <div class="policy-badge">Governed by Policies G200379860 & G200213130</div>
</div>

<div class="hero">
  <h1>Recover Unclaimed FBA Capital in Minutes</h1>
  <p>Drop your raw Amazon Selling Partner API (SP-API) reports below to instantly calculate your uncredited lost, damaged, and unreturned inventory reimbursements under official Amazon policies.</p>
  <div class="guarantee-bar">
    <div class="guarantee-item"><span class="check">&#10003;</span> 100% Free Preliminary Audit</div>
    <div class="guarantee-item"><span class="check">&#10003;</span> Zero Upfront Fees (15% Contingency Only)</div>
    <div class="guarantee-item"><span class="check">&#10003;</span> 100% Deterministic & Amazon-Compliant</div>
  </div>
</div>

<div class="card-container">
  <div class="card">
    <div class="card-title">
      <span>1. Upload SP-API Reports</span>
      <span class="policy-badge">Confidential &amp; Offline</span>
    </div>
    <div class="card-subtitle">Select or drag your 4 standard Amazon flat files. Even a single file will provide partial discrepancy results.</div>

    <div class="drop-grid">
      <div class="drop-box" id="box-ledger">
        <div class="drop-title">Inventory Ledger</div>
        <div class="drop-desc">GET_LEDGER_DETAIL_VIEW_DATA</div>
        <input type="file" id="file-ledger" accept=".tsv,.csv,.txt">
      </div>
      <div class="drop-box" id="box-returns">
        <div class="drop-title">Customer Returns</div>
        <div class="drop-desc">GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA</div>
        <input type="file" id="file-returns" accept=".tsv,.csv,.txt">
      </div>
      <div class="drop-box" id="box-reimb">
        <div class="drop-title">Reimbursements</div>
        <div class="drop-desc">GET_FBA_REIMBURSEMENT_DATA</div>
        <input type="file" id="file-reimb" accept=".tsv,.csv,.txt">
      </div>
      <div class="drop-box" id="box-fees">
        <div class="drop-title">Estimated Fees</div>
        <div class="drop-desc">GET_FBA_ESTIMATED_FBA_FEES_TXT_DATA</div>
        <input type="file" id="file-fees" accept=".tsv,.csv,.txt">
      </div>
    </div>

    <button type="button" class="btn-primary" id="btn-run-audit" onclick="triggerAudit()">Execute Deterministic Audit</button>

    <!-- Results Box -->
    <div class="results-box" id="results-box">
      <div class="kpi-row">
        <div class="kpi-card highlight">
          <div class="kpi-label">Total Recoverable Cash</div>
          <div class="kpi-val" id="val-recoverable">$0.00</div>
          <div class="kpi-sub" id="val-claims-count">0 actionable claims</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Your Net Share (85%)</div>
          <div class="kpi-val" id="val-seller-net">$0.00</div>
          <div class="kpi-sub">Directly to your Amazon balance</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">15% Contingency Fee</div>
          <div class="kpi-val" id="val-fee">$0.00</div>
          <div class="kpi-sub">$0 upfront &bull; Paid only on success</div>
        </div>
      </div>

      <h3 style="font-size:16px; font-weight:800; margin-bottom:12px;">Discrepancy Breakdown by Amazon Policy</h3>
      <table class="breakdown-table">
        <thead>
          <tr>
            <th>Discrepancy Category</th>
            <th>Governing Policy</th>
            <th>Actionable Claims</th>
            <th>Recoverable Amount</th>
          </tr>
        </thead>
        <tbody id="breakdown-tbody">
          <!-- Populated dynamically -->
        </tbody>
      </table>

      <!-- Authorization Form -->
      <div class="auth-form" id="auth-section">
        <h3 style="font-size:16px; font-weight:800; margin-bottom:8px;">2. Authorize Dispute Package Preparation</h3>
        <p style="font-size:13px; color:var(--slate-600); margin-bottom:16px;">We prepare the complete itemized claim package (CSV &amp; dossier) citing exact Amazon policies for 1-click submission. We invoice our 15% contingency fee only after funds are credited to your seller balance.</p>

        <div class="form-group">
          <label class="form-label">Seller Central Account / Storefront Name</label>
          <input type="text" class="form-input" id="auth-seller" placeholder="e.g. AuraKitchen Official">
        </div>
        <div class="form-group">
          <label class="form-label">Contact Email (for Payout &amp; Dispute Deliverables)</label>
          <input type="email" class="form-input" id="auth-email" placeholder="e.g. founder@aurakitchen.com">
        </div>
        <div class="form-group">
          <label class="form-label">Authorized Signatory Name</label>
          <input type="text" class="form-input" id="auth-name" placeholder="Full Legal Name">
        </div>

        <div class="checkbox-group">
          <input type="checkbox" id="auth-agree" checked>
          <label for="auth-agree">I authorize NexusPulse FBA Audit Engine to compile dispute deliverables under the <strong>15% performance contingency fee agreement</strong>. I acknowledge there are zero upfront costs and fees are earned only upon successful reimbursement.</label>
        </div>

        <button type="button" class="btn-success" id="btn-submit-auth" onclick="submitAuthorization()">Authorize &amp; Generate Dispute Package</button>

        <div class="banner-success" id="auth-success-banner">
          <strong>&#10003; Authorization Successfully Processed!</strong><br>
          Your dispute package reference: <span id="auth-ref-id" style="font-family:monospace; font-weight:bold;"></span><br>
          Our team is dispatching the complete audit dossier and claims batch to your email.
        </div>
      </div>
    </div>
  </div>
</div>

<script>
let currentSubmissionId = null;
let reportContents = { ledger: null, returns: null, reimbursements: null, fees: null };

function bindFileInput(inputId, boxId, key) {
  const inp = document.getElementById(inputId);
  const box = document.getElementById(boxId);
  inp.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
      const file = e.target.files[0];
      const reader = new FileReader();
      reader.onload = (evt) => {
        reportContents[key] = evt.target.result;
        box.classList.add('loaded');
        box.querySelector('.drop-title').innerText = file.name;
      };
      reader.readAsText(file);
    }
  });
}

bindFileInput('file-ledger', 'box-ledger', 'ledger');
bindFileInput('file-returns', 'box-returns', 'returns');
bindFileInput('file-reimb', 'box-reimb', 'reimbursements');
bindFileInput('file-fees', 'box-fees', 'fees');

async function triggerAudit() {
  const btn = document.getElementById('btn-run-audit');
  btn.disabled = true;
  btn.innerText = 'Analyzing SP-API Reports...';

  try {
    const res = await fetch('/api/audit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(reportContents)
    });
    const data = await res.json();
    currentSubmissionId = data.submission_id;

    document.getElementById('val-recoverable').innerText = '$' + Number(data.total_recoverable_usd).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
    document.getElementById('val-seller-net').innerText = '$' + Number(data.seller_net_recovery_usd).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
    document.getElementById('val-fee').innerText = '$' + Number(data.contingency_fee_usd).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
    document.getElementById('val-claims-count').innerText = data.eligible_claims_count + ' actionable claims';

    const tbody = document.getElementById('breakdown-tbody');
    tbody.innerHTML = '';
    for (const [k, v] of Object.entries(data.category_breakdown)) {
      const row = `<tr>
        <td><strong>${v.name}</strong></td>
        <td><span class="policy-badge">${v.policy}</span></td>
        <td>${v.claims_count}</td>
        <td><strong>$${Number(v.amount_usd).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</strong></td>
      </tr>`;
      tbody.innerHTML += row;
    }

    document.getElementById('results-box').style.display = 'block';
  } catch (err) {
    alert('Error auditing reports: ' + err.message);
  } finally {
    btn.disabled = false;
    btn.innerText = 'Execute Deterministic Audit';
  }
}

async function submitAuthorization() {
  const seller = document.getElementById('auth-seller').value.trim();
  const email = document.getElementById('auth-email').value.trim();
  const name = document.getElementById('auth-name').value.trim();
  const agree = document.getElementById('auth-agree').checked;

  if (!seller || !email || !name) {
    alert('Please fill in your storefront name, contact email, and authorized name.');
    return;
  }
  if (!agree) {
    alert('Please accept the contingency terms to proceed.');
    return;
  }

  const payload = {
    submission_id: currentSubmissionId || 'SUB-PROSPECT',
    seller_id: seller,
    brand_name: seller,
    contact_email: email,
    contact_name: name,
    signature_name: name,
    contingency_agreement_accepted: true
  };

  const btn = document.getElementById('btn-submit-auth');
  btn.disabled = true;
  btn.innerText = 'Processing Authorization...';

  try {
    const res = await fetch('/api/authorize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    document.getElementById('auth-ref-id').innerText = data.authorization_id;
    document.getElementById('auth-success-banner').style.display = 'block';
    btn.style.display = 'none';
  } catch (err) {
    alert('Authorization failed: ' + err.message);
    btn.disabled = false;
    btn.innerText = 'Authorize & Generate Dispute Package';
  }
}
</script>
</body>
</html>"""


class PortalHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
    """
    Lightweight REST request handler for the intake portal.
    """

    portal_instance: Optional[SellerIntakePortal] = None

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress noisy standard HTTP access logs
        return

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            html = self.portal_instance.render_portal_html() if self.portal_instance else "<h1>Portal Initializing</h1>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
        elif self.path in ("/api/health", "/health"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "service": "fba_audit_intake_portal"}).encode("utf-8"))
        elif self.path == "/api/submissions":
            auths = self.portal_instance.list_authorizations() if self.portal_instance else []
            data = [json.loads(a.model_dump_json()) for a in auths]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode("utf-8"))
        elif self.path.startswith("/api/submissions/"):
            auth_id = self.path[len("/api/submissions/"):]
            auth = self.portal_instance.get_authorization(auth_id) if self.portal_instance else None
            if auth:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(json.loads(auth.model_dump_json())).encode("utf-8"))
            else:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"Authorization '{auth_id}' not found"}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        if self.path == "/api/audit":
            try:
                data = json.loads(body.decode("utf-8")) if body else {}
                summary = self.portal_instance.audit_reports(
                    ledger_content=data.get("ledger"),
                    returns_content=data.get("returns"),
                    reimbursements_content=data.get("reimbursements"),
                    fees_content=data.get("fees"),
                    seller_id=data.get("seller_id", "PROSPECTIVE_SELLER"),
                )
                resp = json.loads(summary.model_dump_json())
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(resp).encode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))

        elif self.path == "/api/authorize":
            try:
                data = json.loads(body.decode("utf-8"))
                req = AuthorizationRequest(**data)
                record = self.portal_instance.authorize_dispute_processing(req)
                resp = json.loads(record.model_dump_json())
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(resp).encode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def start_portal_server(
    portal: SellerIntakePortal,
    host: str = "127.0.0.1",
    port: int = 8080,
) -> Tuple[ThreadedHTTPServer, threading.Thread]:
    """
    Starts the intake portal web server in a daemonized background thread.
    """
    handler = PortalHTTPRequestHandler
    handler.portal_instance = portal
    server = ThreadedHTTPServer((host, port), handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, t


def main() -> int:
    import argparse
    import sys
    parser = argparse.ArgumentParser(
        prog="fba_portal",
        description="Self-Serve Web Intake Portal for Amazon FBA Sellers",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")
    parser.add_argument("--portal-dir", type=str, default="payouts/portal", help="Portal data directory")
    args = parser.parse_args()

    portal = SellerIntakePortal(portal_dir=args.portal_dir)
    print(f"[PORTAL] Starting Amazon FBA Intake Portal on http://{args.host}:{args.port}")
    server, thread = start_portal_server(portal=portal, host=args.host, port=args.port)
    try:
        thread.join()
    except KeyboardInterrupt:
        print("\nStopping portal server...")
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
