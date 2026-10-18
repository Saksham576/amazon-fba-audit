"""
Command-Line Interface for the Amazon FBA audit engine.
"""

import argparse
from datetime import datetime
from pathlib import Path
import sys

from .api import run_audit


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="fba_audit",
        description="Deterministic Amazon FBA Inventory Discrepancy & Reimbursement Audit Engine",
    )
    parser.add_argument("--ledger", type=str, help="Path to GET_LEDGER_DETAIL_VIEW_DATA TSV report")
    parser.add_argument("--returns", type=str, help="Path to GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA TSV report")
    parser.add_argument("--reimbursements", type=str, help="Path to GET_FBA_REIMBURSEMENT_DATA TSV report")
    parser.add_argument("--fees", type=str, help="Path to GET_FBA_ESTIMATED_FBA_FEES_TXT_DATA TSV report")
    parser.add_argument("--as-of-date", type=str, help="Audit evaluation date (YYYY-MM-DD)")
    parser.add_argument("--output-dir", type=str, default="./audit_output", help="Directory to output reports")

    args = parser.parse_args()

    as_of = None
    if args.as_of_date:
        as_of = datetime.strptime(args.as_of_date, "%Y-%m-%d").date()

    if not (args.ledger or args.returns or args.reimbursements or args.fees):
        print("Error: At least one SP-API report file must be provided.", file=sys.stderr)
        parser.print_help(sys.stderr)
        return 1

    print(f"Running Amazon FBA Audit...")
    result = run_audit(
        ledger_path=args.ledger,
        returns_path=args.returns,
        reimbursements_path=args.reimbursements,
        fees_path=args.fees,
        as_of_date=as_of,
        output_dir=args.output_dir,
    )

    s = result.summary
    print("\n--- Audit Summary ---")
    print(f"Total Discrepancies: ${s.total_claim_amount:,.2f} ({s.total_discrepancy_units:,} units across {s.total_claims_count} claims)")
    print(f"Actionable Eligible: ${s.eligible_claim_amount:,.2f} ({s.total_eligible_count} claims)")
    print(f"Expired / Forfeited: ${s.expired_claim_amount:,.2f} ({s.total_expired_count} claims)")
    print(f"Deliverables written to: {Path(args.output_dir).resolve()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
