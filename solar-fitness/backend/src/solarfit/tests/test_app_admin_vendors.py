"""Owner: karthik (App Platform & Foundation).

Tests for routers/app_admin_vendors.py — closes the "admin vendor
oversight has no backend at all" gap found during a frontend/backend
sync audit. Same seeding pattern test_vendor_router.py uses (no
create_job()/create_vendor() endpoint exists, so tests seed VendorRow/
VendorJobRow directly against the ORM).
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from solarfit.db import get_session
from solarfit.main import app
from solarfit.repositories import audit as audit_repo
from solarfit.repositories import sites as sites_repo
from solarfit.repositories.vendors import VendorJobRow, VendorRow

LON, LAT = 78.4867, 17.3850


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def site(db_session):
    return sites_repo.create(
        db_session,
        site_type="ROOFTOP_RESIDENTIAL",
        name="Test Rooftop",
        owner_org="Test Org",
        jurisdiction="IN-TG",
        centroid={"type": "Point", "coordinates": [LON, LAT]},
    )


def _vendor(db_session, **overrides) -> VendorRow:
    defaults = {
        "name": "Acme Surveys",
        "verification_status": "verified",
        "availability": True,
        "accuracy_score": 0.92,
        "service_area": {"region": "Telangana", "districts": ["Hyderabad"]},
        "payout_method_type": "UPI",
        "payout_masked_account": "acme@upi",
        "documents": ["license.pdf"],
    }
    defaults.update(overrides)
    row = VendorRow(**defaults)
    db_session.add(row)
    db_session.flush()
    return row


def _job(db_session, site, vendor, **overrides) -> VendorJobRow:
    defaults = {
        "site_id": site.id,
        "vendor_id": vendor.id,
        "status": "queued",
        "district": "Hyderabad",
        "state": "Telangana",
        "deadline": datetime.now(UTC) + timedelta(days=3),
        "payout_inr": 1500,
        "requirements": [],
    }
    defaults.update(overrides)
    row = VendorJobRow(**defaults)
    db_session.add(row)
    db_session.flush()
    return row


def test_list_requires_admin_role(client, make_auth_header):
    r = client.get("/app/admin/vendors", headers=make_auth_header(role="vendor"))
    assert r.status_code == 403


def test_list_requires_auth(client):
    r = client.get("/app/admin/vendors")
    assert r.status_code == 401


def test_list_returns_camelcase_summary(client, make_auth_header, db_session, site):
    vendor = _vendor(db_session)
    r = client.get("/app/admin/vendors", headers=make_auth_header(role="admin"))
    assert r.status_code == 200
    body = r.json()
    match = next(v for v in body if v["id"] == str(vendor.id))
    assert match["name"] == "Acme Surveys"
    assert match["verificationStatus"] == "verified"
    assert match["serviceArea"] == "Telangana"
    assert match["payoutMethod"] == "UPI"
    assert match["activeJobs"] == 0
    assert match["totalJobsCompleted"] == 0
    assert match["slaCompliancePct"] == 0.0


def test_list_filters_by_q_and_verification_status(client, make_auth_header, db_session):
    _vendor(db_session, name="Alpha Surveys", verification_status="verified")
    _vendor(db_session, name="Beta Surveys", verification_status="pending")

    headers = make_auth_header(role="admin")
    r = client.get("/app/admin/vendors", headers=headers, params={"q": "Alpha"})
    assert [v["name"] for v in r.json()] == ["Alpha Surveys"]

    r = client.get("/app/admin/vendors", headers=headers, params={"verificationStatus": "pending"})
    assert [v["name"] for v in r.json()] == ["Beta Surveys"]


def test_active_and_completed_job_counts_are_real(client, make_auth_header, db_session, site):
    vendor = _vendor(db_session)
    _job(db_session, site, vendor, status="in_progress")
    on_time = datetime.now(UTC)
    _job(
        db_session,
        site,
        vendor,
        status="submitted",
        deadline=on_time + timedelta(days=1),
        submitted_at=on_time,
    )

    r = client.get(f"/app/admin/vendors/{vendor.id}", headers=make_auth_header(role="admin"))
    body = r.json()
    assert body["activeJobs"] == 1
    assert body["totalJobsCompleted"] == 1
    assert body["slaCompliancePct"] == 100.0


def test_get_unknown_vendor_is_404(client, make_auth_header):
    r = client.get("/app/admin/vendors/00000000-0000-0000-0000-000000000000", headers=make_auth_header(role="admin"))
    assert r.status_code == 404


def test_verification_queue_only_returns_pending(client, make_auth_header, db_session):
    _vendor(db_session, name="Verified Co", verification_status="verified")
    pending = _vendor(db_session, name="Pending Co", verification_status="pending")

    r = client.get("/app/admin/vendors/verification-queue", headers=make_auth_header(role="admin"))
    body = r.json()
    assert [v["id"] for v in body] == [str(pending.id)]


def test_suspend_sets_status_and_writes_audit_log(client, make_auth_header, db_session):
    vendor = _vendor(db_session)
    headers = make_auth_header(role="admin")

    r = client.post(f"/app/admin/vendors/{vendor.id}/suspend", headers=headers)
    assert r.status_code == 200
    assert r.json()["verificationStatus"] == "suspended"

    rows = audit_repo.list_audit_log(db_session, action="vendor.suspend")
    assert any(row.target == str(vendor.id) for row in rows)


def test_reinstate_sets_status_to_verified(client, make_auth_header, db_session):
    vendor = _vendor(db_session, verification_status="suspended")
    r = client.post(f"/app/admin/vendors/{vendor.id}/reinstate", headers=make_auth_header(role="admin"))
    assert r.status_code == 200
    assert r.json()["verificationStatus"] == "verified"


def test_approve_verification_sets_status_to_verified(client, make_auth_header, db_session):
    vendor = _vendor(db_session, verification_status="pending")
    r = client.post(
        f"/app/admin/vendors/{vendor.id}/verification/approve", headers=make_auth_header(role="admin")
    )
    assert r.status_code == 200
    assert r.json()["verificationStatus"] == "verified"


def test_reject_verification_sets_status_to_rejected(client, make_auth_header, db_session):
    vendor = _vendor(db_session, verification_status="pending")
    r = client.post(
        f"/app/admin/vendors/{vendor.id}/verification/reject", headers=make_auth_header(role="admin")
    )
    assert r.status_code == 200
    assert r.json()["verificationStatus"] == "rejected"


def test_mutation_on_unknown_vendor_is_404(client, make_auth_header):
    r = client.post(
        "/app/admin/vendors/00000000-0000-0000-0000-000000000000/suspend",
        headers=make_auth_header(role="admin"),
    )
    assert r.status_code == 404
