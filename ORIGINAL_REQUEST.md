# Original User Request

## 2026-10-18T06:26:18Z

An offline-first, deterministic Amazon FBA inventory discrepancy reconciliation and reimbursement audit engine that parses authoritative Selling Partner API (SP-API) report schemas, calculates exact verified unit/fee discrepancies against official Amazon FBA Reimbursement Policies with cited documentation sources, and generates audit-ready claim dossiers.

Working directory: C:\Users\saksh\teamwork_projects\amazon_fba_audit
Integrity mode: development

## Requirements

### R1. Authoritative SP-API Report Fixtures & Ingestion Parsers
Implement high-fidelity parsers and synthetic test fixtures adhering strictly to official Amazon Selling Partner API (SP-API) v2021-06-30 report specifications:
- `GET_LEDGER_DETAIL_VIEW_DATA` (daily inventory movement, lost, damaged, destroyed, disposed, found event codes).
- `GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA` (order ID, return date, customer return disposition, FC receipt status).
- `GET_FBA_REIMBURSEMENT_DATA` (reimbursement IDs, reasons, units reimbursed in cash or inventory).
- `GET_FBA_ESTIMATED_FBA_FEES_TXT_DATA` (package dimensions, unit weight, fee tier classifications).

### R2. Deterministic Reconciliation & Policy Citation Engine
Implement the core mathematical crosswalk and policy rule evaluation:
- **Warehouse Lost/Damaged**: `(Lost Units + Damaged Units) - (Found Units + Reimbursed Units + Disposed Units)`.
- **Customer Return Reconciliation**: Flag refunded orders where physical item was not received at an FC within 45–60 days of refund date.
- **Dimensional Overcharges**: Detect products charged under incorrect size/weight tiers against physical catalog specifications.
- **Policy Citation Mapping**: Every identified discrepancy must cite the exact Amazon Seller Central Policy clause (e.g. *Customer return claims policy G200213130*, *Fulfillment center operations claims policy*) and calculate the eligible claim window (60-day limit from event/refund date under 2024–2025 rules).

### R3. Audit Dossier & Dispute Package Generator
Generate exportable, auditable deliverables:
- Itemized CSV/JSON claim batch formatted for direct submission to Amazon Seller Central or SP-API `createCase`.
- Markdown/HTML executive summary dossier detailing total verified discrepancies, unit breakdowns, and evidence tables.

### R4. Automated Verification & Test Suite
Provide comprehensive test coverage using `pytest` verifying:
- Complex synthetic ledger edge cases (partially reimbursed units, units found within 30 days, damaged-by-carrier vs damaged-by-customer).
- Exact mathematical reconciliation with zero floating-point discrepancies or speculative estimations.

## Acceptance Criteria

### Schema & Parser Fidelity
- [ ] Parsers validate and extract all mandatory SP-API fields without schema error across valid TSV/CSV fixtures.

### Discrepancy & Policy Math
- [ ] Reconciler correctly identifies 100% of injected discrepancy types in test ledgers with 0 false positives.
- [ ] Every generated claim record includes: FNSKU/MSKU, Transaction/Order ID, Event Date, Discrepancy Type, Verified Policy Citation, and Claim Expiry Date.

### Deliverable Generation
- [ ] Audit generator outputs a structured CSV claim file and a readable dispute report matching the calculated figures.

### Test Execution
- [ ] Full `pytest` test suite runs and passes cleanly with 100% success rate from the project directory.


## 2026-10-18T07:08:30Z

A server restart briefly paused subagent execution. Please revive the project orchestrator and your child workers, verify current progress in C:\Users\saksh\teamwork_projects\amazon_fba_audit, and resume full-speed execution across all milestones (Milestone M1 parsers, M2 reconciliation engine, M3 dossier generator, and M4 dual-track E2E verification). Do not stop until all acceptance criteria are met and verified.
