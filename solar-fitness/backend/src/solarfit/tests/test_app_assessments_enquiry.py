"""Tests for the enquiry-workflow additions to routers/app_assessments.py
(customer-selected-vendor visibility on approve, and the new reassign
endpoint) — run against a real Postgres-backed session (db_session,
rolled back after each test), since vendor_jobs/vendors use JSONB/UUID
columns that don't work against test_app_assessments.py's in-memory
SQLite fixture. Mirrors test_vendor_router.py's own fixture pattern.
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from solarfit.auth_users import create_access_token, hash_password
from solarfit.db import get_session
from solarfit.main import app
from solarfit.repositories import audit as audit_repo
from solarfit.repositories import notifications as notifications_repo
from solarfit.repositories import sites as sites_repo
from solarfit.repositories import users as users_repo
from solarfit.repositories.assessments import AssessmentRow
from solarfit.repositories.vendors import VendorJobRow, VendorRow

LON, LAT = 78.4867, 17.3850


@pytest.fixture
def client(db_session, monkeypatch):
    app.dependency_overrides[get_session] = lambda: db_session

    # approve/reject/reassign all re-read via get_admin_assessment(),
    # which opens its OWN session_scope() rather than the request's
    # dependency-injected session — patched to the same db_session so it
    # sees this test's uncommitted (savepoint-scoped) writes, same
    # pattern test_app_checks.py's _complete_with_canned_verdict uses.
    from contextlib import contextmanager

    @contextmanager
    def _fake_session_scope():
        yield db_session

    monkeypatch.setattr("solarfit.routers.app_assessments.session_scope", _fake_session_scope)

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


def _make_vendor(db_session, **overrides):
    defaults = dict(
        name="Acme Solar",
        verification_status="verified",
        availability=True,
        accuracy_score=0.9,
        service_area={"region": "Telangana", "districts": ["Hyderabad"]},
        payout_method_type="UPI",
        payout_masked_account="acme@upi",
    )
    defaults.update(overrides)
    row = VendorRow(**defaults)
    db_session.add(row)
    db_session.flush()
    return row


def _seed_pending_assessment(
    db_session, site_id: str, *, customer_selected_vendor_id=None, raised_by_user_id=None
):
    row = AssessmentRow(
        id=f"as-{site_id}",
        site_id=site_id,
        owner_org="Test Org",
        site_type="ROOFTOP_RESIDENTIAL",
        verdict="SUITABLE",
        score=0.8,
        confidence=0.75,
        review_status="pending",
        binding_constraint="net_metering_cap",
        reasons=["net_metering_cap is binding"],
        limitations="Pre-feasibility estimate only.",
        capacity={"recommended_kwp": 4.5, "ceilings": []},
        boundary={"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [0, 0]]]},
        usable_area_m2=80.0,
        cache_hit=False,
        customer_selected_vendor_id=customer_selected_vendor_id,
        enquiry_submitted_at=datetime.now(UTC) if customer_selected_vendor_id else None,
        raised_by_user_id=raised_by_user_id,
        engine_version="test",
        constraint_pack_version="rooftop_v1",
        created_at=datetime.now(UTC),
    )
    db_session.add(row)
    db_session.flush()
    return row


def _admin_headers(make_auth_header):
    return make_auth_header(role="admin")


def _make_customer(db_session):
    """Same shape as conftest.py's make_auth_header(role="customer"), but
    returns the created row too — the new audit/notification tests below
    need the customer's own id for raised_by_user_id, which the header
    fixture doesn't expose."""
    import uuid

    row = users_repo.create_user(
        db_session,
        email=f"test-customer-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("Test1234!"),
        name="Test Customer",
        role="customer",
        owner_org="Test Org",
    )
    token = create_access_token(str(row.id), row.role)
    return row, {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------- #
# approve — customer-selected vendor visibility
# --------------------------------------------------------------------- #


def test_approve_confirms_the_customers_own_vendor_selection(client, make_auth_header, db_session, site):
    vendor = _make_vendor(db_session)
    assessment = _seed_pending_assessment(db_session, site.id, customer_selected_vendor_id=vendor.id)

    response = client.post(
        f"/app/admin/assessments/{assessment.id}/approve",
        json={"vendorId": str(vendor.id)},
        headers=_admin_headers(make_auth_header),
    )
    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["customerSelectedVendorId"] == str(vendor.id)
    assert body["assignedVendorId"] == str(vendor.id)


def test_approve_can_override_the_customers_selection(client, make_auth_header, db_session, site):
    customer_pick = _make_vendor(db_session, name="Customer's Pick")
    admin_pick = _make_vendor(db_session, name="Admin's Pick")
    assessment = _seed_pending_assessment(db_session, site.id, customer_selected_vendor_id=customer_pick.id)

    response = client.post(
        f"/app/admin/assessments/{assessment.id}/approve",
        json={"vendorId": str(admin_pick.id)},
        headers=_admin_headers(make_auth_header),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["customerSelectedVendorId"] == str(customer_pick.id)
    assert body["assignedVendorId"] == str(admin_pick.id)
    assert body["customerSelectedVendorId"] != body["assignedVendorId"]


# --------------------------------------------------------------------- #
# reassign
# --------------------------------------------------------------------- #


def test_reassign_moves_the_same_job_to_a_new_vendor(client, make_auth_header, db_session, site):
    old_vendor = _make_vendor(db_session, name="Old Vendor")
    new_vendor = _make_vendor(db_session, name="New Vendor")
    assessment = _seed_pending_assessment(db_session, site.id)

    approve = client.post(
        f"/app/admin/assessments/{assessment.id}/approve",
        json={"vendorId": str(old_vendor.id)},
        headers=_admin_headers(make_auth_header),
    )
    assert approve.status_code == 200
    job_id = approve.json()["vendorJobId"]

    reassign = client.post(
        f"/app/admin/assessments/{assessment.id}/reassign",
        json={"vendorId": str(new_vendor.id)},
        headers=_admin_headers(make_auth_header),
    )
    assert reassign.status_code == 200
    body = reassign.json()
    assert body["assignedVendorId"] == str(new_vendor.id)
    assert body["vendorJobId"] == job_id  # same job, not a new one

    job = db_session.get(VendorJobRow, job_id)
    assert str(job.vendor_id) == str(new_vendor.id)
    assert str(old_vendor.id) in [str(v) for v in job.previous_vendor_ids]
    assert job.status == "queued"


def test_reassign_requires_the_assessment_to_already_be_approved(client, make_auth_header, db_session, site):
    vendor = _make_vendor(db_session)
    assessment = _seed_pending_assessment(db_session, site.id)  # never approved

    response = client.post(
        f"/app/admin/assessments/{assessment.id}/reassign",
        json={"vendorId": str(vendor.id)},
        headers=_admin_headers(make_auth_header),
    )
    assert response.status_code == 409


def test_reassign_rejects_an_unverified_vendor(client, make_auth_header, db_session, site):
    good_vendor = _make_vendor(db_session)
    unverified = _make_vendor(db_session, name="Unverified", verification_status="pending")
    assessment = _seed_pending_assessment(db_session, site.id)
    client.post(
        f"/app/admin/assessments/{assessment.id}/approve",
        json={"vendorId": str(good_vendor.id)},
        headers=_admin_headers(make_auth_header),
    )

    response = client.post(
        f"/app/admin/assessments/{assessment.id}/reassign",
        json={"vendorId": str(unverified.id)},
        headers=_admin_headers(make_auth_header),
    )
    assert response.status_code == 409


# --------------------------------------------------------------------- #
# audit log + customer notifications (User -> Vendor -> Super Admin
# controlled workflow — spec sections 4, 7, 10)
# --------------------------------------------------------------------- #


def test_approve_writes_a_structured_audit_row_and_notifies_the_customer(client, make_auth_header, db_session, site):
    customer, _customer_headers = _make_customer(db_session)
    vendor = _make_vendor(db_session)
    assessment = _seed_pending_assessment(db_session, site.id, raised_by_user_id=customer.id)

    response = client.post(
        f"/app/admin/assessments/{assessment.id}/approve",
        json={"vendorId": str(vendor.id)},
        headers=_admin_headers(make_auth_header),
    )
    assert response.status_code == 200, response.json()

    rows = audit_repo.list_audit_log(db_session, action="assessment.approved")
    row = next(r for r in rows if r.target == assessment.id)
    assert row.entity_type == "assessment"
    assert row.project_id == site.id
    assert row.survey_id == assessment.id
    assert row.customer_id == str(customer.id)
    assert row.vendor_id == str(vendor.id)
    assert row.previous_value == {"reviewStatus": "pending"}
    assert row.new_value["reviewStatus"] == "approved"

    notes = notifications_repo.list_for_user(db_session, customer.id)
    assert any(n.kind == "vendor_request_approved" for n in notes)


def test_reject_requires_a_reason_and_notifies_the_customer(client, make_auth_header, db_session, site):
    customer, _customer_headers = _make_customer(db_session)
    assessment = _seed_pending_assessment(db_session, site.id, raised_by_user_id=customer.id)

    missing_reason = client.post(
        f"/app/admin/assessments/{assessment.id}/reject",
        json={"reason": ""},
        headers=_admin_headers(make_auth_header),
    )
    assert missing_reason.status_code == 422

    response = client.post(
        f"/app/admin/assessments/{assessment.id}/reject",
        json={"reason": "Roof shading too severe"},
        headers=_admin_headers(make_auth_header),
    )
    assert response.status_code == 200, response.json()

    rows = audit_repo.list_audit_log(db_session, action="assessment.rejected")
    row = next(r for r in rows if r.target == assessment.id)
    assert row.reason == "Roof shading too severe"
    assert row.customer_id == str(customer.id)

    notes = notifications_repo.list_for_user(db_session, customer.id)
    assert any(n.kind == "vendor_request_rejected" for n in notes)


def test_reassign_records_an_optional_reason(client, make_auth_header, db_session, site):
    old_vendor = _make_vendor(db_session, name="Old Vendor")
    new_vendor = _make_vendor(db_session, name="New Vendor")
    assessment = _seed_pending_assessment(db_session, site.id)
    client.post(
        f"/app/admin/assessments/{assessment.id}/approve",
        json={"vendorId": str(old_vendor.id)},
        headers=_admin_headers(make_auth_header),
    )

    response = client.post(
        f"/app/admin/assessments/{assessment.id}/reassign",
        json={"vendorId": str(new_vendor.id), "reason": "Old vendor unavailable"},
        headers=_admin_headers(make_auth_header),
    )
    assert response.status_code == 200, response.json()

    rows = audit_repo.list_audit_log(db_session, action="assessment.reassigned")
    row = next(r for r in rows if r.target == assessment.id)
    assert row.reason == "Old vendor unavailable"
    assert row.previous_value == {"vendorId": str(old_vendor.id)}
    assert row.new_value == {"vendorId": str(new_vendor.id)}
