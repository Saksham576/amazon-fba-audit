"""
Unit tests for self-serve web intake portal & dispute authorization API (fba_audit.acquisition.portal).
"""

from decimal import Decimal
import json
from pathlib import Path
import urllib.request
import urllib.error
import pytest

from fba_audit.acquisition.portal import (
    AuthorizationRecord,
    AuthorizationRequest,
    IntakeAuditSummary,
    SellerIntakePortal,
    start_portal_server,
)


@pytest.fixture
def fixtures_dir() -> Path:
    return Path("tests/fixtures")


def test_portal_audit_from_files(tmp_path: Path, fixtures_dir: Path):
    portal = SellerIntakePortal(portal_dir=tmp_path / "portal")

    ledger_file = fixtures_dir / "ledger_detail_sample.tsv"
    returns_file = fixtures_dir / "customer_returns_sample.tsv"
    reimb_file = fixtures_dir / "reimbursements_sample.tsv"
    fees_file = fixtures_dir / "estimated_fees_sample.tsv"

    summary = portal.audit_from_files(
        ledger_path=ledger_file,
        returns_path=returns_file,
        reimbursements_path=reimb_file,
        fees_path=fees_file,
        seller_id="TEST_BRAND_STORE",
    )

    assert summary.submission_id.startswith("SUB-")
    assert summary.seller_id == "TEST_BRAND_STORE"
    assert summary.total_recoverable_usd > 0
    assert summary.contingency_fee_usd == (summary.total_recoverable_usd * Decimal("0.15")).quantize(Decimal("0.01"))
    assert summary.seller_net_recovery_usd == (summary.total_recoverable_usd - summary.contingency_fee_usd).quantize(Decimal("0.01"))
    assert "warehouse_lost_damaged" in summary.category_breakdown
    assert "customer_returns" in summary.category_breakdown
    assert "G200379860" in summary.policy_citations
    assert "G200213130" in summary.policy_citations


def test_portal_audit_from_string_content(tmp_path: Path, fixtures_dir: Path):
    portal = SellerIntakePortal(portal_dir=tmp_path / "portal")

    ledger_content = (fixtures_dir / "ledger_detail_sample.tsv").read_text(encoding="utf-8")
    reimb_content = (fixtures_dir / "reimbursements_sample.tsv").read_text(encoding="utf-8")
    fees_content = (fixtures_dir / "estimated_fees_sample.tsv").read_text(encoding="utf-8")

    summary = portal.audit_reports(
        ledger_content=ledger_content,
        reimbursements_content=reimb_content,
        fees_content=fees_content,
        seller_id="STRING_SELLER",
    )

    assert summary.total_claims_count > 0
    assert summary.seller_id == "STRING_SELLER"


def test_portal_authorize_and_persistence(tmp_path: Path, fixtures_dir: Path):
    portal = SellerIntakePortal(portal_dir=tmp_path / "portal")

    summary = portal.audit_from_files(
        ledger_path=fixtures_dir / "ledger_detail_sample.tsv",
        reimbursements_path=fixtures_dir / "reimbursements_sample.tsv",
        fees_path=fixtures_dir / "estimated_fees_sample.tsv",
        seller_id="AURA_STORE",
    )

    auth_req = AuthorizationRequest(
        submission_id=summary.submission_id,
        seller_id="AURA_STORE",
        brand_name="AuraKitchen Labs",
        contact_email="marcus@aurakitchenlabs.com",
        contact_name="Marcus Vance",
        signature_name="Marcus Vance",
        contingency_agreement_accepted=True,
    )

    auth_record = portal.authorize_dispute_processing(auth_req)

    assert auth_record.authorization_id.startswith("AUTH-")
    assert auth_record.status == "AUTHORIZED"
    assert auth_record.total_recoverable_usd == summary.total_recoverable_usd
    assert auth_record.contingency_fee_usd == summary.contingency_fee_usd
    assert Path(auth_record.deliverables_dir).exists()

    # Verify persistent retrieval
    all_auths = portal.list_authorizations()
    assert len(all_auths) == 1
    assert all_auths[0].authorization_id == auth_record.authorization_id

    fetched = portal.get_authorization(auth_record.authorization_id)
    assert fetched is not None
    assert fetched.contact_email == "marcus@aurakitchenlabs.com"


def test_portal_html_rendering(tmp_path: Path):
    portal = SellerIntakePortal(portal_dir=tmp_path / "portal")
    html = portal.render_portal_html()

    assert "<!DOCTYPE html>" in html
    assert "NexusPulse" in html
    assert "G200379860" in html
    assert "G200213130" in html
    assert "15% Contingency Fee" in html or "15%" in html
    assert "file-ledger" in html
    assert "file-returns" in html
    assert "file-reimb" in html
    assert "file-fees" in html


