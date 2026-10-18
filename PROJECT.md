# Project: Amazon FBA Inventory Discrepancy & Reimbursement Audit Engine

## Architecture

The Amazon FBA Inventory Discrepancy & Reimbursement Audit Engine is an offline-first, deterministic Python engine designed to parse official Amazon SP-API report data, execute mathematical crosswalks against Amazon Seller Central reimbursement policies, and generate audit-ready dispute deliverables.

### Architectural Layers
1. **Models Layer (`src/fba_audit/models/`)**:
   - Immutable domain entities defined using `pydantic.BaseModel(frozen=True)` or dataclasses.
   - Strict zero-float representation: all financial amounts, package dimensions, weights, and fee rates use `decimal.Decimal` with explicit rounding modes (`ROUND_HALF_UP` for currency, `ROUND_UP` for weight).
   - Strict enumerations for Discrepancy Types, Event Types, Reason Codes, Dispositions, Policy Identifiers, and Claim Status.

2. **Parsers Layer (`src/fba_audit/parsers/`)**:
   - Deterministic TSV/CSV parsers for all 4 SP-API v2021-06-30 reports:
     - `GET_LEDGER_DETAIL_VIEW_DATA` (Inventory ledger detail view)
     - `GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA` (Customer returns data)
     - `GET_FBA_REIMBURSEMENT_DATA` (Reimbursements report)
     - `GET_FBA_ESTIMATED_FBA_FEES_TXT_DATA` (Estimated FBA fees & dimension catalog)
   - Resilient header alias mapping, datetime normalization, and malformed row validation.

3. **Reconciliation Engine Layer (`src/fba_audit/engine/`)**:
   - `WarehouseReconciler`: Evaluates `(Lost + Damaged) - (Found + Reimbursed + Disposed)` with FIFO event-matching queues.
   - `CustomerReturnReconciler`: Tracks refunded customer orders against FC return receipts, enforcing the 45-day waiting period and calculating the 60-day / 120-day claim eligibility window under Policy `G200213130`.
   - `DimensionalOverchargeReconciler`: Recomputes product size tiers (Small Standard, Large Standard, Oversize tiers), dimensional weight ($L \times W \times H / 139$), and billing weight against catalog specs to isolate overcharge deltas under Policy `G21213`.
   - `PolicyCitationRegistry`: Binds every discrepancy to its authoritative Seller Central Help Hub code, clause text, and claim expiry timestamp relative to the injected `as_of_date`.

4. **Reporting & Deliverables Layer (`src/fba_audit/reports/`)**:
   - Itemized 19-column CSV claim batch generation with deterministic UUID5 `claim_id`.
   - Structured JSON claim batch output conforming to Draft-2020-12 schema.
   - Executive Audit Dossier in Markdown and single-file self-contained HTML (zero external CSS/JS CDNs) featuring KPI cards, summary breakdowns, and audit evidence tables.

5. **Entry Points Layer (`src/fba_audit/cli.py` & `src/fba_audit/api.py`)**:
   - Command-Line Interface (`python -m fba_audit.cli audit ...`) with rich arguments, JSON/CSV/HTML output switches, and custom date injection.
   - Programmatic Python API (`AuditEngine.run_audit(...) -> AuditResult`).

---

## Feature Inventory

Every feature discovered in the Survey Phase is inventoried below with an assigned milestone:

| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Ledger Detail TSV Parser | Parse `GET_LEDGER_DETAIL_VIEW_DATA` with 14 columns, event types, reason codes, FCs | M1 | survey_spec_miner_1 |
| 2 | Customer Returns TSV Parser | Parse `GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA` with 13 columns, dispositions, return status | M1 | survey_spec_miner_1 |
| 3 | Reimbursements TSV Parser | Parse `GET_FBA_REIMBURSEMENT_DATA` with 16 columns, cash/inventory reimbursement units | M1 | survey_spec_miner_1 |
| 4 | Estimated Fees TSV Parser | Parse `GET_FBA_ESTIMATED_FBA_FEES_TXT_DATA` with dimensions, weights, tier classifications | M1 | survey_spec_miner_1 |
| 5 | Synthetic SP-API Fixtures | High-fidelity test fixtures modeling edge cases for all 4 SP-API report types | M1 | survey_spec_miner_1 |
| 6 | Zero-Float Domain Models | Immutable Pydantic models using `decimal.Decimal` and strict Enums | M1 | survey_explorer_2 |
| 7 | Warehouse Lost/Damaged Crosswalk | Mathematical formula `(Lost + Damaged) - (Found + Reimbursed + Disposed)` with FIFO queue | M2 | survey_explorer_1 |
| 8 | Customer Return 45-60 Day Reconciler | Unreturned refund identification, 45-day hold, 60-day claim window evaluation | M2 | survey_explorer_1 |
| 9 | Dimensional Tier & Fee Reconciler | Size tier classification, dimensional weight ($L \times W \times H / 139$), overcharge delta math | M2 | survey_explorer_1 |
| 10 | Policy Citation Registry | Precise citation mapping (G200213130, G200379860, G21213, G200453320) & claim expiry dates | M2 | survey_explorer_1 |
| 11 | Temporal As-Of Date Engine | Injected historical clock for deterministic timeline evaluation and expiration math | M2 | survey_explorer_2 |
| 12 | 19-Column CSV Claim Batch Generator | Direct Seller Central / dispute submission CSV with UUID5 deterministic IDs | M3 | survey_explorer_2 |
| 13 | JSON Claim Batch Exporter | Draft-2020-12 compliant JSON export for machine ingestion | M3 | survey_explorer_2 |
| 14 | Markdown Executive Dossier | Comprehensive executive audit report with KPI summary and evidence tables | M3 | survey_explorer_2 |
| 15 | Standalone HTML Executive Dossier | Self-contained single-file HTML audit dossier (zero external CDN dependencies) | M3 | survey_explorer_2 |
| 16 | CLI & Programmatic API Entry Points | `fba_audit.cli` and `fba_audit.api` interfaces for offline execution | M3 | survey_explorer_2 |
| 17 | E2E Testing Suite (Tiers 1-4) | Comprehensive test suite (Feature, Boundary, Combinatorial, 90-Day Synthetic Workload) | M4 | survey_explorer_2 |
| 18 | Tier 5 Adversarial Coverage Hardening | White-box stress testing, edge-case generation, and regression verification | M4 | survey_explorer_2 |

---

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | SP-API Ingestion Parsers & Report Fixtures | `src/fba_audit/models/`, `src/fba_audit/parsers/`, and `tests/fixtures/` | none | DONE |
| M2 | Deterministic Reconciliation & Policy Citation Engine | `src/fba_audit/engine/` (Warehouse, Returns, Dimensions, Policy Registry) | M1 | DONE |
| M3 | Audit Dossier & Dispute Package Generator | `src/fba_audit/reports/`, `src/fba_audit/cli.py`, `src/fba_audit/api.py` | M2 | DONE |
| M4 | E2E Verification & Adversarial Hardening (Final Milestone) | Full test pass (Tiers 1-4) & Tier 5 Adversarial Hardening | M1, M2, M3 | DONE |
| M5 | Autonomous Operations & Payout Alert Pipeline | 24/7 Daemon, Persistent Payout Ledger, MIME/HTML Notification Mailer, Scheduled Tasks | M4 | DONE |

---

## Interface Contracts

