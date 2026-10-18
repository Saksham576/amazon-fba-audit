# Amazon SP-API Inbound Reports Directory

Drop raw Amazon Selling Partner API (SP-API) TSV/CSV reports here:
- `ledger*.tsv` -> GET_LEDGER_DETAIL_VIEW_DATA (warehouse inventory movements)
- `returns*.tsv` -> GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA (customer returns)
- `reimbursements*.tsv` -> GET_FBA_REIMBURSEMENT_DATA (Amazon reimbursement receipts)
- `fees*.tsv` -> GET_FBA_ESTIMATED_FBA_FEES_TXT_DATA (package dimensions & fee tiers)

The autonomous daemon monitors this directory, parses new reports,
reconciles discrepancies, generates dispute packages in /audit_output,
and emails payout notices (15% contingency) to virajtiwari52@gmail.com.