def test_portal_http_server_endpoints(tmp_path: Path, fixtures_dir: Path):
    portal = SellerIntakePortal(portal_dir=tmp_path / "portal")
    # Bind to localhost on port 0 to let OS assign an open ephemeral port
    server, thread = start_portal_server(portal=portal, host="127.0.0.1", port=0)
    assigned_port = server.server_address[1]
    base_url = f"http://127.0.0.1:{assigned_port}"

    try:
        # 1. GET / (portal HTML)
        with urllib.request.urlopen(f"{base_url}/") as resp:
            assert resp.status == 200
            assert "text/html" in resp.headers.get("Content-Type")
            html_body = resp.read().decode("utf-8")
            assert "Amazon FBA" in html_body

        # 2. GET /api/health
        with urllib.request.urlopen(f"{base_url}/api/health") as resp:
            assert resp.status == 200
            health_data = json.loads(resp.read().decode("utf-8"))
            assert health_data["status"] == "ok"

        # 3. POST /api/audit
        ledger_txt = (fixtures_dir / "ledger_detail_sample.tsv").read_text(encoding="utf-8")
        reimb_txt = (fixtures_dir / "reimbursements_sample.tsv").read_text(encoding="utf-8")
        audit_payload = json.dumps({
            "seller_id": "HTTP_TEST_SELLER",
            "ledger": ledger_txt,
            "reimbursements": reimb_txt,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{base_url}/api/audit",
            data=audit_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            audit_resp = json.loads(resp.read().decode("utf-8"))
            assert "submission_id" in audit_resp
            assert audit_resp["total_claims_count"] > 0
            submission_id = audit_resp["submission_id"]

        # 4. POST /api/authorize
        auth_payload = json.dumps({
            "submission_id": submission_id,
            "seller_id": "HTTP_TEST_SELLER",
            "brand_name": "HTTP Test Brand",
            "contact_email": "test@httpbrand.com",
            "contact_name": "Tester",
            "signature_name": "Tester",
            "contingency_agreement_accepted": True,
        }).encode("utf-8")

        req_auth = urllib.request.Request(
            f"{base_url}/api/authorize",
            data=auth_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req_auth) as resp:
            assert resp.status == 200
            auth_resp = json.loads(resp.read().decode("utf-8"))
            assert "authorization_id" in auth_resp
            assert auth_resp["status"] == "AUTHORIZED"

        # 5. GET /api/submissions
        with urllib.request.urlopen(f"{base_url}/api/submissions") as resp:
            assert resp.status == 200
            subs = json.loads(resp.read().decode("utf-8"))
            assert len(subs) == 1
            assert subs[0]["contact_email"] == "test@httpbrand.com"

        # 5b. GET /api/submissions/<auth_id> (success and 404)
        auth_id = auth_resp["authorization_id"]
        with urllib.request.urlopen(f"{base_url}/api/submissions/{auth_id}") as resp:
            assert resp.status == 200
            single_sub = json.loads(resp.read().decode("utf-8"))
            assert single_sub["authorization_id"] == auth_id
            assert single_sub["contact_email"] == "test@httpbrand.com"

        with pytest.raises(urllib.error.HTTPError) as exc_404:
            urllib.request.urlopen(f"{base_url}/api/submissions/AUTH-NONEXISTENT")
        assert exc_404.value.code == 404

        # 5c. POST /api/audit with invalid JSON -> 400
        req_bad = urllib.request.Request(
            f"{base_url}/api/audit",
            data=b"INVALID_JSON_CONTENT{{{",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_bad:
            urllib.request.urlopen(req_bad)
        assert exc_bad.value.code == 400

        # 5d. POST /api/authorize with invalid payload -> 400
        req_bad_auth = urllib.request.Request(
            f"{base_url}/api/authorize",
            data=json.dumps({"invalid": "missing_required_fields"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_bad_auth:
            urllib.request.urlopen(req_bad_auth)
        assert exc_bad_auth.value.code == 400

        # 6. GET /invalid_path -> 404
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(f"{base_url}/nonexistent")
        assert exc_info.value.code == 404

    finally:
        server.shutdown()
        server.server_close()


def test_portal_audit_all_four_reports(tmp_path: Path, fixtures_dir: Path):
    portal = SellerIntakePortal(portal_dir=tmp_path / "portal")

    ledger_txt = (fixtures_dir / "ledger_detail_sample.tsv").read_text(encoding="utf-8")
    returns_txt = (fixtures_dir / "customer_returns_sample.tsv").read_text(encoding="utf-8")
    reimb_txt = (fixtures_dir / "reimbursements_sample.tsv").read_text(encoding="utf-8")
    fees_txt = (fixtures_dir / "estimated_fees_sample.tsv").read_text(encoding="utf-8")

    summary = portal.audit_reports(
        ledger_content=ledger_txt,
        returns_content=returns_txt,
        reimbursements_content=reimb_txt,
        fees_content=fees_txt,
        seller_id="ALL_REPORTS_SELLER",
    )
    assert summary.total_claims_count > 0
    assert summary.seller_id == "ALL_REPORTS_SELLER"


def test_portal_authorize_uncached_submission(tmp_path: Path):
    portal = SellerIntakePortal(portal_dir=tmp_path / "portal")

    auth_req = AuthorizationRequest(
        submission_id="SUB-UNCACHED-99",
        seller_id="UNCACHED_STORE",
        brand_name="Uncached Brand",
        contact_email="uncached@brand.com",
        contact_name="Uncached User",
        signature_name="Uncached User",
        contingency_agreement_accepted=True,
    )
    record = portal.authorize_dispute_processing(auth_req)
    assert record.submission_id == "SUB-UNCACHED-99"
    assert record.status == "AUTHORIZED"
    assert portal.get_authorization(record.authorization_id) is not None
    assert portal.get_authorization("AUTH-DOES-NOT-EXIST") is None


def test_portal_cli_main(monkeypatch, tmp_path: Path):
    from fba_audit.acquisition.portal import main
    p_dir = tmp_path / "cli_portal"
    # Provide --port 0 so it binds to an OS free port and doesn't block
    monkeypatch.setattr("sys.argv", ["fba-portal", "--port", "0", "--portal-dir", str(p_dir)])
    # Raise KeyboardInterrupt when thread.join is called to test clean shutdown
    import threading
    real_join = threading.Thread.join
    def mock_join(self, timeout=None):
        raise KeyboardInterrupt
    monkeypatch.setattr(threading.Thread, "join", mock_join)

    ret = main()
    assert ret == 0
