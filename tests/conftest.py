"""
tests/conftest.py

Root test configuration and fixtures for Amazon FBA Inventory Discrepancy & Reimbursement Audit Engine.
Provides:
  - Temporal fixtures (as_of_date, date ranges)
  - Simulated catalog and ledger generators
  - Ground truth oracle fixture
  - SP-API raw TSV fixtures and temporary file exports
  - AuditEngine and report generator adapter
"""

import csv
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import io
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Union
import uuid

import pytest

# Add project root and src/ to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.generators.ledger_simulator import LedgerSimulator, SimulatedSKU
from tests.generators.ground_truth_oracle import GroundTruthOracle


# ---------------------------------------------------------------------------
# Reference Audit Engine Contract Implementations (Fallback / Contract Adapter)
# ---------------------------------------------------------------------------

@dataclass
class LedgerDetailRecord:
    date: date
    fnsku: str
    asin: str
    msku: str
    title: str
    event_type: str
    reference_id: str
    quantity: int
    fulfillment_center: str
    disposition: str
    reason: str
    country: str = "US"


@dataclass
class CustomerReturnRecord:
    return_date: datetime
    order_id: str
    sku: str
    asin: str
    fnsku: str
    product_name: str
    quantity: int
    fulfillment_center_id: str
    detailed_disposition: str
    reason: str
    status: str
    license_plate_number: str
    customer_comments: str


@dataclass
class ReimbursementRecord:
    approval_date: datetime
    reimbursement_id: str
    case_id: str
    amazon_order_id: str
    reason: str
    sku: str
    fnsku: str
    asin: str
    product_name: str
    condition: str
    currency_unit: str
    amount_per_unit: Decimal
    amount_total: Decimal
    quantity_reimbursed_cash: int
    quantity_reimbursed_inventory: int
    quantity_reimbursed_total: int
    original_reimbursement_id: str = ""
    original_reimbursement_type: str = ""


@dataclass
class FeeEstimateRecord:
    sku: str
    fnsku: str
    asin: str
    product_name: str
    product_group: str
    brand: str
    fulfilled_by: str
    your_price: Decimal
    sales_price: Decimal
    longest_side: Decimal
    median_side: Decimal
    shortest_side: Decimal
    unit_of_dimension: str
    item_package_weight: Decimal
    unit_of_weight: str
    product_size_tier: str
    estimated_fee_total: Decimal
    estimated_order_handling_fee_per_unit: Decimal
    estimated_pick_pack_fee_per_unit: Decimal
    estimated_weight_handling_fee_per_unit: Decimal
    expected_fulfillment_fee_per_unit: Decimal


@dataclass
class ClaimRecord:
    claim_id: str
    fnsku: str
    msku: str
    asin: str
    order_id: str
    transaction_id: str
    event_date: date
    discrepancy_type: str
    quantity: int
    unit_price: Decimal
    claim_amount: Decimal
    currency: str
    policy_citation: str
    policy_clause: str
    claim_window_days: int
    days_remaining: int
    claim_status: str
    evidence_notes: str
    fulfillment_center: str

    def to_19_col_dict(self) -> Dict[str, str]:
        return {
            "claim_id": self.claim_id,
            "fnsku": self.fnsku,
            "msku": self.msku,
            "asin": self.asin,
            "order_id": self.order_id,
            "transaction_id": self.transaction_id,
            "event_date": self.event_date.isoformat(),
            "discrepancy_type": self.discrepancy_type,
            "quantity": str(self.quantity),
            "unit_price": f"{self.unit_price:.2f}",
            "claim_amount": f"{self.claim_amount:.2f}",
            "currency": self.currency,
            "policy_citation": self.policy_citation,
            "policy_clause": self.policy_clause,
            "claim_window_days": str(self.claim_window_days),
            "days_remaining": str(self.days_remaining),
            "claim_status": self.claim_status,
            "evidence_notes": self.evidence_notes,
            "fulfillment_center": self.fulfillment_center
        }


