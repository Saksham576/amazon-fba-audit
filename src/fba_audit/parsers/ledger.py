"""Parser for SP-API GET_LEDGER_DETAIL_VIEW_DATA reports.

Parses inventory ledger detail flat files into immutable LedgerDetailRecord instances.
"""

import csv
import io
from pathlib import Path
from typing import List, TextIO, Union

from fba_audit.models.reports import LedgerDetailRecord
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


def parse_ledger_report(source: Union[str, Path, TextIO, io.TextIOBase]) -> List[LedgerDetailRecord]:
    """Parse GET_LEDGER_DETAIL_VIEW_DATA report from file path or open text stream.

    Returns:
        List of immutable LedgerDetailRecord objects.
    """
    content = read_content_string(source)
    if not content.strip():
        return []

    lines = content.splitlines()
    # Find first non-empty line as header
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
    validate_mandatory_headers(headers, {"fnsku"}, report_name="Ledger Detail Report")

    records: List[LedgerDetailRecord] = []
    line_number = header_idx + 1

    for row in reader:
        line_number += 1
        # Skip empty lines
        if not row or not any(cell.strip() for cell in row):
            continue

        # If row has fewer columns than header, pad with empty strings
        if len(row) < len(headers):
            row = row + [""] * (len(headers) - len(row))

        row_dict = {headers[i]: row[i].strip() for i in range(len(headers))}

        # Parse date
        dt_val = row_dict.get("event_date_time")
        if not dt_val:
            raise RowParsingError("Missing event date/time", line_number, "event_date_time", dt_val)
        event_dt = parse_iso_datetime(dt_val, line_number, "event_date_time")

        # Parse identifiers
        fnsku = parse_str(row_dict.get("fnsku"), line_number, "fnsku", allow_none=False)
        asin = parse_str(row_dict.get("asin"), line_number, "asin", allow_none=True) or ""
        msku = parse_str(row_dict.get("msku"), line_number, "msku", allow_none=True) or parse_str(row_dict.get("sku"), line_number, "sku", allow_none=True) or ""
        title = parse_str(row_dict.get("title"), line_number, "title", allow_none=True)
        event_type = parse_str(row_dict.get("event_type"), line_number, "event_type", allow_none=False)
        ref_id = parse_str(row_dict.get("reference_id"), line_number, "reference_id", allow_none=True)

        # Parse numeric & warehouse fields
        qty = parse_int(row_dict.get("quantity"), line_number, "quantity", allow_none=False)
        fc = parse_str(row_dict.get("fulfillment_center_id"), line_number, "fulfillment_center_id", allow_none=True) or ""
        disp = parse_str(row_dict.get("disposition"), line_number, "disposition", allow_none=True) or "SELLABLE"
        reason = parse_str(row_dict.get("reason"), line_number, "reason", allow_none=True)
        country = parse_str(row_dict.get("country"), line_number, "country", allow_none=True) or "US"
        rec_qty = parse_int(row_dict.get("reconciled_quantity"), line_number, "reconciled_quantity", allow_none=True, default=0)
        unrec_qty = parse_int(row_dict.get("unreconciled_quantity"), line_number, "unreconciled_quantity", allow_none=True, default=0)

        record = LedgerDetailRecord(
            event_date_time=event_dt,
            fnsku=fnsku,
            asin=asin,
            msku=msku,
            title=title,
            event_type=event_type,
            reference_id=ref_id,
            quantity=qty,
            fulfillment_center_id=fc,
            disposition=disp,
            reason=reason,
            country=country,
            reconciled_quantity=rec_qty,
            unreconciled_quantity=unrec_qty,
        )
        records.append(record)

    return records
