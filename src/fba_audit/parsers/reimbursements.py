"""Parser for SP-API GET_FBA_REIMBURSEMENT_DATA reports.

Parses reimbursement flat files into immutable ReimbursementRecord instances.
"""

import csv
from decimal import Decimal
import io
from pathlib import Path
from typing import List, TextIO, Union

from fba_audit.models.reports import ReimbursementRecord
from fba_audit.parsers.base import (
    RowParsingError,
    detect_delimiter,
    normalize_headers,
    parse_decimal,
    parse_int,
    parse_iso_datetime,
    parse_str,
    read_content_string,
    validate_mandatory_headers,
)


def parse_reimbursements_report(source: Union[str, Path, TextIO, io.TextIOBase]) -> List[ReimbursementRecord]:
    """Parse GET_FBA_REIMBURSEMENT_DATA report.

    Returns:
        List of immutable ReimbursementRecord objects.
    """
    content = read_content_string(source)
    if not content.strip():
        return []

    lines = content.splitlines()
    header_idx = -1
    for idx, line in enumerate(lines):
        if line.strip():
            header_idx = idx
            break

    if header_idx == -1:
        return []

    first_line = lines[header_idx]
    delimiter = detect_delimiter(first_line)

    reader = csv.reader(lines[header_idx:], delimiter=delimiter)
    try:
        raw_headers = next(reader)
    except StopIteration:
        return []

    headers = normalize_headers(raw_headers)
    validate_mandatory_headers(headers, {"fnsku", "reimbursement_id"}, report_name="Reimbursements Report")

    records: List[ReimbursementRecord] = []
    line_number = header_idx + 1

    for row in reader:
        line_number += 1
        if not row or not any(cell.strip() for cell in row):
            continue

        if len(row) < len(headers):
            row = row + [""] * (len(headers) - len(row))

        row_dict = {headers[i]: row[i].strip() for i in range(len(headers))}

        dt_val = row_dict.get("approval_date")
        if not dt_val:
            raise RowParsingError("Missing approval date", line_number, "approval_date", dt_val)
        approval_dt = parse_iso_datetime(dt_val, line_number, "approval_date")

        reimb_id = parse_str(row_dict.get("reimbursement_id"), line_number, "reimbursement_id", allow_none=False)
        case_id = parse_str(row_dict.get("case_id"), line_number, "case_id", allow_none=True)
        order_id = parse_str(row_dict.get("amazon_order_id"), line_number, "amazon_order_id", allow_none=True)
        reason = parse_str(row_dict.get("reason"), line_number, "reason", allow_none=True) or ""
        sku = parse_str(row_dict.get("sku"), line_number, "sku", allow_none=True) or ""
        fnsku = parse_str(row_dict.get("fnsku"), line_number, "fnsku", allow_none=False)
        asin = parse_str(row_dict.get("asin"), line_number, "asin", allow_none=True) or ""
        pname = parse_str(row_dict.get("product_name"), line_number, "product_name", allow_none=True)
        condition = parse_str(row_dict.get("condition"), line_number, "condition", allow_none=True)
        currency = parse_str(row_dict.get("currency"), line_number, "currency", allow_none=True) or "USD"

        amt_unit = parse_decimal(row_dict.get("amount_per_unit"), line_number, "amount_per_unit", allow_none=True, default=Decimal("0.00"))
        amt_tot = parse_decimal(row_dict.get("amount_total"), line_number, "amount_total", allow_none=True, default=Decimal("0.00"))

        qty_cash = parse_int(row_dict.get("quantity_reimbursed_cash"), line_number, "quantity_reimbursed_cash", allow_none=True, default=0)
        qty_inv = parse_int(row_dict.get("quantity_reimbursed_inventory"), line_number, "quantity_reimbursed_inventory", allow_none=True, default=0)
        qty_tot = parse_int(
            row_dict.get("quantity_reimbursed_total"),
            line_number,
            "quantity_reimbursed_total",
            allow_none=True,
            default=(qty_cash + qty_inv),
        )

        record = ReimbursementRecord(
            approval_date=approval_dt,
            reimbursement_id=reimb_id,
            case_id=case_id,
            amazon_order_id=order_id,
            reason=reason,
            sku=sku,
            fnsku=fnsku,
            asin=asin,
            product_name=pname,
            condition=condition,
            currency=currency,
            amount_per_unit=amt_unit,
            amount_total=amt_tot,
            quantity_reimbursed_cash=qty_cash,
            quantity_reimbursed_inventory=qty_inv,
            quantity_reimbursed_total=qty_tot,
        )
        records.append(record)

    return records