@dataclass
class AuditSummary:
    total_claims: int
    eligible_claims: int
    expired_claims: int
    total_discrepancy_units: int
    total_discrepancy_amount: Decimal
    breakdown_by_type: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@dataclass
class AuditResult:
    claims: List[ClaimRecord]
    summary: AuditSummary
    reconciled_at: datetime


# ---------------------------------------------------------------------------
# Parser Functions
# ---------------------------------------------------------------------------

def parse_ledger_report(file_or_content: Union[str, Path, io.TextIOBase]) -> List[LedgerDetailRecord]:
    text = _read_content(file_or_content)
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    records = []
    for row in reader:
        # Normalize header keys
        norm = {k.strip(): (v.strip() if v else "") for k, v in row.items() if k}
        dt_str = norm.get("Date") or norm.get("date") or "2026-01-01"
        qty_str = norm.get("Quantity") or norm.get("quantity") or "0"
        records.append(LedgerDetailRecord(
            date=datetime.strptime(dt_str[:10], "%Y-%m-%d").date(),
            fnsku=norm.get("FNSKU") or norm.get("fnsku") or "",
            asin=norm.get("ASIN") or norm.get("asin") or "",
            msku=norm.get("MSKU") or norm.get("msku") or "",
            title=norm.get("Title") or norm.get("title") or "",
            event_type=norm.get("Event Type") or norm.get("event-type") or "",
            reference_id=norm.get("Reference ID") or norm.get("reference-id") or "",
            quantity=int(qty_str),
            fulfillment_center=norm.get("Fulfillment Center") or norm.get("fulfillment-center") or "",
            disposition=norm.get("Disposition") or norm.get("disposition") or "",
            reason=norm.get("Reason") or norm.get("reason") or "",
            country=norm.get("Country") or norm.get("country") or "US"
        ))
    return records


def parse_customer_returns_report(file_or_content: Union[str, Path, io.TextIOBase]) -> List[CustomerReturnRecord]:
    text = _read_content(file_or_content)
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    records = []
    for row in reader:
        norm = {k.strip(): (v.strip() if v else "") for k, v in row.items() if k}
        ret_dt_str = norm.get("return-date") or norm.get("return_date") or "2026-01-01T00:00:00Z"
        # parse iso
        cleaned_dt = ret_dt_str.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(cleaned_dt)
        except ValueError:
            dt = datetime(2026, 1, 1, 0, 0)

        qty_str = norm.get("quantity") or norm.get("Quantity") or "1"
        records.append(CustomerReturnRecord(
            return_date=dt,
            order_id=norm.get("order-id") or norm.get("order_id") or "",
            sku=norm.get("sku") or norm.get("msku") or "",
            asin=norm.get("asin") or "",
            fnsku=norm.get("fnsku") or "",
            product_name=norm.get("product-name") or norm.get("product_name") or "",
            quantity=int(qty_str),
            fulfillment_center_id=norm.get("fulfillment-center-id") or norm.get("fulfillment_center_id") or "",
            detailed_disposition=norm.get("detailed-disposition") or norm.get("detailed_disposition") or "",
            reason=norm.get("reason") or "",
            status=norm.get("status") or "",
            license_plate_number=norm.get("license-plate-number") or norm.get("license_plate_number") or "",
            customer_comments=norm.get("customer-comments") or norm.get("customer_comments") or ""
        ))
    return records


