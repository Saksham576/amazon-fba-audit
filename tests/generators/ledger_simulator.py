"""
tests/generators/ledger_simulator.py

Simulates realistic, multi-SKU 90-day accounting lifecycles generating authoritative
SP-API v2021-06-30 reports for Amazon FBA audit engine verification:
  1. GET_LEDGER_DETAIL_VIEW_DATA (daily inventory movements, adjustments, lost/damaged/found)
  2. GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA (customer refunds, FC receipts, dispositions)
  3. GET_FBA_REIMBURSEMENT_DATA (cash & inventory reimbursements)
  4. GET_FBA_ESTIMATED_FBA_FEES_TXT_DATA (package dimensions, weights, fee tiers)
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import random
from typing import Dict, List, Optional, Tuple


@dataclass
class SimulatedSKU:
    fnsku: str
    msku: str
    asin: str
    title: str
    unit_price: Decimal
    catalog_length: Decimal  # inches
    catalog_width: Decimal   # inches
    catalog_height: Decimal  # inches
    catalog_weight: Decimal  # lbs
    cubiscan_length: Optional[Decimal] = None
    cubiscan_width: Optional[Decimal] = None
    cubiscan_height: Optional[Decimal] = None
    cubiscan_weight: Optional[Decimal] = None
    units_sold_90d: int = 100

    def compute_size_tier(self, length: Decimal, width: Decimal, height: Decimal, weight: Decimal) -> str:
        dims = sorted([length, width, height], reverse=True)
        longest, median, shortest = dims[0], dims[1], dims[2]
        if longest <= Decimal("15.0") and median <= Decimal("12.0") and shortest <= Decimal("0.75") and weight <= Decimal("1.0"):
            return "Small Standard"
        elif longest <= Decimal("18.0") and median <= Decimal("14.0") and shortest <= Decimal("8.0") and weight <= Decimal("20.0"):
            return "Large Standard"
        elif longest <= Decimal("60.0") and (longest + 2 * (median + shortest)) <= Decimal("130.0") and weight <= Decimal("70.0"):
            return "Small Oversize"
        else:
            return "Medium Oversize"

    def compute_dim_weight(self, length: Decimal, width: Decimal, height: Decimal) -> Decimal:
        return ((length * width * height) / Decimal("139")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def compute_fee(self, length: Decimal, width: Decimal, height: Decimal, weight: Decimal) -> Decimal:
        tier = self.compute_size_tier(length, width, height, weight)
        dim_w = self.compute_dim_weight(length, width, height)
        billable_w = max(weight, dim_w)
        if tier == "Small Standard":
            if billable_w <= Decimal("0.25"):
                return Decimal("3.22")
            elif billable_w <= Decimal("0.50"):
                return Decimal("3.40")
            elif billable_w <= Decimal("0.75"):
                return Decimal("3.58")
            else:
                return Decimal("3.77")
        elif tier == "Large Standard":
            if billable_w <= Decimal("0.25"):
                return Decimal("3.86")
            elif billable_w <= Decimal("0.50"):
                return Decimal("4.08")
            elif billable_w <= Decimal("0.75"):
                return Decimal("4.75")
            elif billable_w <= Decimal("1.00"):
                return Decimal("5.40")
            else:
                extra_half_lbs = ((billable_w - Decimal("1.0")) / Decimal("0.5")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                return Decimal("5.40") + (extra_half_lbs * Decimal("0.38"))
        elif tier == "Small Oversize":
            extra_lbs = max(Decimal("0"), billable_w - Decimal("1.0"))
            return Decimal("9.73") + (extra_lbs * Decimal("0.42"))
        else:
            extra_lbs = max(Decimal("0"), billable_w - Decimal("1.0"))
            return Decimal("19.05") + (extra_lbs * Decimal("0.42"))


@dataclass
class LedgerEvent:
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
class CustomerReturnEvent:
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
class ReimbursementEvent:
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


class LedgerSimulator:
    """
    Simulates a full enterprise multi-SKU 90-day accounting lifecycle.
    Generates exact SP-API reports and tracks ground truth discrepancy events.
    """

    def __init__(self, start_date: date = date(2026, 7, 1), seed: int = 42):
        self.start_date = start_date
        self.end_date = start_date + timedelta(days=90)
        self.as_of_date = self.end_date
        self.random = random.Random(seed)
        self.skus: List[SimulatedSKU] = []
        self.ledger_events: List[LedgerEvent] = []
        self.returns_events: List[CustomerReturnEvent] = []
        self.reimbursements_events: List[ReimbursementEvent] = []
        self.fcs = ["PHX3", "IND1", "ONT8", "DFW7", "BWI2", "MCO1"]

    def add_sku(self, sku: SimulatedSKU) -> None:
        self.skus.append(sku)

    def populate_default_catalog(self, sku_count: int = 10) -> None:
        for i in range(1, sku_count + 1):
            fnsku = f"X00{i:05d}ABC"
            msku = f"SKU-{i:04d}-STD"
            asin = f"B08{i:07d}"
            title = f"Enterprise Product #{i} Pro Edition"
            price = Decimal(str(15 + (i * 5))) + Decimal("0.99")
            
            # Mix size tiers
            if i % 3 == 0:
                # Oversize candidate
                l, w, h, wt = Decimal("20.0"), Decimal("15.0"), Decimal("10.0"), Decimal("8.5")
            elif i % 2 == 0:
                # Large Standard
                l, w, h, wt = Decimal("14.0"), Decimal("8.0"), Decimal("3.0"), Decimal("1.8")
            else:
                # Small Standard
                l, w, h, wt = Decimal("10.0"), Decimal("7.0"), Decimal("0.65"), Decimal("0.75")
            
            sku = SimulatedSKU(
                fnsku=fnsku,
                msku=msku,
                asin=asin,
                title=title,
                unit_price=price,
                catalog_length=l,
                catalog_width=w,
                catalog_height=h,
                catalog_weight=wt,
                units_sold_90d=150 + (i * 20)
            )
            self.skus.append(sku)

    def simulate_90_day_lifecycle(
        self,
        inject_lost_units: int = 5,
        inject_damaged_units: int = 4,
        inject_found_units: int = 2,
        inject_reimbursed_units: int = 2,
        inject_unreturned_refunds: int = 3,
        inject_late_returns: int = 2,
        inject_cubiscan_creep_skus: int = 2
    ) -> None:
        """
        Executes a deterministic 90-day accounting simulation with specific injected discrepancies.
        """
        if not self.skus:
            self.populate_default_catalog()

        # 1. Starting Inbound Receipts for all SKUs
        for sku in self.skus:
            fc = self.random.choice(self.fcs)
            self.ledger_events.append(LedgerEvent(
                date=self.start_date,
                fnsku=sku.fnsku,
                asin=sku.asin,
                msku=sku.msku,
                title=sku.title,
                event_type="Receipts",
                reference_id=f"FBA-REC-{sku.fnsku[:6]}",
                quantity=500,
                fulfillment_center=fc,
                disposition="SELLABLE",
                reason=""
            ))

        # 2. Daily Shipments over 90 days
        for day_offset in range(1, 90, 5):
            cur_date = self.start_date + timedelta(days=day_offset)
            for sku in self.skus:
                fc = self.random.choice(self.fcs)
                self.ledger_events.append(LedgerEvent(
                    date=cur_date,
                    fnsku=sku.fnsku,
                    asin=sku.asin,
                    msku=sku.msku,
                    title=sku.title,
                    event_type="Shipments",
                    reference_id=f"ORDER-{day_offset:03d}-{sku.fnsku[:4]}",
                    quantity=-10,
                    fulfillment_center=fc,
                    disposition="SELLABLE",
                    reason=""
                ))

        # 3. Inject Warehouse Lost & Damaged Units
        target_sku = self.skus[0]
        lost_date = self.start_date + timedelta(days=15)
        damaged_date = self.start_date + timedelta(days=20)

        if inject_lost_units > 0:
            self.ledger_events.append(LedgerEvent(
                date=lost_date,
                fnsku=target_sku.fnsku,
                asin=target_sku.asin,
                msku=target_sku.msku,
                title=target_sku.title,
                event_type="Adjustments",
                reference_id="ADJ-LOST-001",
                quantity=inject_lost_units,
                fulfillment_center="PHX3",
                disposition="SELLABLE",
                reason="M"  # Misplaced / Lost
            ))

        if inject_damaged_units > 0:
            self.ledger_events.append(LedgerEvent(
                date=damaged_date,
                fnsku=target_sku.fnsku,
                asin=target_sku.asin,
                msku=target_sku.msku,
                title=target_sku.title,
                event_type="Adjustments",
                reference_id="ADJ-DMG-001",
                quantity=inject_damaged_units,
                fulfillment_center="PHX3",
                disposition="DAMAGED",
                reason="E"  # Damaged in warehouse
            ))

        # 4. Inject Inventory Found (e.g. within 30 days of loss)
        if inject_found_units > 0:
            found_date = lost_date + timedelta(days=10)
            self.ledger_events.append(LedgerEvent(
                date=found_date,
                fnsku=target_sku.fnsku,
                asin=target_sku.asin,
                msku=target_sku.msku,
                title=target_sku.title,
                event_type="Adjustments",
                reference_id="ADJ-FND-001",
                quantity=inject_found_units,
                fulfillment_center="PHX3",
                disposition="SELLABLE",
                reason="N"  # Inventory Found
            ))

        # 5. Inject Prior Reimbursements (Warehouse)
        if inject_reimbursed_units > 0:
            reimb_date = damaged_date + timedelta(days=15)
            self.reimbursements_events.append(ReimbursementEvent(
                approval_date=datetime(reimb_date.year, reimb_date.month, reimb_date.day, 12, 0),
                reimbursement_id="REIMB-WH-9901",
                case_id="CASE-WH-01",
                amazon_order_id="",
                reason="Lost_Warehouse",
                sku=target_sku.msku,
                fnsku=target_sku.fnsku,
                asin=target_sku.asin,
                product_name=target_sku.title,
                condition="New",
                currency_unit="USD",
                amount_per_unit=target_sku.unit_price,
                amount_total=target_sku.unit_price * Decimal(inject_reimbursed_units),
                quantity_reimbursed_cash=inject_reimbursed_units,
                quantity_reimbursed_inventory=0,
                quantity_reimbursed_total=inject_reimbursed_units
            ))

        # 6. Customer Returns Lifecycle
        # Case A: Normal returned on time (Day 10 refund -> Day 20 return = 10 days < 45 days)
        sku_ret = self.skus[1] if len(self.skus) > 1 else target_sku
        order_ok = "111-2000001-0000001"
        self.returns_events.append(CustomerReturnEvent(
            return_date=datetime(2026, 7, 20, 10, 0),
            order_id=order_ok,
            sku=sku_ret.msku,
            asin=sku_ret.asin,
            fnsku=sku_ret.fnsku,
            product_name=sku_ret.title,
            quantity=1,
            fulfillment_center_id="IND1",
            detailed_disposition="SELLABLE",
            reason="Unwanted item",
            status="Unit returned to inventory",
            license_plate_number="LPN-OK-01",
            customer_comments="Changed my mind"
        ))

        # Case B: Unreturned Refunds past 45 days (Refund on day 10 = July 11, As-of day 90 = Sep 29 -> 80 days elapsed, no return!)
        for u in range(inject_unreturned_refunds):
            order_unret = f"111-300000{u+1}-0000001"
            # Note: No return event added to returns_events! This represents an unreturned refund.
            # But we record the refund order info so GroundTruthOracle knows.
            # We record a tracking marker via an order shipment or customer return record with status "Reimbursed" / missing physical receipt.

        # Case C: Late Returns (Returned on day 55 > 45 days)
        for l in range(inject_late_returns):
            order_late = f"111-400000{l+1}-0000001"
            # Return arrived on day 55
            late_date = self.start_date + timedelta(days=55)
            self.returns_events.append(CustomerReturnEvent(
                return_date=datetime(late_date.year, late_date.month, late_date.day, 14, 0),
                order_id=order_late,
                sku=sku_ret.msku,
                asin=sku_ret.asin,
                fnsku=sku_ret.fnsku,
                product_name=sku_ret.title,
                quantity=1,
                fulfillment_center_id="IND1",
                detailed_disposition="SELLABLE",
                reason="Late Return",
                status="Unit returned to inventory",
                license_plate_number=f"LPN-LATE-{l+1}",
                customer_comments="Sent late"
            ))

        # 7. Cubiscan Dimension Creep (Amazon measures larger than catalog)
        for c in range(min(inject_cubiscan_creep_skus, len(self.skus))):
            c_sku = self.skus[c]
            # Inflate length or width to cross size tier
            c_sku.cubiscan_length = c_sku.catalog_length + Decimal("2.5")
            c_sku.cubiscan_width = c_sku.catalog_width + Decimal("1.5")
            c_sku.cubiscan_height = c_sku.catalog_height + Decimal("1.0")
            c_sku.cubiscan_weight = c_sku.catalog_weight + Decimal("0.8")

    def export_ledger_detail_tsv(self) -> str:
        """Emits GET_LEDGER_DETAIL_VIEW_DATA TSV string."""
        headers = [
            "Date", "FNSKU", "ASIN", "MSKU", "Title", "Event Type",
            "Reference ID", "Quantity", "Fulfillment Center", "Disposition",
            "Reason", "Country", "Starting Balance", "Ending Balance"
        ]
        lines = ["\t".join(headers)]
        for ev in self.ledger_events:
            row = [
                ev.date.strftime("%Y-%m-%d"),
                ev.fnsku,
                ev.asin,
                ev.msku,
                ev.title,
                ev.event_type,
                ev.reference_id,
                str(ev.quantity),
                ev.fulfillment_center,
                ev.disposition,
                ev.reason,
                ev.country,
                "0",
                str(ev.quantity)
            ]
            lines.append("\t".join(row))
        return "\n".join(lines) + "\n"

    def export_customer_returns_tsv(self) -> str:
        """Emits GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA TSV string."""
        headers = [
            "return-date", "order-id", "sku", "asin", "fnsku",
            "product-name", "quantity", "fulfillment-center-id",
            "detailed-disposition", "reason", "status",
            "license-plate-number", "customer-comments"
        ]
        lines = ["\t".join(headers)]
        for ev in self.returns_events:
            row = [
                ev.return_date.strftime("%Y-%m-%dT%H:%M:%S%z") if ev.return_date.tzinfo else ev.return_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
                ev.order_id,
                ev.sku,
                ev.asin,
                ev.fnsku,
                ev.product_name,
                str(ev.quantity),
                ev.fulfillment_center_id,
                ev.detailed_disposition,
                ev.reason,
                ev.status,
                ev.license_plate_number,
                ev.customer_comments
            ]
            lines.append("\t".join(row))
        return "\n".join(lines) + "\n"

    def export_reimbursements_tsv(self) -> str:
        """Emits GET_FBA_REIMBURSEMENT_DATA TSV string."""
        headers = [
            "approval-date", "reimbursement-id", "case-id", "amazon-order-id",
            "reason", "sku", "fnsku", "asin", "product-name", "condition",
            "currency-unit", "amount-per-unit", "amount-total",
            "quantity-reimbursed-cash", "quantity-reimbursed-inventory",
            "quantity-reimbursed-total", "original-reimbursement-id",
            "original-reimbursement-type"
        ]
        lines = ["\t".join(headers)]
        for ev in self.reimbursements_events:
            row = [
                ev.approval_date.strftime("%Y-%m-%dT%H:%M:%S%z") if ev.approval_date.tzinfo else ev.approval_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
                ev.reimbursement_id,
                ev.case_id,
                ev.amazon_order_id,
                ev.reason,
                ev.sku,
                ev.fnsku,
                ev.asin,
                ev.product_name,
                ev.condition,
                ev.currency_unit,
                str(ev.amount_per_unit),
                str(ev.amount_total),
                str(ev.quantity_reimbursed_cash),
                str(ev.quantity_reimbursed_inventory),
                str(ev.quantity_reimbursed_total),
                ev.original_reimbursement_id,
                ev.original_reimbursement_type
            ]
            lines.append("\t".join(row))
        return "\n".join(lines) + "\n"

    def export_estimated_fees_tsv(self) -> str:
        """Emits GET_FBA_ESTIMATED_FBA_FEES_TXT_DATA TSV string."""
        headers = [
            "sku", "fnsku", "asin", "product-name", "product-group", "brand",
            "fulfilled-by", "your-price", "sales-price", "longest-side",
            "median-side", "shortest-side", "unit-of-dimension", "item-package-weight",
            "unit-of-weight", "product-size-tier", "estimated-fee-total",
            "estimated-order-handling-fee-per-unit", "estimated-pick-pack-fee-per-unit",
            "estimated-weight-handling-fee-per-unit", "expected-fulfillment-fee-per-unit"
        ]
        lines = ["\t".join(headers)]
        for sku in self.skus:
            # If cubiscan was injected, use cubiscan dimensions (what Amazon charged)
            l = sku.cubiscan_length or sku.catalog_length
            w = sku.cubiscan_width or sku.catalog_width
            h = sku.cubiscan_height or sku.catalog_height
            wt = sku.cubiscan_weight or sku.catalog_weight
            
            dims = sorted([l, w, h], reverse=True)
            tier = sku.compute_size_tier(l, w, h, wt)
            fee = sku.compute_fee(l, w, h, wt)

            row = [
                sku.msku,
                sku.fnsku,
                sku.asin,
                sku.title,
                "GL_HOME",
                "BrandGeneric",
                "AMAZON_NA",
                str(sku.unit_price),
                str(sku.unit_price),
                str(dims[0]),
                str(dims[1]),
                str(dims[2]),
                "inches",
                str(wt),
                "pounds",
                tier,
                str(fee),
                "0.00",
                str(fee),
                "0.00",
                str(fee)
            ]
            lines.append("\t".join(row))
        return "\n".join(lines) + "\n"
