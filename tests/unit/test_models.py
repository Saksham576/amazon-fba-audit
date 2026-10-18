"""Unit tests for core domain models, policies, and claim records."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import pytest
from pydantic import ValidationError

from fba_audit.models.claims import (
    AuditSummary,
    CategoryBreakdown,
    ClaimRecord,
    generate_claim_id,
)
from fba_audit.models.enums import (
    ClaimStatus,
    DiscrepancyType,
    Disposition,
    EventType,
    PolicyCode,
    ReasonCode,
    SizeTier,
)
from fba_audit.models.policies import (
    ClaimWindow,
    POLICY_REGISTRY,
    get_policy_citation,
)
from fba_audit.models.reports import (
    CustomerReturnRecord,
    FeeEstimateRecord,
    LedgerDetailRecord,
    ReimbursementRecord,
    coerce_to_decimal,
)


def test_models_immutability():
    """Verify that domain models are frozen and reject in-place attribute mutations."""
    now = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)

    # 1. LedgerDetailRecord
    ledger = LedgerDetailRecord(
        event_date_time=now,
        fnsku="X001",
        quantity=5,
    )
    with pytest.raises(ValidationError):
        ledger.quantity = 10  # type: ignore

    # 2. CustomerReturnRecord
    ret = CustomerReturnRecord(
        return_date=now,
        amazon_order_id="111-1234567-1234567",
        fnsku="X001",
    )
    with pytest.raises(ValidationError):
        ret.fnsku = "X002"  # type: ignore

    # 3. ReimbursementRecord
    reimb = ReimbursementRecord(
        approval_date=now,
        reimbursement_id="R101",
        fnsku="X001",
        amount_per_unit=Decimal("15.50"),
        amount_total=Decimal("15.50"),
        quantity_reimbursed_cash=1,
        quantity_reimbursed_total=1,
    )
    with pytest.raises(ValidationError):
        reimb.amount_total = Decimal("20.00")  # type: ignore

    # 4. FeeEstimateRecord
    fee = FeeEstimateRecord(
        sku="SKU1",
        fnsku="X001",
        longest_side=Decimal("10.0"),
        median_side=Decimal("8.0"),
        shortest_side=Decimal("2.0"),
        item_package_weight=Decimal("1.500"),
    )
    with pytest.raises(ValidationError):
        fee.longest_side = Decimal("12.0")  # type: ignore

    # 5. ClaimRecord
    claim = ClaimRecord.create(
        fnsku="X001",
        msku="SKU1",
        asin="B001",
        event_date=date(2026, 8, 1),
        discrepancy_type=DiscrepancyType.WAREHOUSE_LOST,
        discrepancy_quantity=2,
        unit_reimbursement_estimate=Decimal("25.00"),
        policy_citation="Policy G200213130",
        policy_clause="Lost warehouse inventory",
        claim_window_days=60,
        claim_expiration_date=date(2026, 9, 30),
        days_until_expiration=60,
        claim_status=ClaimStatus.ELIGIBLE_NOW,
        evidence_notes="Verified loss",
        transaction_id="TX123",
    )
    with pytest.raises(ValidationError):
        claim.fnsku = "X999"  # type: ignore


def test_zero_float_decimal_coercion():
    """Verify that coerce_to_decimal rejects float representation artifacts and preserves exact precision."""
    assert coerce_to_decimal("19.99") == Decimal("19.99")
    assert coerce_to_decimal(10) == Decimal("10.00")
    assert coerce_to_decimal(None) == Decimal("0.00")
    assert coerce_to_decimal("$1,249.99") == Decimal("1249.99")
    assert coerce_to_decimal("€45.50") == Decimal("45.50")
    assert isinstance(coerce_to_decimal("19.99"), Decimal)
    assert not isinstance(coerce_to_decimal("19.99"), float)


def test_reimbursement_model_invariants():
    """Verify reimbursement arithmetic rules and quantity validations."""
    now = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)

    # Valid reimbursement with cash and inventory components
    r = ReimbursementRecord(
        approval_date=now,
        reimbursement_id="R100",
        fnsku="X001",
        amount_per_unit=Decimal("20.00"),
        amount_total=Decimal("40.00"),
        quantity_reimbursed_cash=2,
        quantity_reimbursed_inventory=1,
        quantity_reimbursed_total=3,
    )
    assert r.quantity_reimbursed_total == 3
    assert r.currency_unit == "USD"

    # Auto-computation when total is omitted / zero
    r_auto = ReimbursementRecord(
        approval_date=now,
        reimbursement_id="R101",
        fnsku="X001",
        amount_per_unit=Decimal("10.00"),
        amount_total=Decimal("10.00"),
        quantity_reimbursed_cash=1,
        quantity_reimbursed_inventory=2,
    )
    assert r_auto.quantity_reimbursed_total == 3

    # Mismatch raises error
    with pytest.raises(ValidationError):
        ReimbursementRecord(
            approval_date=now,
            reimbursement_id="R102",
            fnsku="X001",
            amount_per_unit=Decimal("10.00"),
            amount_total=Decimal("10.00"),
            quantity_reimbursed_cash=1,
            quantity_reimbursed_inventory=1,
            quantity_reimbursed_total=5,
        )


def test_fee_model_dimensional_helpers():
    """Verify package dimension helper properties on FeeEstimateRecord."""
    rec = FeeEstimateRecord(
        sku="SKU-YOGA",
        fnsku="X005XYZ",
        longest_side=Decimal("24.0"),
        median_side=Decimal("6.0"),
        shortest_side=Decimal("6.0"),
        item_package_weight=Decimal("3.200"),
    )
    # Girth = 2 * (6.0 + 6.0) = 24.0
    assert rec.girth == Decimal("24.00")
    # Length + Girth = 24.0 + 24.0 = 48.0
    assert rec.length_and_girth == Decimal("48.00")
    # Dimensional Weight = (24 * 6 * 6) / 139 = 864 / 139 = 6.2158... -> 6.22
    assert rec.dimensional_weight == Decimal("6.22")


def test_deterministic_claim_id_generation():
    """Verify that claim_id calculation via RFC 4122 UUID5 is 100% deterministic and reproducible."""
    d = date(2026, 8, 15)
    id1 = generate_claim_id("X002ABC101", "ORD-12345", DiscrepancyType.CUSTOMER_RETURN_NOT_RECEIVED, d)
    id2 = generate_claim_id("X002ABC101", "ORD-12345", DiscrepancyType.CUSTOMER_RETURN_NOT_RECEIVED, d)
    assert id1 == id2
    assert len(id1) == 36  # Standard UUID length

    # Different reference or date changes UUID
    id3 = generate_claim_id("X002ABC101", "ORD-99999", DiscrepancyType.CUSTOMER_RETURN_NOT_RECEIVED, d)
    assert id1 != id3


def test_claim_record_creation_and_19_col_dict():
    """Verify ClaimRecord creation factory and 19-column Seller Central export dictionary."""
    ev_date = date(2026, 8, 1)
    claim = ClaimRecord.create(
        fnsku="X002ABC101",
        msku="SKU-WIRELESS",
        asin="B09ABCDEFG",
        event_date=ev_date,
        discrepancy_type=DiscrepancyType.WAREHOUSE_LOST,
        discrepancy_quantity=3,
        unit_reimbursement_estimate=Decimal("49.99"),
        policy_citation="FBA inventory reimbursement policy: Fulfillment center operations claims",
        policy_clause="G200213130 - Lost inventory",
        claim_window_days=60,
        claim_expiration_date=date(2026, 9, 30),
        days_until_expiration=45,
        claim_status=ClaimStatus.ELIGIBLE_NOW,
        evidence_notes="3 units lost at DFW6",
        transaction_id="TX-DFW6-01",
    )
    assert claim.discrepancy_quantity == 3
    assert claim.total_reimbursement_estimate == Decimal("149.97")

    d = claim.to_19_col_dict()
    assert len(d) == 19
    expected_keys = [
        "claim_id", "fnsku", "msku", "asin", "transaction_id", "order_id",
        "event_date", "discrepancy_type", "quantity", "unit_price",
        "claim_amount", "currency", "policy_citation", "policy_clause",
        "claim_window_days", "claim_expiration_date", "days_until_expiration",
        "claim_status", "evidence_notes"
    ]
    for key in expected_keys:
        assert key in d, f"Missing expected key: {key}"
    assert d["quantity"] == "3"
    assert d["claim_amount"] == "149.97"
    assert d["unit_price"] == "49.99"


def test_policy_citation_and_claim_window_evaluation():
    """Verify ClaimWindow temporal logic and Policy Citation Registry."""
    ev_date = date(2026, 8, 1)

    # 1. Under hold window (e.g. 20 days elapsed < 45 days hold)
    w_hold = ClaimWindow.evaluate(
        event_date=ev_date,
        as_of_date=ev_date + timedelta(days=20),
        window_days=60,
        hold_days=45,
    )
    assert w_hold.status == ClaimStatus.PENDING_RETURN_WINDOW
    assert w_hold.expiration_date == date(2026, 9, 30)
    assert w_hold.days_until_expiration == 40

    # 2. Eligible window (e.g. 50 days elapsed with hold 45, window 60)
    w_elig = ClaimWindow.evaluate(
        event_date=ev_date,
        as_of_date=ev_date + timedelta(days=50),
        window_days=60,
        hold_days=45,
    )
    assert w_elig.status == ClaimStatus.ELIGIBLE_NOW
    assert w_elig.days_until_expiration == 10

    # 3. Expired window (e.g. 65 days elapsed > 60 days window)
    w_exp = ClaimWindow.evaluate(
        event_date=ev_date,
        as_of_date=ev_date + timedelta(days=65),
        window_days=60,
        hold_days=45,
    )
    assert w_exp.status == ClaimStatus.EXPIRED
    assert w_exp.days_until_expiration == -5

    # Policy citations lookup
    cit_wh = get_policy_citation(DiscrepancyType.WAREHOUSE_LOST)
    assert cit_wh.help_hub_id == "G200213130"
    assert cit_wh.standard_window_days == 60

    cit_ret = get_policy_citation(DiscrepancyType.CUSTOMER_RETURN_NOT_RECEIVED)
    assert cit_ret.help_hub_id == "G200379860"

    cit_dim = get_policy_citation(DiscrepancyType.DIMENSIONAL_WEIGHT_OVERCHARGE)
    assert cit_dim.help_hub_id == "G21213"
    assert cit_dim.standard_window_days == 90


def test_audit_summary_and_category_breakdown():
    """Verify CategoryBreakdown and AuditSummary instantiation and field syncing."""
    bd = CategoryBreakdown(
        discrepancy_type=DiscrepancyType.WAREHOUSE_LOST,
        total_claims=3,
        total_units=5,
        total_amount=Decimal("125.00"),
    )
    assert bd.total_units == 5

    summary = AuditSummary(
        audit_id="AUD-001",
        as_of_date=date(2026, 9, 29),
        generated_at=datetime.now(),
        total_claims=10,
        total_eligible_count=8,
        total_expired_count=2,
        total_discrepancy_units=15,
        total_claim_amount=Decimal("350.00"),
        category_breakdowns=[bd],
    )
    assert summary.total_claims_count == 10
    assert summary.total_verified_amount == Decimal("350.00")
    assert summary.total_discrepancy_amount == Decimal("350.00")


def test_policy_fallback():
    """Verify that unknown discrepancy types safely fallback to master operations policy."""
    cit = get_policy_citation("UNKNOWN_DISCREPANCY")
    assert cit.code == PolicyCode.POL_FBA_OPS


def test_reports_compat_fields():
    """Verify backward-compatibility fields on report domain models."""
    d = date(2026, 8, 10)
    l = LedgerDetailRecord(
        date=d,
        fnsku="X001",
        quantity=2,
        fulfillment_center="PHX3",
    )
    assert l.date == d
    assert l.fulfillment_center == "PHX3"
    assert l.fulfillment_center_id == "PHX3"

    ret = CustomerReturnRecord(
        return_date=d,
        order_id="111-999",
        fnsku="X001",
    )
    assert ret.order_id == "111-999"
    assert ret.amazon_order_id == "111-999"

    # Type error on invalid input to coerce_to_decimal
    with pytest.raises(TypeError):
        coerce_to_decimal(object())
