"""Frozen Pydantic Models for Authoritative SP-API Report Records.

Strictly enforces decimal.Decimal on all monetary and dimensional fields,
eliminating floating-point errors across report ingestion and reconciliation.
"""

from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from fba_audit.models.enums import (
    Disposition,
    EventType,
    SizeTier,
)

CENT = Decimal("0.01")
THOUSANDTH = Decimal("0.001")


def coerce_to_decimal(v: Any, precision: Decimal = CENT) -> Decimal:
    """Safely coerce any numeric input (str, int, Decimal) to quantized Decimal."""
    if v is None:
        return Decimal("0.00").quantize(precision)
    if isinstance(v, Decimal):
        return v.quantize(precision, rounding=ROUND_HALF_UP)
    if isinstance(v, (int, str)):
        s = str(v).strip()
        if not s or s.lower() in ("null", "none", "n/a", "-"):
            return Decimal("0.00").quantize(precision)
        # Strip currency symbols and commas
        s = s.replace("$", "").replace("€", "").replace("£", "").replace(",", "")
        return Decimal(s).quantize(precision, rounding=ROUND_HALF_UP)
    if isinstance(v, float):
        return Decimal(f"{v:.4f}").quantize(precision, rounding=ROUND_HALF_UP)
    raise TypeError(f"Cannot coerce value of type {type(v)} to Decimal: {v!r}")


class LedgerDetailRecord(BaseModel):
    """Domain model for GET_LEDGER_DETAIL_VIEW_DATA (Inventory Ledger Detail).

    Itemizes all physical warehouse inventory adjustments, movements,
    receipts, customer returns, and shipments.
    """
    model_config = ConfigDict(frozen=True, extra="ignore", arbitrary_types_allowed=True)

    event_date_time: datetime = Field(
        default_factory=lambda: datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        description="UTC timestamp of the inventory transaction"
    )
    fnsku: str = Field(description="Amazon Fulfillment Network SKU")
    asin: str = Field(default="", description="Amazon Standard Identification Number")
    msku: str = Field(default="", description="Merchant SKU assigned by seller")
    title: Optional[str] = Field(default=None, description="Product catalog title")
    event_type: Union[EventType, str] = Field(
        default=EventType.Adjustments,
        description="Transaction category: Receipts, Shipments, Adjustments, etc."
    )
    reference_id: Optional[str] = Field(
        default=None,
        description="Reference tracking ID: Inbound Shipment ID, Order ID, or Adjustment ID"
    )
    quantity: int = Field(
        default=0,
        description="Net signed unit change (+ for addition, - for reduction)"
    )
    fulfillment_center_id: str = Field(
        default="",
        description="Physical Amazon Fulfillment Center code (e.g. PHX3, DFW6)"
    )
    disposition: Union[Disposition, str] = Field(
        default=Disposition.SELLABLE,
        description="Unit condition: SELLABLE, DEFECTIVE, WAREHOUSE_DAMAGED, etc."
    )
    reason: Optional[str] = Field(
        default=None,
        description="Specific adjustment reason code or description"
    )
    country: str = Field(
        default="US",
        description="Two-letter ISO country code of FC location"
    )
    reconciled_quantity: Optional[int] = Field(
        default=0,
        description="Units matched and resolved internally by Amazon"
    )
    unreconciled_quantity: Optional[int] = Field(
        default=0,
        description="Units remaining unmatched/unresolved by Amazon"
    )

    @model_validator(mode="before")
    @classmethod
    def handle_compat_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Support 'date' argument
            if "event_date_time" not in data and "date" in data:
                d = data["date"]
                if isinstance(d, datetime):
                    data["event_date_time"] = d if d.tzinfo else d.replace(tzinfo=timezone.utc)
                elif isinstance(d, date):
                    data["event_date_time"] = datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc)
            # Support 'fulfillment_center' argument
            if "fulfillment_center_id" not in data and "fulfillment_center" in data:
                data["fulfillment_center_id"] = data["fulfillment_center"]
        return data

    @field_validator("disposition", mode="before")
    @classmethod
    def normalize_disposition(cls, v: Any) -> str:
        if isinstance(v, str):
            return v.strip().upper()
        return str(v)

    @property
    def date(self) -> date:
        """Compatibility property returning date of event_date_time."""
        if isinstance(self.event_date_time, datetime):
            return self.event_date_time.date()
        return self.event_date_time

    @property
    def fulfillment_center(self) -> str:
        """Compatibility property returning fulfillment_center_id."""
        return self.fulfillment_center_id


