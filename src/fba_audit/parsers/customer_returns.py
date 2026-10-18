"""Parser for SP-API GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA reports.

Parses customer returns flat files into immutable CustomerReturnRecord instances.
"""

import csv
import io
from pathlib import Path
from typing import List, TextIO, Union

from fba_audit.models.reports import CustomerReturnRecord
from fba_audit.parsers.base import (
    RowParsingError,
    detect_delimiter,
    normalize_headers,
    parse_int,
    parse_iso_datetime,
    parse_str,
    read_content_string,
    validate_mandatory_headers,
)


def parse_customer_returns_report(source: Union[str, Path, TextIO, io.TextIOBase]) -> List[CustomerReturnRecord]:
    """Parse GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA report.

    Returns:
        List of immutable CustomerReturnRecord objects.
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
    validate_mandatory_headers(headers, {"fnsku", "amazon_order_id"}, report_name="Customer Returns Report")

    records: List[CustomerReturnRecord] = []
    line_number = header_idx + 1

    for row in reader:
        line_number += 1
        if not row or not any(cell.strip() for cell in row):
            continue

        if len(row) < len(headers):
            row = row + [""] * (len(headers) - len(row))

        row_dict = {headers[i]: row[i].strip() for i in range(len(headers))}

        dt_val = row_dict.get("return_date")
        if not dt_val:
            raise RowParsingError("Missing return date", line_number, "return_date", dt_val)
        ret_date = parse_iso_datetime(dt_val, line_number, "return_date")

        order_id = parse_str(row_dict.get("amazon_order_id"), line_number, "amazon_order_id", allow_none=False)
        sku = parse_str(row_dict.get("sku"), line_number, "sku", allow_none=True) or ""
        asin = parse_str(row_dict.get("asin"), line_number, "asin", allow_none=True) or ""
        fnsku = parse_str(row_dict.get("fnsku"), line_number, "fnsku", allow_none=False)
        pname = parse_str(row_dict.get("product_name"), line_number, "product_name", allow_none=True)
        qty = parse_int(row_dict.get("quantity"), line_number, "quantity", allow_none=True, default=1)
        fc = parse_str(row_dict.get("fulfillment_center_id"), line_number, "fulfillment_center_id", allow_none=True) or ""
        disp = parse_str(row_dict.get("detailed_disposition"), line_number, "detailed_disposition", allow_none=True) or "SELLABLE"
        reason = parse_str(row_dict.get("reason"), line_number, "reason", allow_none=True) or ""
        status = parse_str(row_dict.get("status"), line_number, "status", allow_none=True)
        lpn = parse_str(row_dict.get("license_plate_number"), line_number, "license_plate_number", allow_none=True)
        comments = parse_str(row_dict.get("customer_comments"), line_number, "customer_comments", allow_none=True)

        record = CustomerReturnRecord(
            return_date=ret_date,
            amazon_order_id=order_id,
            sku=sku,
            asin=asin,
            fnsku=fnsku,
            product_name=pname,
            quantity=qty,
            fulfillment_center_id=fc,
            detailed_disposition=disp,
            reason=reason,
            status=status,
            license_plate_number=lpn,
            customer_comments=comments,
        )
        records.append(record)

    return records
