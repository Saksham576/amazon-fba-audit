"""Universal parsing engine and utilities for SP-API reports.

Provides dialect sniffing, header normalization, resilient date parsing,
strict Decimal coercion, string sanitization, and structured ParserError hierarchy.
"""

from contextlib import contextmanager
import csv
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import io
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Set, TextIO, Tuple, Union

# ---------------------------------------------------------------------------
# Exception Hierarchy
# ---------------------------------------------------------------------------

class ParserError(Exception):
    """Base exception for all parser failures in fba_audit.parsers."""
    pass


class SchemaValidationError(ParserError):
    """Raised when flat file headers are malformed or missing mandatory columns."""
    def __init__(
        self,
        message: str,
        missing_columns: Optional[List[str]] = None,
        found_columns: Optional[List[str]] = None
    ):
        super().__init__(message)
        self.missing_columns = missing_columns or []
        self.found_columns = found_columns or []


class RowParsingError(ParserError):
    """Raised when a specific data row fails type conversion or validation."""
    def __init__(
        self,
        message: str,
        line_number: int,
        field_name: Optional[str] = None,
        raw_value: Any = None
    ):
        super().__init__(f"Line {line_number}: {message} (field='{field_name}', raw='{raw_value}')")
        self.line_number = line_number
        self.field_name = field_name
        self.raw_value = raw_value


class EmptyFileError(ParserError):
    """Raised when a report file is completely empty or contains only whitespace."""
    pass


# ---------------------------------------------------------------------------
# Master Header Normalization Map
# ---------------------------------------------------------------------------

MASTER_HEADER_ALIAS_MAP: Dict[str, str] = {
    # Common & Identifiers
    "order_id": "amazon_order_id",
    "amazon_order_id": "amazon_order_id",
    "fnsku": "fnsku",
    "asin": "asin",
    "msku": "msku",
    "sku": "sku",
    "title": "title",
    "product_name": "product_name",
    "fulfillment_center": "fulfillment_center_id",
    "fulfillment_center_id": "fulfillment_center_id",
    "country": "country",
    "store": "store",
    "amazon_store": "store",
    "currency_unit": "currency",
    "currency": "currency",

    # Ledger Report Specific
    "date_and_time": "event_date_time",
    "event_date_time": "event_date_time",
    "date_time": "event_date_time",
    "date": "event_date_time",
    "event_type": "event_type",
    "reference_id": "reference_id",
    "quantity": "quantity",
    "disposition": "disposition",
    "reason": "reason",
    "reconciled_quantity": "reconciled_quantity",
    "unreconciled_quantity": "unreconciled_quantity",

    # Customer Returns Specific
    "return_date": "return_date",
    "detailed_disposition": "detailed_disposition",
    "status": "status",
    "license_plate_number": "license_plate_number",
    "customer_comments": "customer_comments",

    # Reimbursements Specific
    "approval_date": "approval_date",
    "reimbursement_id": "reimbursement_id",
    "case_id": "case_id",
    "condition": "condition",
    "amount_per_unit": "amount_per_unit",
    "amount_total": "amount_total",
    "quantity_reimbursed_cash": "quantity_reimbursed_cash",
    "quantity_reimbursed_inventory": "quantity_reimbursed_inventory",
    "quantity_reimbursed_total": "quantity_reimbursed_total",
    "original_reimbursement_id": "original_reimbursement_id",
    "original_reimbursement_type": "original_reimbursement_type",

    # Fee Preview Specific
    "product_group": "product_group",
    "brand": "brand",
    "fulfilled_by": "fulfilled_by",
    "your_price": "your_price",
    "sales_price": "sales_price",
    "longest_side": "longest_side",
    "median_side": "median_side",
    "shortest_side": "shortest_side",
    "unit_of_dimension": "unit_of_dimension",
    "item_package_weight": "item_package_weight",
    "unit_of_weight": "unit_of_weight",
    "product_size_tier": "product_size_tier",
    "estimated_fee_total": "estimated_fee_total",
    "estimated_referral_fee_per_unit": "estimated_referral_fee",
    "estimated_referral_fee": "estimated_referral_fee",
    "estimated_variable_closing_fee": "estimated_variable_closing_fee",
    "expected_fulfillment_fee_per_unit": "expected_fulfillment_fee",
    "expected_fulfillment_fee": "expected_fulfillment_fee",
    "estimated_order_handling_fee_per_unit": "estimated_order_handling_fee",
    "estimated_order_handling_fee": "estimated_order_handling_fee",
    "estimated_pick_pack_fee_per_unit": "estimated_pick_pack_fee",
    "estimated_pick_pack_fee": "estimated_pick_pack_fee",
    "estimated_weight_handling_fee_per_unit": "estimated_weight_handling_fee",
    "estimated_weight_handling_fee": "estimated_weight_handling_fee",
}


def normalize_header(raw_header: str) -> str:
    """Normalize a single column header using alias mapping."""
    clean = raw_header.strip().replace("-", "_").replace(" ", "_").lower()
    return MASTER_HEADER_ALIAS_MAP.get(clean, clean)


