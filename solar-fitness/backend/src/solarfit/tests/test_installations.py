"""Tests for the post-quotation installation pipeline — the customer's
quotation acceptance (routers/app_checks.py), the vendor's stage/QC/
photo/commissioning capture (routers/app_vendor_installations.py) and
the admin's two approval gates (routers/app_admin_installations.py).

Postgres-backed (db_session, rolled back per test) rather than the
in-memory SQLite fixture: installation_projects FKs sites/vendors/
vendor_jobs and those tables use UUID/JSONB columns. Same rationale and
fixture shape as test_app_assessments_enquiry.py.
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from solarfit.auth_users import create_access_token, hash_password
from solarfit.db import get_session
from solarfit.main import app
from solarfit.repositories import installations as installations_repo
from solarfit.repositories import sites as sites_repo
from solarfit.repositories import users as users_repo
from solarfit.repositories.assessments import AssessmentRow
from solarfit.repositories.vendors import VendorRow

LON, LAT = 78.4867, 17.3850


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def vendor(db_session):
    row = VendorRow(
        name="Acme Solar",
        verification_status="verified",
        availability=True,
        accuracy_score=0.9,
        service_area={"region": "Telangana", "districts": ["Hyderabad"]},
        payout_method_type="UPI",
        payout_masked_account="acme@upi",
    )
    db_session.add(row)
    db_session.flush()
    return row


@pytest.fixture
def customer(db_session):
    """A customer plus a check they own. app_checks.py scopes everything
    by the synthetic owner_org f"individual:{user.id}", so the site has
    to be created with exactly that value or every route 404s."""
    user = users_repo.create_user(
        db_session,
        email=f"buyer-{datetime.now(UTC).timestamp()}@example.com",
        password_hash=hash_password("Test1234!"),
        name="Buyer",
        role="customer",
    )
    owner_org = f"individual:{user.id}"
    site = sites_repo.create(
        db_session,
        site_type="ROOFTOP_RESIDENTIAL",
        name="Test Rooftop",
        owner_org=owner_org,
        jurisdiction="IN-TG",
        centroid={"type": "Point", "coordinates": [LON, LAT]},
    )
    headers = {"Authorization": f"Bearer {create_access_token(str(user.id), user.role)}"}
    return user, site, headers


def _seed_assessment(db_session, site_id: str, owner_org: str, *, review_status: str, vendor_id=None):
    row = AssessmentRow(
        id=f"as-{site_id}",
        site_id=site_id,
        owner_org=owner_org,
        site_type="ROOFTOP_RESIDENTIAL",
        verdict="SUITABLE",
        score=0.8,
        confidence=0.75,
        review_status=review_status,
        assigned_vendor_id=vendor_id,
        binding_constraint="net_metering_cap",
        reasons=["net_metering_cap is binding"],
        limitations="Pre-feasibility estimate only.",
        capacity={"recommended_kwp": 4.5, "ceilings": []},
        boundary={"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [0, 0]]]},
        usable_area_m2=80.0,
        cache_hit=False,
        engine_version="test",
        constraint_pack_version="rooftop_v1",
        created_at=datetime.now(UTC),
    )
    db_session.add(row)
    db_session.flush()
    return row


def _vendor_headers(db_session, vendor_row):
    user = users_repo.create_user(
        db_session,
        email=f"crew-{datetime.now(UTC).timestamp()}@example.com",
        password_hash=hash_password("Test1234!"),
        name="Crew",
        role="vendor",
        vendor_id=vendor_row.id,
    )
    return {"Authorization": f"Bearer {create_access_token(str(user.id), user.role)}"}


def _admin_headers(make_auth_header):
    return make_auth_header(role="admin")


# --------------------------------------------------------------------- #
# the missing trigger: customer accepts the quotation
# --------------------------------------------------------------------- #


def test_accept_quotation_opens_an_installation_project(client, db_session, customer, vendor):
    _user, site, headers = customer
    _seed_assessment(db_session, site.id, site.owner_org, review_status="approved", vendor_id=vendor.id)

    response = client.post(f"/app/checks/{site.id}/accept-quotation", headers=headers)
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["status"] == "created"
    assert body["stageIndex"] == 0
    assert body["stages"][0] == "created"
    assert body["stages"][-1] == "completed"
    assert body["approvedCapacityKwp"] == 4.5

    project = installations_repo.get_project_for_site(db_session, site.id)
    assert project is not None
    assert str(project.assigned_vendor_id) == str(vendor.id)


def test_accept_quotation_requires_an_approved_assessment(client, db_session, customer):
    _user, site, headers = customer
    _seed_assessment(db_session, site.id, site.owner_org, review_status="pending")

    response = client.post(f"/app/checks/{site.id}/accept-quotation", headers=headers)
    assert response.status_code == 409
    assert "not approved" in response.json()["detail"]


def test_accept_quotation_is_not_repeatable(client, db_session, customer, vendor):
    _user, site, headers = customer
    _seed_assessment(db_session, site.id, site.owner_org, review_status="approved", vendor_id=vendor.id)

    assert client.post(f"/app/checks/{site.id}/accept-quotation", headers=headers).status_code == 201
    second = client.post(f"/app/checks/{site.id}/accept-quotation", headers=headers)
    assert second.status_code == 409


def test_accept_quotation_404s_without_an_assessment(client, customer):
    _user, site, headers = customer
    response = client.post(f"/app/checks/{site.id}/accept-quotation", headers=headers)
    assert response.status_code == 404


def test_customer_installation_status_is_404_until_a_project_exists(client, customer):
    _user, site, headers = customer
    assert client.get(f"/app/checks/{site.id}/installation", headers=headers).status_code == 404


# --------------------------------------------------------------------- #
# vendor: stages, QC, photos
# --------------------------------------------------------------------- #


@pytest.fixture
def project(db_session, customer, vendor):
    _user, site, _headers = customer
    return installations_repo.create_project(
        db_session, site_id=site.id, approved_capacity_kwp=4.5, assigned_vendor_id=vendor.id
    )


def test_vendor_sees_only_its_own_projects(client, db_session, project, vendor):
    other = VendorRow(
        name="Other Solar",
        verification_status="verified",
        availability=True,
        accuracy_score=0.5,
        service_area={"region": "Telangana", "districts": []},
        payout_method_type="UPI",
        payout_masked_account="other@upi",
    )
    db_session.add(other)
    db_session.flush()

    mine = client.get("/app/vendor/installations", headers=_vendor_headers(db_session, vendor))
    assert mine.status_code == 200
    assert [p["id"] for p in mine.json()] == [project.id]

    theirs = client.get("/app/vendor/installations", headers=_vendor_headers(db_session, other))
    assert theirs.json() == []
    assert (
        client.get(
            f"/app/vendor/installations/{project.id}", headers=_vendor_headers(db_session, other)
        ).status_code
        == 404
    )


def test_vendor_advances_stages_and_stage_index_tracks(client, db_session, project, vendor):
    headers = _vendor_headers(db_session, vendor)
    response = client.patch(
        f"/app/vendor/installations/{project.id}/status",
        json={"status": "panels_installed", "panelModel": "Adani 540W"},
        headers=headers,
    )
    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["status"] == "panels_installed"
    assert body["stageIndex"] == installations_repo.INSTALLATION_STAGES.index("panels_installed")
    assert body["panelModel"] == "Adani 540W"


def test_vendor_cannot_mark_a_project_completed(client, db_session, project, vendor):
    response = client.patch(
        f"/app/vendor/installations/{project.id}/status",
        json={"status": "completed"},
        headers=_vendor_headers(db_session, vendor),
    )
    assert response.status_code == 409


def test_unknown_stage_is_rejected(client, db_session, project, vendor):
    response = client.patch(
        f"/app/vendor/installations/{project.id}/status",
        json={"status": "teleportation"},
        headers=_vendor_headers(db_session, vendor),
    )
    assert response.status_code == 422


def test_empty_qc_checklist_reads_back_as_every_item_unset(client, db_session, project, vendor):
    response = client.get(
        f"/app/vendor/installations/{project.id}/qc", headers=_vendor_headers(db_session, vendor)
    )
    assert response.status_code == 200
    checklist = response.json()["checklist"]
    assert set(checklist) == set(installations_repo.QC_CHECKLIST_ITEMS)
    assert all(v is None for v in checklist.values())
    assert response.json()["submittedAt"] is None


def test_vendor_saves_then_submits_the_qc_checklist(client, db_session, project, vendor):
    headers = _vendor_headers(db_session, vendor)
    saved = client.patch(
        f"/app/vendor/installations/{project.id}/qc",
        json={"checklist": {"panel_alignment": True, "waterproofing": False}, "notes": "wip"},
        headers=headers,
    )
    assert saved.status_code == 200
    assert saved.json()["checklist"]["panel_alignment"] is True
    assert saved.json()["submittedAt"] is None

    submitted = client.post(
        f"/app/vendor/installations/{project.id}/qc/submit",
        json={"checklist": {k: True for k in installations_repo.QC_CHECKLIST_ITEMS}},
        headers=headers,
    )
    assert submitted.status_code == 200
    assert submitted.json()["submittedAt"] is not None


def test_vendor_posts_a_geotagged_stage_photo(client, db_session, project, vendor):
    headers = _vendor_headers(db_session, vendor)
    response = client.post(
        f"/app/vendor/installations/{project.id}/photos",
        json={
            "stage": "mounting_installed",
            "dataUrl": "data:image/png;base64,iVBORw0KGgo=",
            "lat": LAT,
            "lng": LON,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.json()
    assert response.json()["lat"] == LAT
    listed = client.get(f"/app/vendor/installations/{project.id}/photos", headers=headers)
    assert len(listed.json()) == 1


# --------------------------------------------------------------------- #
# admin: the two approval gates
# --------------------------------------------------------------------- #


def test_admin_cannot_approve_an_unsubmitted_checklist(client, db_session, project, make_auth_header):
    response = client.post(
        f"/app/admin/installations/{project.id}/qc/approve", headers=_admin_headers(make_auth_header)
    )
    assert response.status_code == 409


def test_admin_approves_a_submitted_checklist_once(client, db_session, project, vendor, make_auth_header):
    client.post(
        f"/app/vendor/installations/{project.id}/qc/submit",
        json={"checklist": {k: True for k in installations_repo.QC_CHECKLIST_ITEMS}},
        headers=_vendor_headers(db_session, vendor),
    )
    admin = _admin_headers(make_auth_header)
    first = client.post(f"/app/admin/installations/{project.id}/qc/approve", headers=admin)
    assert first.status_code == 200, first.json()
    assert first.json()["approvedAt"] is not None
    assert client.post(f"/app/admin/installations/{project.id}/qc/approve", headers=admin).status_code == 409


def test_commissioning_runs_vendor_then_customer_then_admin(
    client, db_session, customer, project, vendor, make_auth_header
):
    _user, site, customer_headers = customer
    admin = _admin_headers(make_auth_header)

    # nothing to accept or approve before the vendor submits
    assert client.post(f"/app/checks/{site.id}/installation/accept", headers=customer_headers).status_code == 409
    assert client.post(f"/app/admin/installations/{project.id}/commissioning/approve", headers=admin).status_code == 409

    submitted = client.post(
        f"/app/vendor/installations/{project.id}/commissioning",
        json={
            "installedCapacityKwp": 4.4,
            "installedPanelCount": 8,
            "panelSerialNumbers": ["SN-1", "SN-2"],
            "inverterSerialNumber": "INV-9",
            "meterNumber": "MTR-3",
            "earthingTestPassed": True,
            "insulationTestPassed": True,
        },
        headers=_vendor_headers(db_session, vendor),
    )
    assert submitted.status_code == 200, submitted.json()
    assert submitted.json()["vendorConfirmed"] is True
    assert submitted.json()["customerAccepted"] is False

    accepted = client.post(f"/app/checks/{site.id}/installation/accept", headers=customer_headers)
    assert accepted.status_code == 200
    assert accepted.json()["customerAccepted"] is True
    # the vendor's own submission must survive the customer's sign-off
    assert accepted.json()["inverterSerialNumber"] == "INV-9"
    assert client.post(f"/app/checks/{site.id}/installation/accept", headers=customer_headers).status_code == 409

    approved = client.post(f"/app/admin/installations/{project.id}/commissioning/approve", headers=admin)
    assert approved.status_code == 200, approved.json()
    assert approved.json()["adminApproved"] is True
    assert approved.json()["commissioningDate"] is not None

    # approval is what completes the project — nothing else sets it
    detail = client.get(f"/app/admin/installations/{project.id}", headers=admin)
    assert detail.json()["status"] == "completed"

    # and the customer's own view reflects the whole chain
    view = client.get(f"/app/checks/{site.id}/installation", headers=customer_headers)
    assert view.status_code == 200
    assert view.json()["adminApproved"] is True
    assert view.json()["customerAccepted"] is True


def test_vendor_cannot_edit_an_approved_commissioning_record(
    client, db_session, project, vendor, make_auth_header
):
    headers = _vendor_headers(db_session, vendor)
    client.post(
        f"/app/vendor/installations/{project.id}/commissioning",
        json={"installedCapacityKwp": 4.4},
        headers=headers,
    )
    client.post(
        f"/app/admin/installations/{project.id}/commissioning/approve",
        headers=_admin_headers(make_auth_header),
    )
    response = client.post(
        f"/app/vendor/installations/{project.id}/commissioning",
        json={"installedCapacityKwp": 9.9},
        headers=headers,
    )
    assert response.status_code == 409


def test_admin_status_override_can_move_backwards(client, project, make_auth_header):
    admin = _admin_headers(make_auth_header)
    client.patch(
        f"/app/admin/installations/{project.id}/status", json={"status": "ac_wiring"}, headers=admin
    )
    back = client.patch(
        f"/app/admin/installations/{project.id}/status",
        json={"status": "material_procurement"},
        headers=admin,
    )
    assert back.status_code == 200
    assert back.json()["status"] == "material_procurement"


def test_installation_routes_require_the_right_role(client, db_session, project, customer):
    _user, _site, customer_headers = customer
    assert client.get("/app/admin/installations", headers=customer_headers).status_code == 403
    assert client.get("/app/vendor/installations", headers=customer_headers).status_code == 403


# --------------------------------------------------------------------- #
# vendor reviews — only available after the customer accepts the
# finished installation
# --------------------------------------------------------------------- #


def _accept_installation(client, db_session, site, vendor, project, customer_headers):
    """Runs the vendor-confirms -> customer-accepts sequence a review
    needs as its precondition — mirrors test_commissioning_runs_vendor_then_customer_then_admin."""
    client.post(
        f"/app/vendor/installations/{project.id}/commissioning",
        json={
            "installedCapacityKwp": 4.4,
            "installedPanelCount": 8,
            "panelSerialNumbers": ["SN-1", "SN-2"],
            "inverterSerialNumber": "INV-9",
            "meterNumber": "MTR-3",
            "earthingTestPassed": True,
            "insulationTestPassed": True,
        },
        headers=_vendor_headers(db_session, vendor),
    )
    accepted = client.post(f"/app/checks/{site.id}/installation/accept", headers=customer_headers)
    assert accepted.status_code == 200


def test_cannot_review_before_accepting_installation(client, db_session, customer, project, vendor):
    _user, site, customer_headers = customer
    response = client.post(
        f"/app/checks/{site.id}/review", json={"rating": 5}, headers=customer_headers
    )
    assert response.status_code == 409


def test_customer_can_review_after_accepting_installation(client, db_session, customer, project, vendor):
    _user, site, customer_headers = customer
    _accept_installation(client, db_session, site, vendor, project, customer_headers)

    response = client.post(
        f"/app/checks/{site.id}/review",
        json={"rating": 5, "comment": "Great crew, on time."},
        headers=customer_headers,
    )
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["rating"] == 5
    assert body["comment"] == "Great crew, on time."
    assert body["vendorId"] == str(vendor.id)


def test_cannot_review_the_same_installation_twice(client, db_session, customer, project, vendor):
    _user, site, customer_headers = customer
    _accept_installation(client, db_session, site, vendor, project, customer_headers)

    first = client.post(f"/app/checks/{site.id}/review", json={"rating": 4}, headers=customer_headers)
    assert first.status_code == 201
    second = client.post(f"/app/checks/{site.id}/review", json={"rating": 2}, headers=customer_headers)
    assert second.status_code == 409


def test_review_rating_must_be_in_range(client, db_session, customer, project, vendor):
    _user, site, customer_headers = customer
    _accept_installation(client, db_session, site, vendor, project, customer_headers)

    response = client.post(f"/app/checks/{site.id}/review", json={"rating": 6}, headers=customer_headers)
    assert response.status_code == 422


def test_vendor_list_reflects_review_rating_and_workload(client, db_session, customer, project, vendor):
    _user, site, customer_headers = customer
    _accept_installation(client, db_session, site, vendor, project, customer_headers)
    client.post(f"/app/checks/{site.id}/review", json={"rating": 5}, headers=customer_headers)

    vendors = client.get(f"/app/checks/{site.id}/vendors", headers=customer_headers)
    assert vendors.status_code == 200
    entry = next(v for v in vendors.json() if v["id"] == str(vendor.id))
    assert entry["averageRating"] == 5.0
    assert entry["reviewCount"] == 1

    reviews = client.get(f"/app/checks/{site.id}/vendors/{vendor.id}/reviews", headers=customer_headers)
    assert reviews.status_code == 200
    assert len(reviews.json()) == 1
    assert reviews.json()[0]["rating"] == 5


def test_vendor_with_no_reviews_shows_null_average(client, db_session, customer, vendor):
    _user, site, customer_headers = customer
    vendors = client.get(f"/app/checks/{site.id}/vendors", headers=customer_headers)
    entry = next(v for v in vendors.json() if v["id"] == str(vendor.id))
    assert entry["averageRating"] is None
    assert entry["reviewCount"] == 0