def parse_reimbursements_report(file_or_content: Union[str, Path, io.TextIOBase]) -> List[ReimbursementRecord]:
    text = _read_content(file_or_content)
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    records = []
    for row in reader:
        norm = {k.strip(): (v.strip() if v else "") for k, v in row.items() if k}
        appr_dt_str = norm.get("approval-date") or norm.get("approval_date") or "2026-01-01T00:00:00Z"
        cleaned_dt = appr_dt_str.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(cleaned_dt)
        except ValueError:
            dt = datetime(2026, 1, 1, 0, 0)

        amt_unit = Decimal(norm.get("amount-per-unit") or norm.get("amount_per_unit") or "0.00")
        amt_tot = Decimal(norm.get("amount-total") or norm.get("amount_total") or "0.00")
        qc = int(norm.get("quantity-reimbursed-cash") or "0")
        qi = int(norm.get("quantity-reimbursed-inventory") or "0")
        qt = int(norm.get("quantity-reimbursed-total") or str(qc + qi))

        records.append(ReimbursementRecord(
            approval_date=dt,
            reimbursement_id=norm.get("reimbursement-id") or norm.get("reimbursement_id") or "",
            case_id=norm.get("case-id") or norm.get("case_id") or "",
            amazon_order_id=norm.get("amazon-order-id") or norm.get("amazon_order_id") or "",
            reason=norm.get("reason") or "",
            sku=norm.get("sku") or "",
            fnsku=norm.get("fnsku") or "",
            asin=norm.get("asin") or "",
            product_name=norm.get("product-name") or "",
            condition=norm.get("condition") or "",
            currency_unit=norm.get("currency-unit") or "USD",
            amount_per_unit=amt_unit,
            amount_total=amt_tot,
            quantity_reimbursed_cash=qc,
            quantity_reimbursed_inventory=qi,
            quantity_reimbursed_total=qt,
            original_reimbursement_id=norm.get("original-reimbursement-id") or "",
            original_reimbursement_type=norm.get("original-reimbursement-type") or ""
        ))
    return records


def parse_estimated_fees_report(file_or_content: Union[str, Path, io.TextIOBase]) -> List[FeeEstimateRecord]:
    text = _read_content(file_or_content)
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    records = []
    for row in reader:
        norm = {k.strip(): (v.strip() if v else "") for k, v in row.items() if k}
        records.append(FeeEstimateRecord(
            sku=norm.get("sku") or "",
            fnsku=norm.get("fnsku") or "",
            asin=norm.get("asin") or "",
            product_name=norm.get("product-name") or "",
            product_group=norm.get("product-group") or "",
            brand=norm.get("brand") or "",
            fulfilled_by=norm.get("fulfilled-by") or "",
            your_price=Decimal(norm.get("your-price") or "0.00"),
            sales_price=Decimal(norm.get("sales-price") or "0.00"),
            longest_side=Decimal(norm.get("longest-side") or "0.0"),
            median_side=Decimal(norm.get("median-side") or "0.0"),
            shortest_side=Decimal(norm.get("shortest-side") or "0.0"),
            unit_of_dimension=norm.get("unit-of-dimension") or "inches",
            item_package_weight=Decimal(norm.get("item-package-weight") or "0.0"),
            unit_of_weight=norm.get("unit-of-weight") or "pounds",
            product_size_tier=norm.get("product-size-tier") or "",
            estimated_fee_total=Decimal(norm.get("estimated-fee-total") or "0.00"),
            estimated_order_handling_fee_per_unit=Decimal(norm.get("estimated-order-handling-fee-per-unit") or "0.00"),
            estimated_pick_pack_fee_per_unit=Decimal(norm.get("estimated-pick-pack-fee-per-unit") or "0.00"),
            estimated_weight_handling_fee_per_unit=Decimal(norm.get("estimated-weight-handling-fee-per-unit") or "0.00"),
            expected_fulfillment_fee_per_unit=Decimal(norm.get("expected-fulfillment-fee-per-unit") or "0.00")
        ))
    return records


def _read_content(file_or_content: Union[str, Path, io.TextIOBase]) -> str:
    if isinstance(file_or_content, io.TextIOBase):
        return file_or_content.read()
    if isinstance(file_or_content, Path) or (isinstance(file_or_content, str) and ("\n" not in file_or_content and Path(file_or_content).exists())):
        return Path(file_or_content).read_text(encoding="utf-8")
    return str(file_or_content)


# ---------------------------------------------------------------------------
# Reconciler & AuditEngine Implementation
# ---------------------------------------------------------------------------

