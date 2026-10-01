"""Owner: karthik (App Platform & Foundation).

Tests for repositories/notifications.py and routers/app_notifications.py,
plus the vendor/admin notification call sites wired into
routers/app_assessments.py (approve/reassign), routers/app_admin_vendors.py
(verification reject), and routers/app_vendor.py (job submit).
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from solarfit.db import get_session
from solarfit.main import app
from solarfit.repositories import notifications as repo
from solarfit.repositories import sites as sites_repo
from solarfit.repositories.vendors import VendorJobRow, VendorRow

LON, LAT = 78.4867, 17.3850


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# --------------------------------------------------------------------- #
# repositories/notifications.py
# --------------------------------------------------------------------- #


def test_list_for_user_returns_only_that_users_notifications(db_session):
    import uuid

    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    repo.create_notification(db_session, user_id=user_a, kind="job_assigned", title="For A")
    repo.create_notification(db_session, user_id=user_b, kind="job_assigned", title="For B")

    rows = repo.list_for_user(db_session, user_a)
    assert [r.title for r in rows] == ["For A"]


def test_list_for_user_orders_unread_first_then_newest(db_session):
    import uuid

    user_id = uuid.uuid4()
    first = repo.create_notification(db_session, user_id=user_id, kind="k", title="First")
    second = repo.create_notification(db_session, user_id=user_id, kind="k", title="Second")
    repo.mark_read(db_session, first.id, user_id)

    rows = repo.list_for_user(db_session, user_id)
    assert [r.title for r in rows] == ["Second", "First"]


def test_mark_read_scoped_to_owning_user(db_session):
    import uuid

    owner = uuid.uuid4()
    other = uuid.uuid4()
    note = repo.create_notification(db_session, user_id=owner, kind="k", title="Mine")

    assert repo.mark_read(db_session, note.id, other) is None
    updated = repo.mark_read(db_session, note.id, owner)
    assert updated is not None
    assert updated.read_at is not None


# --------------------------------------------------------------------- #
# routers/app_notifications.py
# --------------------------------------------------------------------- #


def test_list_my_notifications_requires_auth(client):
    r = client.get("/app/notifications")
    assert r.status_code == 401


def test_list_my_notifications_scoped_to_caller(client, make_auth_header, db_session):
    headers_a = make_auth_header(role="customer")
    headers_b = make_auth_header(role="customer")

    me_a = client.get("/app/auth/me", headers=headers_a).json()
    repo.create_notification(db_session, user_id=me_a["id"], kind="k", title="For A")

    r = client.get("/app/notifications", headers=headers_a)
    assert r.status_code == 200
    assert [n["title"] for n in r.json()] == ["For A"]

    r = client.get("/app/notifications", headers=headers_b)
    assert r.json() == []


def test_mark_notification_read(client, make_auth_header, db_session):
    headers = make_auth_header(role="customer")
    me = client.get("/app/auth/me", headers=headers).json()
    note = repo.create_notification(db_session, user_id=me["id"], kind="k", title="For me")

    r = client.post(f"/app/notifications/{note.id}/read", headers=headers)
    assert r.status_code == 200
    assert r.json()["readAt"] is not None


def test_mark_unknown_notification_is_404(client, make_auth_header):
    headers = make_auth_header(role="customer")
    r = client.post(
        "/app/notifications/00000000-0000-0000-0000-000000000000/read", headers=headers
    )
    assert r.status_code == 404


# --------------------------------------------------------------------- #
# call sites
# --------------------------------------------------------------------- #


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


def test_verification_reject_notifies_vendor_users(client, make_auth_header, db_session):
    vendor = _vendor(db_session, verification_status="pending")
    vendor_login = make_auth_header(role="vendor", vendor_id=vendor.id)
    admin_headers = make_auth_header(role="admin")

    r = client.post(f"/app/admin/vendors/{vendor.id}/verification/reject", headers=admin_headers)
    assert r.status_code == 200

    notes = client.get("/app/notifications", headers=vendor_login)
    assert any(n["kind"] == "vendor_verification_rejected" for n in notes.json())


def test_verification_reject_respects_preference_toggle(client, make_auth_header, db_session):
    vendor = _vendor(
        db_session,
        verification_status="pending",
        notification_preferences={"submission_and_payout_updates": False},
    )
    vendor_login = make_auth_header(role="vendor", vendor_id=vendor.id)
    admin_headers = make_auth_header(role="admin")

    client.post(f"/app/admin/vendors/{vendor.id}/verification/reject", headers=admin_headers)

    notes = client.get("/app/notifications", headers=vendor_login)
    assert notes.json() == []


def test_job_submit_notifies_admins(client, make_auth_header, db_session):
    site = sites_repo.create(
        db_session,
        site_type="ROOFTOP_RESIDENTIAL",
        name="Test Rooftop",
        owner_org="Test Org",
        jurisdiction="IN-TG",
        centroid={"type": "Point", "coordinates": [LON, LAT]},
    )
    vendor = _vendor(db_session)
    job = VendorJobRow(
        site_id=site.id,
        vendor_id=vendor.id,
        status="in_progress",
        district="Hyderabad",
        state="Telangana",
        deadline=datetime.now(UTC) + timedelta(days=3),
        payout_inr=1500,
        requirements=[],
    )
    db_session.add(job)
    db_session.flush()

    vendor_headers = make_auth_header(role="vendor", vendor_id=vendor.id)
    admin_headers = make_auth_header(role="admin")

    r = client.post(f"/app/vendor/jobs/{job.id}/submit", headers=vendor_headers)
    assert r.status_code == 200

    notes = client.get("/app/notifications", headers=admin_headers)
    assert any(n["kind"] == "job_submitted" for n in notes.json())
