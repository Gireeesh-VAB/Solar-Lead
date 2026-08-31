"""Owner: keerthana (Vendor domain, customer-account admin, jurisdictions).

Exercises all 12 /app/vendor/* endpoints against a real Postgres-backed
session (db_session, rolled back after each test) — same pattern
test_auth.py already uses for the /app/* surface.

There is no create_job() endpoint (see repositories/vendors.py's
docstring — a real, flagged gap, not an oversight), so every test seeds
a VendorRow/VendorJobRow/VendorPayoutRow directly against the ORM
rather than going through the API.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from solarfit.db import get_session
from solarfit.main import app
from solarfit.repositories import sites as sites_repo
from solarfit.repositories.vendors import (
    VendorAccuracyHistoryRow,
    VendorJobRow,
    VendorPayoutRow,
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


def test_submit_job_sets_submitted_at(client, vendor_auth_header, job):
    r = client.post(f"/app/vendor/jobs/{job.id}/submit", headers=vendor_auth_header)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "submitted"
    assert body["submittedAt"] is not None


def test_decline_job_removes_it(client, vendor_auth_header, job, db_session):
    r = client.post(f"/app/vendor/jobs/{job.id}/decline", headers=vendor_auth_header)
    assert r.status_code == 200
    assert r.json()["id"] == str(job.id)

    follow_up = client.get(f"/app/vendor/jobs/{job.id}", headers=vendor_auth_header)
    assert follow_up.status_code == 404


# --------------------------------------------------------------------- #
# profile
# --------------------------------------------------------------------- #


def test_get_profile(client, vendor_auth_header, vendor, db_session):
    db_session.add(VendorAccuracyHistoryRow(vendor_id=vendor.id, label="Q1", score=0.9))
    db_session.flush()

    r = client.get("/app/vendor/profile", headers=vendor_auth_header)
    assert r.status_code == 200
    body = r.json()
    assert body["vendorId"] == str(vendor.id)
    assert body["name"] == "Acme Surveys"
    assert body["serviceArea"] == {"region": "Telangana", "districts": ["Hyderabad", "Rangareddy"]}
    assert body["payoutMethod"] == {"type": "UPI", "maskedAccount": "acme@upi"}
    assert body["accuracyTrend"] == [{"label": "Q1", "score": 0.9}]


def test_update_availability(client, vendor_auth_header):
    r = client.patch("/app/vendor/profile/availability", json={"available": False}, headers=vendor_auth_header)
    assert r.status_code == 200
    assert r.json()["availability"] is False


# --------------------------------------------------------------------- #
# payouts / earnings / submissions
# --------------------------------------------------------------------- #


def test_list_payouts(client, vendor_auth_header, vendor, job, db_session):
    db_session.add(
        VendorPayoutRow(vendor_id=vendor.id, job_id=job.id, amount=1500, status="paid", date=datetime.now(UTC), method="UPI")
    )
    db_session.flush()

    r = client.get("/app/vendor/payouts", headers=vendor_auth_header)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["amount"] == 1500
    assert body[0]["status"] == "paid"


def test_earnings_summary(client, vendor_auth_header, vendor, db_session):
    db_session.add(VendorPayoutRow(vendor_id=vendor.id, amount=500, status="pending", date=datetime.now(UTC), method="UPI"))
    db_session.add(VendorPayoutRow(vendor_id=vendor.id, amount=1000, status="paid", date=datetime.now(UTC), method="UPI"))
    db_session.add(
        VendorPayoutRow(vendor_id=vendor.id, amount=250, status="disputed", date=datetime.now(UTC), method="Bank transfer")
    )
    db_session.flush()

    r = client.get("/app/vendor/earnings-summary", headers=vendor_auth_header)
    assert r.status_code == 200
    body = r.json()
    assert body["pendingInr"] == 500
    assert body["paidInr"] == 1000
    assert body["disputedInr"] == 250
    assert body["jobsCompletedThisWeek"] == 0


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


def test_save_shading_notes(client, vendor_auth_header, job):
    r = client.patch(
        f"/app/vendor/jobs/{job.id}/shading-notes",
        json={"notes": "Tree shading on the east side after 3pm."},
        headers=vendor_auth_header,
    )
    assert r.status_code == 200
    assert r.json()["shadingNotes"] == "Tree shading on the east side after 3pm."