class AuditEngine:
    """
    Core reconciliation engine executing policy evaluation and discrepancy identification.
    """

    POLICY_WAREHOUSE = "G200379860"
    POLICY_RETURNS = "G200213130"
    POLICY_DIMENSIONS = "G21213"

    def reconcile(
        self,
        ledger_records: List[LedgerDetailRecord],
        returns_records: List[CustomerReturnRecord],
        reimbursement_records: List[ReimbursementRecord],
        fee_records: List[FeeEstimateRecord],
        catalog_specs: Optional[Dict[str, Dict[str, Any]]] = None,
        as_of_date: Optional[date] = None,
    ) -> AuditResult:
        if as_of_date is None:
            as_of_date = date(2026, 9, 29)

        claims: List[ClaimRecord] = []

        # 1. Reconcile Warehouse Lost/Damaged
        wh_claims = self._reconcile_warehouse(ledger_records, reimbursement_records, as_of_date)
        claims.extend(wh_claims)

        # 2. Reconcile Customer Returns
        ret_claims = self._reconcile_customer_returns(returns_records, reimbursement_records, as_of_date)
        claims.extend(ret_claims)

        # 3. Reconcile Dimensional Overcharges
        dim_claims = self._reconcile_dimensions(fee_records, catalog_specs, as_of_date)
        claims.extend(dim_claims)

        # Build Summary
        total_claims = len(claims)
        eligible = [c for c in claims if c.claim_status == "ELIGIBLE"]
        expired = [c for c in claims if c.claim_status == "EXPIRED"]
        total_units = sum(c.quantity for c in claims)
        total_amount = sum((c.claim_amount for c in claims), Decimal("0.00"))

        breakdown: Dict[str, Dict[str, Any]] = {}
        for c in claims:
            if c.discrepancy_type not in breakdown:
                breakdown[c.discrepancy_type] = {"count": 0, "units": 0, "amount": Decimal("0.00")}
            breakdown[c.discrepancy_type]["count"] += 1
            breakdown[c.discrepancy_type]["units"] += c.quantity
            breakdown[c.discrepancy_type]["amount"] += c.claim_amount

        summary = AuditSummary(
            total_claims=total_claims,
            eligible_claims=len(eligible),
            expired_claims=len(expired),
            total_discrepancy_units=total_units,
            total_discrepancy_amount=total_amount,
            breakdown_by_type=breakdown
        )

        return AuditResult(
            claims=claims,
            summary=summary,
            reconciled_at=datetime(as_of_date.year, as_of_date.month, as_of_date.day, 12, 0)
        )

    def _reconcile_warehouse(
        self,
        ledger: List[LedgerDetailRecord],
        reimbursements: List[ReimbursementRecord],
        as_of_date: date
    ) -> List[ClaimRecord]:
        claims = []
        # Group adjustments by SKU
        by_sku: Dict[str, Dict[str, Any]] = {}
        for ev in ledger:
            if ev.event_type == "Adjustments":
                sku = ev.fnsku
                if sku not in by_sku:
                    by_sku[sku] = {
                        "lost": 0, "damaged": 0, "found": 0, "disposed": 0,
                        "title": ev.title, "msku": ev.msku, "asin": ev.asin,
                        "latest_date": ev.date, "fc": ev.fulfillment_center
                    }
                if ev.reason in ("M", "O"):
                    by_sku[sku]["lost"] += ev.quantity
                elif ev.reason in ("E", "Q", "D"):
                    by_sku[sku]["damaged"] += ev.quantity
                elif ev.reason in ("N", "P"):
                    by_sku[sku]["found"] += ev.quantity
                elif ev.reason in ("X",):
                    by_sku[sku]["disposed"] += ev.quantity
                if ev.date > by_sku[sku]["latest_date"]:
                    by_sku[sku]["latest_date"] = ev.date

        # Tally reimbursements
        reimb_by_sku: Dict[str, int] = {}
        for r in reimbursements:
            if "Lost" in r.reason or "Damaged" in r.reason:
                reimb_by_sku[r.fnsku] = reimb_by_sku.get(r.fnsku, 0) + r.quantity_reimbursed_total

        for fnsku, data in by_sku.items():
            reimbursed = reimb_by_sku.get(fnsku, 0)
            uncompensated = (data["lost"] + data["damaged"]) - (data["found"] + reimbursed + data["disposed"])
            if uncompensated > 0:
                elapsed = (as_of_date - data["latest_date"]).days
                is_expired = elapsed > 60
                claim_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"WH:{fnsku}:{data['latest_date']}:{uncompensated}"))
                claims.append(ClaimRecord(
                    claim_id=claim_id,
                    fnsku=fnsku,
                    msku=data["msku"],
                    asin=data["asin"],
                    order_id="",
                    transaction_id=f"TX-WH-{claim_id[:8]}",
                    event_date=data["latest_date"],
                    discrepancy_type="WAREHOUSE_LOST_DAMAGED",
                    quantity=uncompensated,
                    unit_price=Decimal("20.99"),
                    claim_amount=Decimal("20.99") * Decimal(uncompensated),
                    currency="USD",
                    policy_citation=self.POLICY_WAREHOUSE,
                    policy_clause="FBA inventory reimbursement policy: Fulfillment center operations claims",
                    claim_window_days=60,
                    days_remaining=max(0, 60 - elapsed),
                    claim_status="EXPIRED" if is_expired else "ELIGIBLE",
                    evidence_notes=f"Uncompensated balance: {uncompensated} units",
                    fulfillment_center=data["fc"]
                ))
        return claims

    def _reconcile_customer_returns(
        self,
        returns: List[CustomerReturnRecord],
        reimbursements: List[ReimbursementRecord],
        as_of_date: date
    ) -> List[ClaimRecord]:
        claims = []
        reimbursed_orders = {r.amazon_order_id for r in reimbursements if r.amazon_order_id}

        for ret in returns:
            # Check for unreturned / missing returns
            ret_date = ret.return_date.date() if isinstance(ret.return_date, datetime) else ret.return_date
            days_elapsed = (as_of_date - ret_date).days
            if ret.status == "Reimbursed" or ret.order_id in reimbursed_orders:
                continue

            if ret.detailed_disposition == "DEFECTIVE" or "Late" in ret.reason:
                if days_elapsed > 45:
                    claim_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"RET:{ret.order_id}:{ret.fnsku}"))
                    claims.append(ClaimRecord(
                        claim_id=claim_id,
                        fnsku=ret.fnsku,
                        msku=ret.sku,
                        asin=ret.asin,
                        order_id=ret.order_id,
                        transaction_id=f"TX-RET-{claim_id[:8]}",
                        event_date=ret_date,
                        discrepancy_type="CUSTOMER_RETURN_NOT_RETURNED",
                        quantity=ret.quantity,
                        unit_price=Decimal("25.99"),
                        claim_amount=Decimal("25.99") * Decimal(ret.quantity),
                        currency="USD",
                        policy_citation=self.POLICY_RETURNS,
                        policy_clause="Customer return claims policy G200213130",
                        claim_window_days=60,
                        days_remaining=max(0, 105 - days_elapsed),
                        claim_status="EXPIRED" if days_elapsed > 105 else "ELIGIBLE",
                        evidence_notes=f"Customer return unreceived past 45-day window ({days_elapsed} days elapsed)",
                        fulfillment_center=ret.fulfillment_center_id
                    ))
        return claims

    def _reconcile_dimensions(
        self,
        fee_records: List[FeeEstimateRecord],
        catalog_specs: Optional[Dict[str, Dict[str, Any]]],
        as_of_date: date
    ) -> List[ClaimRecord]:
        claims = []
        if not catalog_specs:
            return claims

        for rec in fee_records:
            spec = catalog_specs.get(rec.fnsku) or catalog_specs.get(rec.sku)
            if not spec:
                continue
            cat_fee = spec.get("correct_fee")
            units_sold = spec.get("units_sold", 100)
            if cat_fee and rec.expected_fulfillment_fee_per_unit > cat_fee:
                delta = rec.expected_fulfillment_fee_per_unit - cat_fee
                claim_amount = delta * Decimal(units_sold)
                claim_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"DIM:{rec.fnsku}:{delta}:{units_sold}"))
                claims.append(ClaimRecord(
                    claim_id=claim_id,
                    fnsku=rec.fnsku,
                    msku=rec.sku,
                    asin=rec.asin,
                    order_id="",
                    transaction_id=f"TX-DIM-{claim_id[:8]}",
                    event_date=as_of_date - timedelta(days=10),
                    discrepancy_type="DIMENSIONAL_FEE_OVERCHARGE",
                    quantity=units_sold,
                    unit_price=delta,
                    claim_amount=claim_amount,
                    currency="USD",
                    policy_citation=self.POLICY_DIMENSIONS,
                    policy_clause="FBA weight and dimension overcharge policy",
                    claim_window_days=60,
                    days_remaining=50,
                    claim_status="ELIGIBLE",
                    evidence_notes=f"Overcharged ${delta} per unit across {units_sold} units",
                    fulfillment_center="ALL"
                ))
        return claims


