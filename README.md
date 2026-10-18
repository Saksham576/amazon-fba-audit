# Amazon FBA Inventory Discrepancy & Reimbursement Audit Engine

An offline-first, deterministic Python engine designed to parse official Amazon Selling Partner API (SP-API v2021-06-30) report data, execute mathematical crosswalks against Amazon Seller Central reimbursement policies, and generate audit-ready dispute deliverables.

## Key Features

1. **Authoritative SP-API Ingestion**:
   - `GET_LEDGER_DETAIL_VIEW_DATA` (Inventory Ledger Detail Report)
   - `GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA` (FBA Customer Returns Report)
   - `GET_FBA_REIMBURSEMENT_DATA` (FBA Reimbursements Report)
   - `GET_FBA_ESTIMATED_FBA_FEES_TXT_DATA` (FBA Estimated Fees & Dimension Catalog)

2. **Deterministic Zero-Float Precision**:
   - Uses `decimal.Decimal` with explicit rounding modes (`ROUND_HALF_UP`) for all financial amounts and physical measurements.
   - Eliminates IEEE-754 binary floating-point inaccuracy.

3. **Deterministic RFC 4122 UUID5 Claims**:
   - Idempotent claim generation across composite keys (`fba-audit:{fnsku}:{identifier}:{discrepancy_type}:{event_date}`).
   - Guaranteed identical claim IDs across repeated audit runs.

4. **Amazon Seller Central Policy Citations**:
   - Master policy registry encoding `POL-FBA-OPS` (G200213130 / G200379860), `POL-FBA-RET` (G200213130), `POL-FBA-INB` (G200453320), and `POL-FBA-DIM` (G21213).
   - Strict temporal claim validity evaluation (60-day filing limits, 45-day return holds, expiration dates).

5. **Multi-Format Deliverables**:
   - 19-column CSV claim batch ready for direct submission to Seller Central.
   - Draft-2020-12 structured JSON export.
   - Executive Audit Dossiers in Markdown and standalone, self-contained HTML.

## Installation

```bash
uv pip install -e .
# Or with dev dependencies:
uv pip install -e ".[dev]"
```

## Running the Unit Tests

```bash
uv run pytest tests/unit/ -v
```