def normalize_headers(raw_headers: List[str]) -> List[str]:
    """Normalize a list of raw column headers."""
    return [normalize_header(h) for h in raw_headers]


def validate_mandatory_headers(
    found_headers: List[str],
    mandatory_headers: Set[str],
    report_name: str = "Report"
) -> None:
    """Validate that all mandatory headers are present in normalized headers."""
    found_set = set(found_headers)
    missing = [m for m in mandatory_headers if m not in found_set]
    if missing:
        raise SchemaValidationError(
            f"{report_name} missing mandatory column(s): {', '.join(missing)}. "
            f"Found: {', '.join(found_headers)}",
            missing_columns=missing,
            found_columns=found_headers,
        )


# ---------------------------------------------------------------------------
# Dialect & Source Handling
# ---------------------------------------------------------------------------

def detect_delimiter(first_line: str) -> str:
    """Detect delimiter: prefers tab if tab count >= comma count and tab >= 1."""
    clean_line = first_line.lstrip("\ufeff")
    tabs = clean_line.count("\t")
    commas = clean_line.count(",")
    if tabs >= 1 and tabs >= commas:
        return "\t"
    if commas >= 1:
        return ","
    return "\t"


def read_content_string(source: Union[str, Path, TextIO, io.TextIOBase]) -> str:
    """Read full text content from file path or open text stream, stripping UTF-8 BOM."""
    if isinstance(source, io.TextIOBase) or hasattr(source, "read"):
        content = source.read()
    elif isinstance(source, Path):
        content = source.read_text(encoding="utf-8-sig")
    elif isinstance(source, str):
        p = Path(source)
        if "\n" not in source and p.exists() and p.is_file():
            content = p.read_text(encoding="utf-8-sig")
        else:
            content = source
    else:
        raise ParserError(f"Unsupported source type: {type(source)}")

    if content.startswith("\ufeff"):
        content = content[1:]
    return content


# ---------------------------------------------------------------------------
# Coercion Utilities
# ---------------------------------------------------------------------------

def parse_iso_datetime(value: Any, line_number: int, field_name: str) -> datetime:
    """Resilient date and timestamp parser returning UTC datetime."""
    if value is None or str(value).strip() == "":
        raise RowParsingError("Timestamp field cannot be empty", line_number, field_name, value)

    clean_val = str(value).strip()

    # Fast-path: ISO 8601
    try:
        dt = datetime.fromisoformat(clean_val.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        pass

    # Common legacy formats
    patterns = [
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d",
    ]
    for fmt in patterns:
        try:
            dt = datetime.strptime(clean_val, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    raise RowParsingError(f"Unparseable datetime value: '{clean_val}'", line_number, field_name, value)


def parse_decimal(
    value: Any,
    line_number: int,
    field_name: str,
    allow_none: bool = False,
    default: Optional[Decimal] = None
) -> Optional[Decimal]:
    """Strict zero-float Decimal parser stripping currency symbols and commas."""
    if value is None:
        if allow_none:
            return default
        raise RowParsingError("Mandatory numeric field is null", line_number, field_name, value)

    raw_str = str(value).strip()
    if raw_str == "" or raw_str.lower() in ("null", "none", "n/a", "-"):
        if allow_none:
            return default
        raise RowParsingError("Mandatory numeric field is empty", line_number, field_name, value)

    sanitized = raw_str.replace("$", "").replace("€", "").replace("£", "").replace(",", "")
    try:
        return Decimal(sanitized)
    except InvalidOperation:
        raise RowParsingError(f"Cannot parse '{raw_str}' as Decimal", line_number, field_name, value)


def parse_int(
    value: Any,
    line_number: int,
    field_name: str,
    allow_none: bool = False,
    default: Optional[int] = None
) -> Optional[int]:
    """Strict signed integer parser stripping commas and handling nulls."""
    if value is None:
        if allow_none:
            return default
        raise RowParsingError("Mandatory integer field is null", line_number, field_name, value)

    raw_str = str(value).strip()
    if raw_str == "" or raw_str.lower() in ("null", "none", "n/a"):
        if allow_none:
            return default
        raise RowParsingError("Mandatory integer field is empty", line_number, field_name, value)

    sanitized = raw_str.replace(",", "")
    try:
        return int(sanitized)
    except ValueError:
        raise RowParsingError(f"Cannot parse '{raw_str}' as integer", line_number, field_name, value)


def parse_str(
    value: Any,
    line_number: int,
    field_name: str,
    allow_none: bool = True
) -> Optional[str]:
    """Clean string parser stripping whitespace and converting empty strings to None if optional."""
    if value is None:
        if allow_none:
            return None
        raise RowParsingError("Mandatory string field is null", line_number, field_name, value)

    s = str(value).strip()
    if s == "":
        if allow_none:
            return None
        raise RowParsingError("Mandatory string field is empty", line_number, field_name, value)
    return s