### 1. Ingestion Parsers (`src/fba_audit/parsers/`) ↔ Engine (`src/fba_audit/engine/`)
```python
def parse_ledger_report(file_path: Union[str, Path, TextIO]) -> List[LedgerDetailRecord]: ...
def parse_customer_returns_report(file_path: Union[str, Path, TextIO]) -> List[CustomerReturnRecord]: ...
def parse_reimbursements_report(file_path: Union[str, Path, TextIO]) -> List[ReimbursementRecord]: ...
def parse_estimated_fees_report(file_path: Union[str, Path, TextIO]) -> List[FeeEstimateRecord]: ...
```
- Input: Valid TSV/CSV file paths or open text streams.
- Output: Validated lists of immutable Pydantic records with `Decimal` numeric types.
- Errors: `ParserError` on invalid TSV schemas, missing mandatory columns, or malformed values.

### 2. Reconciliation Engine (`src/fba_audit/engine/`) ↔ Reporting (`src/fba_audit/reports/`)
```python
class AuditEngine:
    def reconcile(
        self,
        ledger_records: List[LedgerDetailRecord],
        returns_records: List[CustomerReturnRecord],
        reimbursement_records: List[ReimbursementRecord],
        fee_records: List[FeeEstimateRecord],
        as_of_date: Optional[date] = None,
    ) -> AuditResult: ...
```
- `AuditResult` contains:
  - `claims: List[ClaimRecord]` (itemized discrepancy claims)
  - `summary: AuditSummary` (totals by discrepancy type, units, dollars, eligible claim counts)
  - `reconciled_at: datetime`

### 3. Reporting (`src/fba_audit/reports/`) ↔ Exporters & CLI
```python
def export_claim_batch_csv(claims: List[ClaimRecord], output_path: Union[str, Path]) -> Path: ...
def export_claim_batch_json(claims: List[ClaimRecord], output_path: Union[str, Path]) -> Path: ...
def generate_markdown_dossier(result: AuditResult, output_path: Union[str, Path]) -> Path: ...
def generate_html_dossier(result: AuditResult, output_path: Union[str, Path]) -> Path: ...
```

---

## Code Layout

```
C:\Users\saksh\teamwork_projects\amazon_fba_audit\
├── pyproject.toml
├── README.md
├── PROJECT.md
├── TEST_INFRA.md
├── run_daily_audit.bat
├── inbound_reports/
├── audit_output/
├── payouts/
│   ├── payout_ledger.json
│   ├── daemon_run.log
│   └── notifications/
├── src/
│   └── fba_audit/
│       ├── __init__.py
│       ├── api.py
│       ├── cli.py
│       ├── daemon.py
│       ├── mailer.py
│       ├── models/
│       │   ├── __init__.py
│       │   ├── enums.py
│       │   ├── reports.py
│       │   ├── claims.py
│       │   └── policies.py
│       ├── parsers/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── ledger.py
│       │   ├── customer_returns.py
│       │   ├── reimbursements.py
│       │   └── estimated_fees.py
│       ├── engine/
│       │   ├── __init__.py
│       │   ├── reconciler.py
│       │   ├── warehouse.py
│       │   ├── customer_returns.py
│       │   ├── dimensional.py
│       │   └── policy_registry.py
│       └── reports/
│           ├── __init__.py
│           ├── csv_generator.py
│           ├── json_generator.py
│           ├── md_dossier.py
│           └── html_dossier.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── fixtures/
    │   ├── ledger_detail_sample.tsv
    │   ├── customer_returns_sample.tsv
    │   ├── reimbursements_sample.tsv
    │   └── estimated_fees_sample.tsv
    ├── unit/
    │   ├── test_parsers.py
    │   ├── test_models.py
    │   ├── test_warehouse_reconciler.py
    │   ├── test_returns_reconciler.py
    │   ├── test_dimensional_reconciler.py
    │   ├── test_policy_registry.py
    │   └── test_reports.py
    ├── e2e/
    │   ├── test_tier1_features.py
    │   ├── test_tier2_boundaries.py
    │   ├── test_tier3_combinations.py
    │   └── test_tier4_synthetic_workload.py
    └── generators/
        ├── ledger_simulator.py
        └── ground_truth_oracle.py
```
