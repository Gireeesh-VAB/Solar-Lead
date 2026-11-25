"""Owner: keerthana (Vendor domain, customer-account admin, jurisdictions).

Exercises the /app/vendor/* endpoints against a real Postgres-backed
session (db_session, rolled back after each test) — same pattern
test_auth.py already uses for the /app/* surface.

There is no create_job() endpoint (see repositories/vendors.py's
docstring — a real, flagged gap, not an oversight), so every test seeds
a VendorRow/VendorJobRow directly against the ORM rather than going
through the API.

The vendor-facing /payouts and /earnings-summary endpoints (and their
tests) were removed along with the vendor portal's Earnings feature.
The admin-facing GET /admin/vendors/{id}/payouts is untouched — see
test_app_admin_vendors.py.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from solarfit.db import get_session
from solarfit.main import app
from solarfit.repositories import sites as sites_repo
from solarfit.repositories.vendors import (
    VendorJobRow,
    VendorRow,
)

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


@pytest.fixture
def vendor(db_session):
    row = VendorRow(
        name="Acme Surveys",
        verification_status="verified",
        availability=True,
        accuracy_score=0.92,
        service_area={"region": "Telangana", "districts": ["Hyderabad", "Rangareddy"]},
        payout_method_type="UPI",
        payout_masked_account="acme@upi",
        documents=["license.pdf"],
    )
    db_session.add(row)
    db_session.flush()
    return row


@pytest.fixture
def vendor_auth_header(make_auth_header, vendor):
    return make_auth_header(role="vendor", vendor_id=vendor.id)


@pytest.fixture
def job(db_session, site, vendor):
    row = VendorJobRow(
        site_id=site.id,
        vendor_id=vendor.id,
        status="queued",
        district="Hyderabad",
        state="Telangana",
        deadline=datetime.now(UTC) + timedelta(days=3),
        payout_inr=1500,
        requirements=["ladder", "drone"],
        distance_km=12.5,
    )
    db_session.add(row)
    db_session.flush()
    return row


def test_requires_auth(client):
    r = client.get("/app/vendor/jobs")
    assert r.status_code == 401


def test_requires_vendor_role(client, make_auth_header):
    r = client.get("/app/vendor/jobs", headers=make_auth_header(role="customer"))
    assert r.status_code == 403


def test_vendor_with_no_linked_profile_gets_404(client, make_auth_header):
    r = client.get("/app/vendor/jobs", headers=make_auth_header(role="vendor"))
    assert r.status_code == 404


# --------------------------------------------------------------------- #
# jobs
# --------------------------------------------------------------------- #


def test_list_jobs(client, vendor_auth_header, job):
    r = client.get("/app/vendor/jobs", headers=vendor_auth_header)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    j = body[0]
    assert j["id"] == str(job.id)
    assert j["siteId"] == str(job.site_id)
    assert j["siteName"] == "Test Rooftop"
    assert j["siteType"] == "ROOFTOP_RESIDENTIAL"
    assert j["district"] == "Hyderabad"
    assert j["status"] == "queued"
    assert j["requirements"] == ["ladder", "drone"]
    assert "assignedAt" in j


def test_list_jobs_filters_by_status(client, vendor_auth_header, job):
    r = client.get("/app/vendor/jobs", params={"status": "accepted"}, headers=vendor_auth_header)
    assert r.status_code == 200
    assert r.json() == []


def test_get_job(client, vendor_auth_header, job):
    r = client.get(f"/app/vendor/jobs/{job.id}", headers=vendor_auth_header)
    assert r.status_code == 200
    assert r.json()["id"] == str(job.id)


def test_get_job_not_owned_by_caller_is_404(client, make_auth_header, db_session, job):
    other_vendor = VendorRow(
        name="Other Vendor",
        payout_method_type="UPI",
        payout_masked_account="other@upi",
    )
    db_session.add(other_vendor)
    db_session.flush()
    header = make_auth_header(role="vendor", vendor_id=other_vendor.id)
    r = client.get(f"/app/vendor/jobs/{job.id}", headers=header)
    assert r.status_code == 404


def test_accept_job(client, vendor_auth_header, job):
    r = client.post(f"/app/vendor/jobs/{job.id}/accept", headers=vendor_auth_header)
    assert r.status_code == 200
    assert r.json()["status"] == "accepted"


def test_start_job(client, vendor_auth_header, job):
    r = client.post(f"/app/vendor/jobs/{job.id}/start", headers=vendor_auth_header)
    assert r.status_code == 200
    assert r.json()["status"] == "in_progress"


@pytest.mark.parametrize("stale_status", ["sla_at_risk", "overdue"])
def test_start_job_from_sla_at_risk_or_overdue(client, vendor_auth_header, db_session, job, stale_status):
    """A job the vendor accepted but never started, then the SLA sweep
    (repositories/vendors.py::sweep_vendor_job_sla) marked sla_at_risk or
    overdue, must still be startable — these two statuses previously only
    allowed a transition to "submitted", so a job in this exact state
    could never be started at all (POST /start 409'd forever)."""
    job.status = stale_status
    db_session.flush()

    r = client.post(f"/app/vendor/jobs/{job.id}/start", headers=vendor_auth_header)
    assert r.status_code == 200
    assert r.json()["status"] == "in_progress"


def test_submit_job_sets_submitted_at(client, vendor_auth_header, job):
    r = client.post(f"/app/vendor/jobs/{job.id}/submit", headers=vendor_auth_header)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "submitted"
    assert body["submittedAt"] is not None


def test_accept_already_submitted_job_is_rejected(client, vendor_auth_header, job, db_session):
    """A completed, already-submitted survey must not be re-acceptable
    or declinable — doing so used to silently overwrite the terminal
    "submitted" status (and everything an admin/customer sees for it)
    with "accepted" then "declined", with no trace of the real
    submission left."""
    job.status = "submitted"
    db_session.flush()

    r = client.post(f"/app/vendor/jobs/{job.id}/accept", headers=vendor_auth_header)
    assert r.status_code == 409

    r = client.post(f"/app/vendor/jobs/{job.id}/decline", headers=vendor_auth_header)
    assert r.status_code == 409

    follow_up = client.get(f"/app/vendor/jobs/{job.id}", headers=vendor_auth_header)
    assert follow_up.json()["status"] == "submitted"


def test_decline_job_preserves_it_with_a_declined_status(client, vendor_auth_header, job, db_session):
    """A vendor declining a job must not lose it — it stays visible (to
    this same vendor, and to an admin who can reassign it) with a real
    "declined" status rather than being deleted."""
    r = client.post(f"/app/vendor/jobs/{job.id}/decline", headers=vendor_auth_header)
    assert r.status_code == 200
    assert r.json()["id"] == str(job.id)
    assert r.json()["status"] == "declined"

    follow_up = client.get(f"/app/vendor/jobs/{job.id}", headers=vendor_auth_header)
    assert follow_up.status_code == 200
    assert follow_up.json()["status"] == "declined"


def test_submit_declined_job_is_rejected(client, vendor_auth_header, job, db_session):
    """A declined job is terminal — repositories/vendors.py::
    VENDOR_JOB_TRANSITIONS["declined"] is empty, so it can never be
    "submitted" back into existence."""
    job.status = "declined"
    db_session.flush()

    r = client.post(f"/app/vendor/jobs/{job.id}/submit", headers=vendor_auth_header)
    assert r.status_code == 409

    follow_up = client.get(f"/app/vendor/jobs/{job.id}", headers=vendor_auth_header)
    assert follow_up.json()["status"] == "declined"


def test_decline_already_declined_job_is_rejected(client, vendor_auth_header, job, db_session):
    """Same terminal rule for decline itself — declining twice is not a
    no-op, it's an illegal transition."""
    job.status = "declined"
    db_session.flush()

    r = client.post(f"/app/vendor/jobs/{job.id}/decline", headers=vendor_auth_header)
    assert r.status_code == 409


# --------------------------------------------------------------------- #
# profile
# --------------------------------------------------------------------- #


def test_get_profile(client, vendor_auth_header, vendor):
    r = client.get("/app/vendor/profile", headers=vendor_auth_header)
    assert r.status_code == 200
    body = r.json()
    assert body["vendorId"] == str(vendor.id)
    assert body["name"] == "Acme Surveys"
    assert body["serviceArea"] == {"region": "Telangana", "districts": ["Hyderabad", "Rangareddy"]}
    assert body["payoutMethod"] == {"type": "UPI", "maskedAccount": "acme@upi"}
    assert body["accuracyScore"] == 0.92
    # legalName/contactPhone/contactEmail are additive Settings-page
    # fields — None here since the `vendor` fixture never sets them.
    assert body["legalName"] is None
    assert body["contactPhone"] is None
    assert body["contactEmail"] is None


def test_update_availability(client, vendor_auth_header):
    r = client.patch("/app/vendor/profile/availability", json={"available": False}, headers=vendor_auth_header)
    assert r.status_code == 200
    assert r.json()["availability"] is False


# --------------------------------------------------------------------- #
# notification preferences
# --------------------------------------------------------------------- #


def test_get_notification_preferences_defaults_to_all_on(client, vendor_auth_header):
    """The `vendor` fixture never sets notification_preferences, so the
    ORM's own default=dict gives an empty {} — the router must still
    report every toggle "on", matching what the migration's
    server_default gives a real (non-test) row."""
    r = client.get("/app/vendor/profile/notification-preferences", headers=vendor_auth_header)
    assert r.status_code == 200
    assert r.json() == {
        "newJobAssignment": True,
        "jobDeadlineReminders": True,
        "jobReassignment": True,
        "submissionAndPayoutUpdates": True,
        "disputeUpdates": True,
        "installationUpdates": True,
    }


def test_update_notification_preferences_persists(client, vendor_auth_header):
    payload = {
        "newJobAssignment": False,
        "jobDeadlineReminders": True,
        "jobReassignment": False,
        "submissionAndPayoutUpdates": True,
        "disputeUpdates": False,
        "installationUpdates": True,
    }
    r = client.patch("/app/vendor/profile/notification-preferences", json=payload, headers=vendor_auth_header)
    assert r.status_code == 200
    assert r.json() == payload

    follow_up = client.get("/app/vendor/profile/notification-preferences", headers=vendor_auth_header)
    assert follow_up.json() == payload


def test_notification_preferences_requires_auth(client):
    r = client.get("/app/vendor/profile/notification-preferences")
    assert r.status_code == 401


def test_notification_preferences_requires_vendor_role(client, make_auth_header):
    r = client.get(
        "/app/vendor/profile/notification-preferences", headers=make_auth_header(role="customer")
    )
    assert r.status_code == 403


# --------------------------------------------------------------------- #
# submissions
# --------------------------------------------------------------------- #


def test_list_submissions_only_returns_submitted(client, vendor_auth_header, job, db_session):
    submitted = VendorJobRow(
        site_id=job.site_id,
        vendor_id=job.vendor_id,
        status="submitted",
        district="Hyderabad",
        state="Telangana",
        deadline=datetime.now(UTC) + timedelta(days=1),
        payout_inr=800,
        submitted_at=datetime.now(UTC),
    )
    db_session.add(submitted)
    db_session.flush()

    r = client.get("/app/vendor/submissions", headers=vendor_auth_header)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["id"] == str(submitted.id)


def test_dispute_submission(client, vendor_auth_header, job, db_session):
    job.status = "submitted"
    job.submitted_at = datetime.now(UTC)
    db_session.flush()

    r = client.post(f"/app/vendor/submissions/{job.id}/dispute", json={"reason": "measured capacity looks wrong"}, headers=vendor_auth_header)
    assert r.status_code == 200
    body = r.json()
    assert body["disputeStatus"] == "open"
    assert body["disputeReason"] == "measured capacity looks wrong"


def test_upload_panorama_photo(client, vendor_auth_header, job):
    r = client.patch(
        f"/app/vendor/jobs/{job.id}/panorama",
        json={"dataUrl": "data:image/png;base64,abc123"},
        headers=vendor_auth_header,
    )
    assert r.status_code == 200
    assert r.json()["panoramaPhotoDataUrl"] == "data:image/png;base64,abc123"


def test_upload_panorama_photo_not_owned_by_caller_is_404(client, make_auth_header, db_session, job):
    other_vendor = VendorRow(
        name="Other Vendor",
        payout_method_type="UPI",
        payout_masked_account="other@upi",
    )
    db_session.add(other_vendor)
    db_session.flush()
    header = make_auth_header(role="vendor", vendor_id=other_vendor.id)
    r = client.patch(
        f"/app/vendor/jobs/{job.id}/panorama",
        json={"dataUrl": "data:image/png;base64,abc123"},
        headers=header,
    )
    assert r.status_code == 404


def _square_around(lon: float, lat: float, half_deg: float = 0.0002) -> list[dict]:
    return [
        {"lat": lat + half_deg, "lng": lon - half_deg},
        {"lat": lat + half_deg, "lng": lon + half_deg},
        {"lat": lat - half_deg, "lng": lon + half_deg},
        {"lat": lat - half_deg, "lng": lon - half_deg},
    ]


def test_submit_field_boundary(client, vendor_auth_header, job, db_session):
    r = client.patch(
        f"/app/vendor/jobs/{job.id}/boundary",
        json={"points": _square_around(LON, LAT)},
        headers=vendor_auth_header,
    )
    assert r.status_code == 200

    site = sites_repo.get(db_session, job.site_id)
    assert site is not None
    # field_measured (GEO-09's highest-trust source, base 0.95) — never
    # the manual_polygon confidence a customer's own desk-bound edit gets.
    assert site.geometry_source == "field_measured"
    assert site.geometry_confidence == pytest.approx(0.95)


def test_submit_field_boundary_rejects_self_intersecting_trace(client, vendor_auth_header, job):
    d = 0.0002
    bowtie = [
        {"lat": LAT + d, "lng": LON - d},
        {"lat": LAT - d, "lng": LON + d},
        {"lat": LAT + d, "lng": LON + d},
        {"lat": LAT - d, "lng": LON - d},
    ]
    r = client.patch(f"/app/vendor/jobs/{job.id}/boundary", json={"points": bowtie}, headers=vendor_auth_header)
    assert r.status_code == 422


def test_submit_field_boundary_rejects_fewer_than_3_points(client, vendor_auth_header, job):
    r = client.patch(
        f"/app/vendor/jobs/{job.id}/boundary",
        json={"points": _square_around(LON, LAT)[:2]},
        headers=vendor_auth_header,
    )
    assert r.status_code == 422


def test_submit_field_boundary_not_owned_by_caller_is_404(client, make_auth_header, db_session, job):
    other_vendor = VendorRow(
        name="Other Vendor",
        payout_method_type="UPI",
        payout_masked_account="other@upi",
    )
    db_session.add(other_vendor)
    db_session.flush()
    header = make_auth_header(role="vendor", vendor_id=other_vendor.id)
    r = client.patch(
        f"/app/vendor/jobs/{job.id}/boundary",
        json={"points": _square_around(LON, LAT)},
        headers=header,
    )
    assert r.status_code == 404


def test_save_shading_notes(client, vendor_auth_header, job):
    r = client.patch(
        f"/app/vendor/jobs/{job.id}/shading-notes",
        json={"notes": "Tree shading on the east side after 3pm."},
        headers=vendor_auth_header,
    )
    assert r.status_code == 200
    assert r.json()["shadingNotes"] == "Tree shading on the east side after 3pm."


# --------------------------------------------------------------------- #
# audit trail — User -> Vendor -> Super Admin controlled workflow
# (spec section 6, "Complete Vendor Activity / Audit Logging")
# --------------------------------------------------------------------- #


def test_accept_job_writes_an_audit_row_scoped_to_vendor_and_project(client, vendor_auth_header, job, db_session, site, vendor):
    from solarfit.repositories import audit as audit_repo

    r = client.post(f"/app/vendor/jobs/{job.id}/accept", headers=vendor_auth_header)
    assert r.status_code == 200

    rows = audit_repo.list_audit_log(db_session, action="vendor_job.accepted")
    row = next(row for row in rows if row.target == str(job.id))
    assert row.entity_type == "vendor_job"
    assert row.project_id == str(site.id)
    assert row.vendor_id == str(vendor.id)
    assert row.actor_role == "vendor"
    assert row.previous_value == {"status": "queued"}
    assert row.new_value == {"status": "accepted"}


def test_declining_a_job_notifies_every_admin(client, vendor_auth_header, job, db_session, make_auth_header):
    from solarfit.repositories import notifications as notifications_repo

    admin_headers = make_auth_header(role="admin")
    # The header itself doesn't expose the created admin's id — re-derive
    # it from the token the same way current_user() does, rather than
    # adding a second helper just for this one test.
    import jwt as pyjwt

    from solarfit.config import get_settings

    token = admin_headers["Authorization"].removeprefix("Bearer ")
    admin_id = pyjwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])["sub"]

    r = client.post(f"/app/vendor/jobs/{job.id}/decline", headers=vendor_auth_header)
    assert r.status_code == 200

    notes = notifications_repo.list_for_user(db_session, admin_id)
    assert any(n.kind == "job_declined" for n in notes)