class CustomerReturnRecord(BaseModel):
    """Domain model for GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA.

    Itemizes customer returns processed at Amazon FCs, tracking inspection
    disposition condition, return reasons, and physical check-in status.
    """
    model_config = ConfigDict(frozen=True, extra="ignore", arbitrary_types_allowed=True)

    return_date: datetime = Field(
        description="Date and time return was processed at FC"
    )
    amazon_order_id: str = Field(
        default="",
        description="Amazon Order ID"
    )
    sku: str = Field(default="", description="Merchant SKU")
    asin: str = Field(default="", description="Amazon ASIN")
    fnsku: str = Field(description="Fulfillment Network SKU")
    product_name: Optional[str] = Field(default=None, description="Product title")
    quantity: int = Field(default=1, description="Quantity returned")
    fulfillment_center_id: str = Field(default="", description="FC where unit was received")
    detailed_disposition: Union[Disposition, str] = Field(
        default=Disposition.SELLABLE,
        description="Inspected condition: SELLABLE, CUSTOMER_DAMAGED, CARRIER_DAMAGED, etc."
    )
    reason: str = Field(default="", description="Return reason selected by customer")
    status: Optional[str] = Field(
        default=None,
        description="Processing status: Unit returned to inventory, Reimbursed, Disposed"
    )
    license_plate_number: Optional[str] = Field(
        default=None,
        description="LPN barcode tracking number affixed to returned unit"
    )
    customer_comments: Optional[str] = Field(
        default=None,
        description="Free-form customer feedback comments"
    )

    @model_validator(mode="before")
    @classmethod
    def handle_compat_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Support 'order_id' as alias for amazon_order_id
            if not data.get("amazon_order_id") and data.get("order_id"):
                data["amazon_order_id"] = data["order_id"]
            # Convert return_date date to datetime if necessary
            if "return_date" in data:
                rd = data["return_date"]
                if isinstance(rd, date) and not isinstance(rd, datetime):
                    data["return_date"] = datetime.combine(rd, datetime.min.time(), tzinfo=timezone.utc)
        return data

    @field_validator("detailed_disposition", mode="before")
    @classmethod
    def normalize_disposition(cls, v: Any) -> str:
        if isinstance(v, str):
            return v.strip().upper()
        return str(v)

    @property
    def order_id(self) -> str:
        """Compatibility property returning amazon_order_id."""
        return self.amazon_order_id