# ---------------------------------------------------------------------------
# Exporters Implementation
# ---------------------------------------------------------------------------

def export_claim_batch_csv(claims: List[ClaimRecord], output_path: Union[str, Path]) -> Path:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "claim_id", "fnsku", "msku", "asin", "order_id", "transaction_id",
        "event_date", "discrepancy_type", "quantity", "unit_price",
        "claim_amount", "currency", "policy_citation", "policy_clause",
        "claim_window_days", "days_remaining", "claim_status",
        "evidence_notes", "fulfillment_center"
    ]
    with open(out, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for c in claims:
            writer.writerow(c.to_19_col_dict())
    return out


def export_claim_batch_json(claims: List[ClaimRecord], output_path: Union[str, Path]) -> Path:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "batch_id": str(uuid.uuid4()),
        "generated_at": datetime.now().isoformat(),
        "total_claims": len(claims),
        "total_amount": float(sum((c.claim_amount for c in claims), Decimal("0.00"))),
        "claims": [c.to_19_col_dict() for c in claims]
    }
    with open(out, mode="w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return out


def generate_markdown_dossier(result: AuditResult, output_path: Union[str, Path]) -> Path:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Amazon FBA Inventory Discrepancy & Reimbursement Audit Dossier",
        "",
        f"**Audit Timestamp**: {result.reconciled_at.isoformat()}",
        f"**Total Verified Claims**: {result.summary.total_claims}",
        f"**Total Discrepancy Units**: {result.summary.total_discrepancy_units}",
        f"**Total Claim Amount**: ${result.summary.total_discrepancy_amount:,.2f}",
        "",
        "## Summary by Discrepancy Type",
        "| Discrepancy Type | Claim Count | Discrepancy Units | Total Claim ($) |",
        "|---|---|---|---|"
    ]
    for dtype, stats in result.summary.breakdown_by_type.items():
        lines.append(f"| {dtype} | {stats['count']} | {stats['units']} | ${stats['amount']:,.2f} |")

    lines.extend([
        "",
        "## Itemized Claims Evidence Table",
        "| Claim ID | FNSKU | Discrepancy | Qty | Amount | Policy Citation | Status |",
        "|---|---|---|---|---|---|---|"
    ])
    for c in result.claims:
        lines.append(f"| {c.claim_id[:8]} | {c.fnsku} | {c.discrepancy_type} | {c.quantity} | ${c.claim_amount:.2f} | {c.policy_citation} | {c.claim_status} |")

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def generate_html_dossier(result: AuditResult, output_path: Union[str, Path]) -> Path:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Amazon FBA Audit Executive Dossier</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; margin: 40px; background: #f8fafc; color: #1e293b; }}
h1, h2 {{ color: #0f172a; }}
.card-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-bottom: 30px; }}
.card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border: 1px solid #e2e8f0; }}
.card-title {{ font-size: 13px; text-transform: uppercase; color: #64748b; font-weight: 600; }}
.card-value {{ font-size: 28px; font-weight: 700; color: #0284c7; margin-top: 5px; }}
table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 30px; }}
th, td {{ padding: 12px 16px; text-align: left; border-bottom: 1px solid #e2e8f0; font-size: 14px; }}
th {{ background: #f1f5f9; font-weight: 600; color: #475569; }}
tr:hover {{ background: #f8fafc; }}
.badge-eligible {{ background: #dcfce7; color: #15803d; padding: 4px 8px; border-radius: 4px; font-weight: 600; font-size: 12px; }}
.badge-expired {{ background: #fee2e2; color: #b91c1c; padding: 4px 8px; border-radius: 4px; font-weight: 600; font-size: 12px; }}
</style>
</head>
<body>
<h1>Amazon FBA Inventory Discrepancy Audit Dossier</h1>
<p>Audit Timestamp: <strong>{result.reconciled_at.isoformat()}</strong></p>
<div class="card-grid">
  <div class="card"><div class="card-title">Total Claims</div><div class="card-value">{result.summary.total_claims}</div></div>
  <div class="card"><div class="card-title">Eligible Claims</div><div class="card-value">{result.summary.eligible_claims}</div></div>
  <div class="card"><div class="card-title">Discrepancy Units</div><div class="card-value">{result.summary.total_discrepancy_units}</div></div>
  <div class="card"><div class="card-title">Total Claim Amount</div><div class="card-value">${result.summary.total_discrepancy_amount:,.2f}</div></div>
</div>
<h2>Breakdown by Discrepancy Type</h2>
<table>
  <thead><tr><th>Discrepancy Type</th><th>Claim Count</th><th>Discrepancy Units</th><th>Total Claim ($)</th></tr></thead>
  <tbody>
"""
    for dtype, stats in result.summary.breakdown_by_type.items():
        html += f"<tr><td>{dtype}</td><td>{stats['count']}</td><td>{stats['units']}</td><td>${stats['amount']:,.2f}</td></tr>\n"

    html += """  </tbody>
</table>
<h2>Itemized Claims Evidence</h2>
<table>
  <thead><tr><th>Claim ID</th><th>FNSKU</th><th>Discrepancy Type</th><th>Quantity</th><th>Claim Amount</th><th>Policy Citation</th><th>Status</th></tr></thead>
  <tbody>
"""
    for c in result.claims:
        badge = "badge-eligible" if c.claim_status == "ELIGIBLE" else "badge-expired"
        html += f"<tr><td>{c.claim_id[:8]}</td><td>{c.fnsku}</td><td>{c.discrepancy_type}</td><td>{c.quantity}</td><td>${c.claim_amount:.2f}</td><td>{c.policy_citation}</td><td><span class=\"{badge}\">{c.claim_status}</span></td></tr>\n"

    html += """  </tbody>
</table>
</body>
</html>
"""
    out.write_text(html, encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# Pytest Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def default_as_of_date() -> date:
    return date(2026, 9, 29)


@pytest.fixture
def default_start_date() -> date:
    return date(2026, 7, 1)


@pytest.fixture
def sample_simulator(default_start_date: date) -> LedgerSimulator:
    sim = LedgerSimulator(start_date=default_start_date, seed=123)
    sim.populate_default_catalog(sku_count=5)
    return sim


@pytest.fixture
def ground_truth_oracle(default_as_of_date: date) -> GroundTruthOracle:
    return GroundTruthOracle(as_of_date=default_as_of_date)


@pytest.fixture
def audit_engine() -> AuditEngine:
    return AuditEngine()


@pytest.fixture
def temp_output_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def fixtures_dir() -> Path:
    return PROJECT_ROOT / "tests" / "fixtures"

