"""Parser for SP-API GET_FBA_ESTIMATED_FBA_FEES_TXT_DATA reports.

Parses fee estimates and package dimension records into immutable FeeEstimateRecord instances.
"""

import csv
from decimal import Decimal
import io
from pathlib import Path
from typing import List, TextIO, Union

from fba_audit.models.reports import FeeEstimateRecord
from fba_audit.parsers.base import (
    detect_delimiter,
    normalize_headers,
    parse_decimal,
    parse_str,
    read_content_string,
    validate_mandatory_headers,
)


def parse_estimated_fees_report(source: Union[str, Path, TextIO, io.TextIOBase]) -> List[FeeEstimateRecord]:
    """Parse GET_FBA_ESTIMATED_FBA_FEES_TXT_DATA report.

    Returns:
        List of immutable FeeEstimateRecord objects.
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
    validate_mandatory_headers(headers, {"fnsku", "sku"}, report_name="Estimated Fees Report")

    records: List[FeeEstimateRecord] = []
    line_number = header_idx + 1

    for row in reader:
        line_number += 1
        if not row or not any(cell.strip() for cell in row):
            continue

        if len(row) < len(headers):
            row = row + [""] * (len(headers) - len(row))

        row_dict = {headers[i]: row[i].strip() for i in range(len(headers))}

        sku = parse_str(row_dict.get("sku"), line_number, "sku", allow_none=False)
        fnsku = parse_str(row_dict.get("fnsku"), line_number, "fnsku", allow_none=False)
        asin = parse_str(row_dict.get("asin"), line_number, "asin", allow_none=True) or ""
        store = parse_str(row_dict.get("store"), line_number, "store", allow_none=True) or "Amazon.com"
        product_name = parse_str(row_dict.get("product_name"), line_number, "product_name", allow_none=True)
        product_group = parse_str(row_dict.get("product_group"), line_number, "product_group", allow_none=True)
        brand = parse_str(row_dict.get("brand"), line_number, "brand", allow_none=True)
        fulfilled_by = parse_str(row_dict.get("fulfilled_by"), line_number, "fulfilled_by", allow_none=True) or "Amazon"

        your_price = parse_decimal(row_dict.get("your_price"), line_number, "your_price", allow_none=True, default=Decimal("0.00"))
        sales_price = parse_decimal(row_dict.get("sales_price"), line_number, "sales_price", allow_none=True, default=None)

        # Dimension triplet sorting: ensure longest >= median >= shortest
        d1 = parse_decimal(row_dict.get("longest_side"), line_number, "longest_side", allow_none=True, default=Decimal("0.00")) or Decimal("0.00")
        d2 = parse_decimal(row_dict.get("median_side"), line_number, "median_side", allow_none=True, default=Decimal("0.00")) or Decimal("0.00")
        d3 = parse_decimal(row_dict.get("shortest_side"), line_number, "shortest_side", allow_none=True, default=Decimal("0.00")) or Decimal("0.00")
        sorted_dims = sorted([d1, d2, d3], reverse=True)
        longest_side, median_side, shortest_side = sorted_dims[0], sorted_dims[1], sorted_dims[2]

        unit_of_dimension = parse_str(row_dict.get("unit_of_dimension"), line_number, "unit_of_dimension", allow_none=True) or "inches"
        item_package_weight = parse_decimal(row_dict.get("item_package_weight"), line_number, "item_package_weight", allow_none=True, default=Decimal("0.000")) or Decimal("0.000")
        unit_of_weight = parse_str(row_dict.get("unit_of_weight"), line_number, "unit_of_weight", allow_none=True) or "pounds"
        product_size_tier = parse_str(row_dict.get("product_size_tier"), line_number, "product_size_tier", allow_none=True) or ""
        currency = parse_str(row_dict.get("currency"), line_number, "currency", allow_none=True) or "USD"

        estimated_fee_total = parse_decimal(row_dict.get("estimated_fee_total"), line_number, "estimated_fee_total", allow_none=True, default=Decimal("0.00")) or Decimal("0.00")
        estimated_referral_fee = parse_decimal(row_dict.get("estimated_referral_fee"), line_number, "estimated_referral_fee", allow_none=True, default=None)
        estimated_variable_closing_fee = parse_decimal(row_dict.get("estimated_variable_closing_fee"), line_number, "estimated_variable_closing_fee", allow_none=True, default=None)
        expected_fulfillment_fee = parse_decimal(row_dict.get("expected_fulfillment_fee"), line_number, "expected_fulfillment_fee", allow_none=True, default=Decimal("0.00")) or Decimal("0.00")
        estimated_order_handling_fee = parse_decimal(row_dict.get("estimated_order_handling_fee"), line_number, "estimated_order_handling_fee", allow_none=True, default=None)
        estimated_pick_pack_fee = parse_decimal(row_dict.get("estimated_pick_pack_fee"), line_number, "estimated_pick_pack_fee", allow_none=True, default=None)
        estimated_weight_handling_fee = parse_decimal(row_dict.get("estimated_weight_handling_fee"), line_number, "estimated_weight_handling_fee", allow_none=True, default=None)

        record = FeeEstimateRecord(
            sku=sku,
            fnsku=fnsku,
            asin=asin,
            store=store,
            product_name=product_name,
            product_group=product_group,
            brand=brand,
            fulfilled_by=fulfilled_by,
            your_price=your_price,
            sales_price=sales_price,
            longest_side=longest_side,
            median_side=median_side,
            shortest_side=shortest_side,
            unit_of_dimension=unit_of_dimension,
            item_package_weight=item_package_weight,
            unit_of_weight=unit_of_weight,
            product_size_tier=product_size_tier,
            currency=currency,
            estimated_fee_total=estimated_fee_total,
            estimated_referral_fee=estimated_referral_fee,
            estimated_variable_closing_fee=estimated_variable_closing_fee,
            expected_fulfillment_fee=expected_fulfillment_fee,
            estimated_order_handling_fee=estimated_order_handling_fee,
            estimated_pick_pack_fee=estimated_pick_pack_fee,
            estimated_weight_handling_fee=estimated_weight_handling_fee,
        )
        records.append(record)

    return records