class ReimbursementRecord(BaseModel):
    """Domain model for GET_FBA_REIMBURSEMENT_DATA.

    Itemizes all historical cash credits and inventory replacements issued
    by Amazon for lost, damaged, destroyed, or unreturned merchandise.
    """
    model_config = ConfigDict(frozen=True, extra="ignore", arbitrary_types_allowed=True)

    approval_date: datetime = Field(
        description="Timestamp reimbursement was approved"
    )
    reimbursement_id: str = Field(
        description="Amazon unique reimbursement transaction ID"
    )
    case_id: Optional[str] = Field(
        default=None,
        description="Seller Central support case ID if manually claimed"
    )
    amazon_order_id: Optional[str] = Field(
        default=None,
        description="Associated Amazon Order ID for customer return reimbursements"
    )
    reason: str = Field(
        default="",
        description="Amazon reimbursement reason (e.g. Lost: Warehouse, Damaged: Warehouse)"
    )
    sku: str = Field(default="", description="Merchant SKU")
    fnsku: str = Field(description="Fulfillment Network SKU")
    asin: str = Field(default="", description="Amazon ASIN")
    product_name: Optional[str] = Field(default=None, description="Product title")
    condition: Optional[str] = Field(default=None, description="Product condition")
    currency: str = Field(default="USD", description="ISO currency code")
    amount_per_unit: Decimal = Field(
        default=Decimal("0.00"),
        description="Monetary compensation per unit in Decimal currency"
    )
    amount_total: Decimal = Field(
        default=Decimal("0.00"),
        description="Total cash reimbursed for transaction in Decimal currency"
    )
    quantity_reimbursed_cash: int = Field(
        default=0,
        description="Units compensated via direct account cash balance credit"
    )
    quantity_reimbursed_inventory: int = Field(
        default=0,
        description="Units compensated via physical inventory stock replacement"
    )
    quantity_reimbursed_total: int = Field(
        default=0,
        description="Sum of cash and inventory reimbursed units"
    )
    original_reimbursement_id: Optional[str] = Field(
        default="",
        description="Original transaction ID if clawback/adjustment"
    )
    original_reimbursement_type: Optional[str] = Field(
        default="",
        description="Original type code"
    )

    @model_validator(mode="before")
    @classmethod
    def handle_compat_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "currency_unit" in data and "currency" not in data:
                data["currency"] = data["currency_unit"]
        return data

    @field_validator("amount_per_unit", "amount_total", mode="before")
    @classmethod
    def validate_decimal_amounts(cls, v: Any) -> Decimal:
        return coerce_to_decimal(v, precision=CENT)

    @model_validator(mode="after")
    def verify_reimbursement_totals(self) -> "ReimbursementRecord":
        computed_total = self.quantity_reimbursed_cash + self.quantity_reimbursed_inventory
        if self.quantity_reimbursed_total != computed_total:
            if self.quantity_reimbursed_total == 0:
                object.__setattr__(self, "quantity_reimbursed_total", computed_total)
            elif computed_total != 0:
                raise ValueError(
                    f"Reimbursement quantity total mismatch: total={self.quantity_reimbursed_total} "
                    f"!= cash({self.quantity_reimbursed_cash}) + inv({self.quantity_reimbursed_inventory})"
                )
        return self

    @property
    def currency_unit(self) -> str:
        """Compatibility property returning currency."""
        return self.currency


