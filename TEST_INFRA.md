# E2E Test Infra: Amazon FBA Inventory Discrepancy & Reimbursement Audit Engine

## Test Philosophy
- **Requirement-Driven & Opaque-Box**: Derived strictly from `ORIGINAL_REQUEST.md` and official Amazon SP-API / Seller Central specifications, completely independent of internal implementation artifacts.
- **Methodology**: Systematic Category-Partition + Boundary Value Analysis (BVA) + Pairwise Combinatorial Testing + 90-Day Real-World Synthetic Workload Simulation.
- **Precision Invariant**: Strict zero-float tolerance — all monetary assertions must match exact cent values ($0.00 drift) with zero rounding ambiguity.
- **Oracle Verification**: Tier 4 tests execute an independent state-machine `GroundTruthOracle` against the engine to verify 100% precision (0 false positives) and 100% recall (0 missed discrepancies).

---

## Feature Inventory & Test Mapping

| # | Feature | Requirement Source | Tier 1 (Coverage) | Tier 2 (Boundaries) | Tier 3 (Combinations) |
|---|---------|-------------------|:-----------------:|:-------------------:|:---------------------:|
| 1 | Ledger Detail TSV Parser | R1 (`GET_LEDGER_DETAIL_VIEW_DATA`) | 5 | 5 | ✓ |
| 2 | Customer Returns TSV Parser | R1 (`GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA`) | 5 | 5 | ✓ |
| 3 | Reimbursements TSV Parser | R1 (`GET_FBA_REIMBURSEMENT_DATA`) | 5 | 5 | ✓ |
| 4 | Estimated Fees TSV Parser | R1 (`GET_FBA_ESTIMATED_FBA_FEES_TXT_DATA`) | 5 | 5 | ✓ |
| 5 | Warehouse Lost/Damaged Math | R2 (`(Lost+Damaged) - (Found+Reimbursed+Disposed)`) | 5 | 5 | ✓ |
| 6 | Customer Return 45-60 Day Reconciler | R2 (Unreturned refunds & hold period) | 5 | 5 | ✓ |
| 7 | Dimensional Tier & Fee Overcharge | R2 (Size tiers, dim weight, fee deltas) | 5 | 5 | ✓ |
| 8 | Policy Citation & Claim Window | R2 (G200213130, G21213, 60-day rule) | 5 | 5 | ✓ |
| 9 | 19-Column CSV Claim Batch | R3 (Itemized Seller Central claim file) | 5 | 5 | ✓ |
| 10 | Draft-2020-12 JSON Claim Batch | R3 (Structured machine export) | 5 | 5 | ✓ |
| 11 | Markdown Executive Dossier | R3 (Summary KPIs & evidence tables) | 5 | 5 | ✓ |
| 12 | Standalone HTML Executive Dossier | R3 (Single-file zero-CDN HTML) | 5 | 5 | ✓ |
| 13 | CLI & Python API Execution | R1-R3 (`fba_audit.cli` & `api.AuditEngine`) | 5 | 5 | ✓ |

---

## Test Architecture

### 1. Test Runner & Invocation
- **Framework**: `pytest`
- **Invocation**:
  ```bash
  python -m pytest tests/ -v
  ```
- **Pass/Fail Semantics**: All test suites must complete with exit code 0, 100% test pass rate, and zero unhandled exceptions.

### 2. Directory Layout
```
tests/
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

### 3. Tier 4: Real-World Application Scenarios
| Scenario # | Scenario Name | Features Exercised | Injected Discrepancies | Complexity |
|------------|---------------|-------------------|------------------------|------------|
| SC-1 | 90-Day Full Account Simulation | F1-F13 | 50 SKUs, 2,500+ ledger events with mixed lost, damaged, found, cash reimbursements, inventory reimbursements | High |
| SC-2 | Return Fraud & Transit Loss Lifecycle | F2, F3, F6, F8 | Customer refunded; 10 units never returned to FC, 5 units received after 45 days, 5 units received damaged by customer | High |
| SC-3 | Amazon Cubiscan Dimension Creep | F4, F7, F8, F9 | 15 products overcharged due to laser-measured Cuban scan flap flare crossing Large Standard into Small Oversize | Medium |
| SC-4 | Cash vs Inventory Reimbursement Balancing | F1, F3, F5, F8 | High-volume electronics with partial cash reimbursements and physical replacement units cancelling losses | High |
| SC-5 | Mixed Multi-Marketplace Edge Account | F1-F13 | Multi-FC transactions (PHX3, IND1, ONT8) with concurrent adjustments and expiration dates | High |

---

## Coverage Thresholds
- **Tier 1 (Feature Coverage)**: ≥65 test cases (≥5 per feature across 13 core features)
- **Tier 2 (Boundary & Corner Cases)**: ≥65 test cases (≥5 boundary conditions per feature: partial reimbursements, 30-day found window, 44/45/46 day return window, 59/60/61 day expiration boundary, zero-float edge cases)
- **Tier 3 (Cross-Feature Combinations)**: ≥15 pairwise interaction test cases (concurrent return + damage, fee dispute + warehouse loss, inventory reimbursement + cash clawback)
- **Tier 4 (Real-World Application Scenarios)**: ≥5 comprehensive scenarios with ground-truth oracle validation
- **Total Minimum Target**: ≥150 test cases with 100% passing rate in `pytest`.
