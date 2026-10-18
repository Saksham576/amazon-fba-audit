"""
Main AuditEngine orchestrator executing all reconciliation modules.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from ..models.claims import AuditResult, AuditSummary, ClaimRecord
from ..models.reports import CustomerReturnRecord, FeeEstimateRecord, LedgerDetailRecord, ReimbursementRecord
from .customer_returns import CustomerReturnReconciler
from .dimensional import DimensionalOverchargeReconciler
from .warehouse import WarehouseReconciler


class AuditEngine:
    """
    Coordinates warehouse, customer return, and dimensional overcharge reconcilers.
    """

    def __init__(self, as_of_date: Optional[date] = None):
        self.as_of_date = as_of_date or date(2026, 9, 29)
        self.warehouse_reconciler = WarehouseReconciler(as_of_date=self.as_of_date)
        self.returns_reconciler = CustomerReturnReconciler(as_of_date=self.as_of_date)
        self.dimensional_reconciler = DimensionalOverchargeReconciler(as_of_date=self.as_of_date)

    def reconcile(
        self,
        ledger_records: Optional[List[LedgerDetailRecord]] = None,
        returns_records: Optional[List[CustomerReturnRecord]] = None,
        reimbursement_records: Optional[List[ReimbursementRecord]] = None,
        fee_records: Optional[List[FeeEstimateRecord]] = None,
        sku_prices: Optional[Dict[str, Decimal]] = None,
        catalog_specs: Optional[Dict[str, Dict[str, Any]]] = None,
        units_sold_map: Optional[Dict[str, int]] = None,
    ) -> AuditResult:
        all_claims: List[ClaimRecord] = []

        if ledger_records:
            wh_claims = self.warehouse_reconciler.reconcile(
                ledger_records=ledger_records,
                reimbursement_records=reimbursement_records,
                sku_prices=sku_prices,
            )
            all_claims.extend(wh_claims)

        if returns_records:
            ret_claims = self.returns_reconciler.reconcile(
                returns_records=returns_records,
                reimbursement_records=reimbursement_records,
                sku_prices=sku_prices,
            )
            all_claims.extend(ret_claims)

        if fee_records:
            dim_claims = self.dimensional_reconciler.reconcile(
                fee_records=fee_records,
                catalog_specs=catalog_specs,
                units_sold_map=units_sold_map,
            )
            all_claims.extend(dim_claims)

        # Sort claims deterministically by event_date, then fnsku
        all_claims.sort(key=lambda c: (c.event_date, c.fnsku, c.claim_id))

        total_amount = sum((c.claim_amount for c in all_claims), Decimal("0.00"))
        total_units = sum(c.quantity for c in all_claims)

        eligible = [c for c in all_claims if c.claim_status == "ELIGIBLE"]
        expired = [c for c in all_claims if c.claim_status == "EXPIRED"]

        eligible_amount = sum((c.claim_amount for c in eligible), Decimal("0.00"))
        expired_amount = sum((c.claim_amount for c in expired), Decimal("0.00"))

        amount_by_type: Dict[str, Decimal] = {}
        units_by_type: Dict[str, int] = {}
        for c in all_claims:
            dt = c.discrepancy_type
            amount_by_type[dt] = amount_by_type.get(dt, Decimal("0.00")) + c.claim_amount
            units_by_type[dt] = units_by_type.get(dt, 0) + c.quantity

        summary = AuditSummary(
            as_of_date=self.as_of_date,
            total_claims_count=len(all_claims),
            total_eligible_count=len(eligible),
            total_expired_count=len(expired),
            total_discrepancy_units=total_units,
            total_claim_amount=total_amount,
            eligible_claim_amount=eligible_amount,
            expired_claim_amount=expired_amount,
            amount_by_discrepancy_type=amount_by_type,
            units_by_discrepancy_type=units_by_type,
        )

        return AuditResult(
            reconciled_at=datetime.now(),
            as_of_date=self.as_of_date,
            claims=all_claims,
            summary=summary,
        )
