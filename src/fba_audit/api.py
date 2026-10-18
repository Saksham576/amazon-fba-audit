"""
High-level programmatic API for the Amazon FBA audit engine.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .engine import AuditEngine
from .models import AuditResult
from .parsers import (
    parse_customer_returns_report,
    parse_estimated_fees_report,
    parse_ledger_report,
    parse_reimbursements_report,
)
from .reports import (
    export_claim_batch_csv,
    export_claim_batch_json,
    generate_html_dossier,
    generate_markdown_dossier,
)


def run_audit(
    ledger_path: Optional[Union[str, Path]] = None,
    returns_path: Optional[Union[str, Path]] = None,
    reimbursements_path: Optional[Union[str, Path]] = None,
    fees_path: Optional[Union[str, Path]] = None,
    as_of_date: Optional[date] = None,
    output_dir: Optional[Union[str, Path]] = None,
    sku_prices: Optional[Dict[str, Decimal]] = None,
    catalog_specs: Optional[Dict[str, Dict[str, Any]]] = None,
    units_sold_map: Optional[Dict[str, int]] = None,
) -> AuditResult:
    """
    Parses provided SP-API report files, reconciles discrepancies against Amazon policies,
    and optionally writes CSV, JSON, Markdown, and HTML deliverables to output_dir.
    """
    ledger_records = parse_ledger_report(ledger_path) if ledger_path else []
    returns_records = parse_customer_returns_report(returns_path) if returns_path else []
    reimb_records = parse_reimbursements_report(reimbursements_path) if reimbursements_path else []
    fee_records = parse_estimated_fees_report(fees_path) if fees_path else []

    # If sku_prices is not provided, populate prices from fee_records
    if not sku_prices and fee_records:
        sku_prices = {}
        for fr in fee_records:
            if fr.your_price > 0:
                sku_prices[fr.fnsku] = fr.your_price

    engine = AuditEngine(as_of_date=as_of_date)
    result = engine.reconcile(
        ledger_records=ledger_records,
        returns_records=returns_records,
        reimbursement_records=reimb_records,
        fee_records=fee_records,
        sku_prices=sku_prices,
        catalog_specs=catalog_specs,
        units_sold_map=units_sold_map,
    )

    if output_dir:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        export_claim_batch_csv(result.claims, out / "claims_batch.csv")
        export_claim_batch_json(result, out / "claims_batch.json")
        generate_markdown_dossier(result, out / "audit_dossier.md")
        generate_html_dossier(result, out / "audit_dossier.html")

    return result