class FeeEstimateRecord(BaseModel):
    """Domain model for GET_FBA_ESTIMATED_FBA_FEES_TXT_DATA.

    Contains catalog dimensions, physical packaged weights, product size tier,
    and estimated itemized FBA fulfillment fee schedules.
    """
    model_config = ConfigDict(frozen=True, extra="ignore", arbitrary_types_allowed=True)

    sku: str = Field(description="Merchant SKU")
    fnsku: str = Field(description="Fulfillment Network SKU")
    asin: str = Field(default="", description="Amazon Standard Identification Number")
    store: Optional[str] = Field(default="Amazon.com", description="Marketplace store")
    product_name: Optional[str] = Field(default=None, description="Catalog title")
    product_group: Optional[str] = Field(default=None, description="Category / GL group")
    brand: Optional[str] = Field(default=None, description="Brand name")
    fulfilled_by: str = Field(default="Amazon", description="Fulfillment channel (Amazon/AFN)")
    your_price: Decimal = Field(default=Decimal("0.00"), description="Listing price in Decimal currency")
    sales_price: Optional[Decimal] = Field(default=None, description="Promotional price")
    longest_side: Decimal = Field(default=Decimal("0.00"), description="Package longest side in Decimal units")
    median_side: Decimal = Field(default=Decimal("0.00"), description="Package intermediate side in Decimal units")
    shortest_side: Decimal = Field(default=Decimal("0.00"), description="Package shortest side in Decimal units")
    unit_of_dimension: str = Field(default="inches", description="Measurement unit (inches/cm)")
    item_package_weight: Decimal = Field(default=Decimal("0.000"), description="Measured package weight in Decimal units")
    unit_of_weight: str = Field(default="pounds", description="Weight unit (pounds/ounces/kg)")
    product_size_tier: Union[SizeTier, str] = Field(
        default="",
        description="Assigned product size tier (Small Standard, Large Standard, etc.)"
    )
    currency: str = Field(default="USD", description="Currency code (USD)")
    estimated_fee_total: Decimal = Field(default=Decimal("0.00"), description="Total estimated FBA fees per unit")
    estimated_referral_fee: Optional[Decimal] = Field(default=None)
    estimated_variable_closing_fee: Optional[Decimal] = Field(default=None)
    expected_fulfillment_fee: Decimal = Field(default=Decimal("0.00"), description="Core FBA pick/pack/ship fulfillment fee")
    estimated_order_handling_fee: Optional[Decimal] = Field(default=None)
    estimated_pick_pack_fee: Optional[Decimal] = Field(default=None)
    estimated_weight_handling_fee: Optional[Decimal] = Field(default=None)

    @model_validator(mode="before")
    @classmethod
    def handle_compat_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "expected_fulfillment_fee_per_unit" in data and "expected_fulfillment_fee" not in data:
                data["expected_fulfillment_fee"] = data["expected_fulfillment_fee_per_unit"]
            if "estimated_order_handling_fee_per_unit" in data and "estimated_order_handling_fee" not in data:
                data["estimated_order_handling_fee"] = data["estimated_order_handling_fee_per_unit"]
            if "estimated_pick_pack_fee_per_unit" in data and "estimated_pick_pack_fee" not in data:
                data["estimated_pick_pack_fee"] = data["estimated_pick_pack_fee_per_unit"]
            if "estimated_weight_handling_fee_per_unit" in data and "estimated_weight_handling_fee" not in data:
                data["estimated_weight_handling_fee"] = data["estimated_weight_handling_fee_per_unit"]
        return data

    @field_validator(
        "your_price",
        "sales_price",
        "longest_side",
        "median_side",
        "shortest_side",
        "estimated_fee_total",
        "estimated_referral_fee",
        "estimated_variable_closing_fee",
        "expected_fulfillment_fee",
        "estimated_order_handling_fee",
        "estimated_pick_pack_fee",
        "estimated_weight_handling_fee",
        mode="before"
    )
    @classmethod
    def validate_decimals_2dp(cls, v: Any) -> Optional[Decimal]:
        if v is None:
            return None
        return coerce_to_decimal(v, precision=CENT)

    @field_validator("item_package_weight", mode="before")
    @classmethod
    def validate_weight_3dp(cls, v: Any) -> Decimal:
        return coerce_to_decimal(v, precision=THOUSANDTH)

    @property
    def expected_fulfillment_fee_per_unit(self) -> Decimal:
        return self.expected_fulfillment_fee

    @property
    def estimated_order_handling_fee_per_unit(self) -> Decimal:
        return self.estimated_order_handling_fee or Decimal("0.00")

    @property
    def estimated_pick_pack_fee_per_unit(self) -> Decimal:
        return self.estimated_pick_pack_fee or Decimal("0.00")

    @property
    def estimated_weight_handling_fee_per_unit(self) -> Decimal:
        return self.estimated_weight_handling_fee or Decimal("0.00")

    @property
    def girth(self) -> Decimal:
        """Girth = 2 * (median_side + shortest_side)"""
        return (Decimal("2.0") * (self.median_side + self.shortest_side)).quantize(CENT, rounding=ROUND_HALF_UP)

    @property
    def length_and_girth(self) -> Decimal:
        """Length + Girth = longest_side + 2 * (median_side + shortest_side)"""
        return (self.longest_side + self.girth).quantize(CENT, rounding=ROUND_HALF_UP)

    @property
    def dimensional_weight(self) -> Decimal:
        """Dimensional Weight = (L * W * H) / 139"""
        return ((self.longest_side * self.median_side * self.shortest_side) / Decimal("139")).quantize(
            CENT, rounding=ROUND_HALF_UP
        )
