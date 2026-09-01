"""Owner: karthik (App Platform & Foundation).

Tests for routers/app_checks.py — the consumer self-service "checks"
portal, closing the "no backend for the checks flow at all" gap found
during a frontend/backend sync audit.

Checks reuse routers/sites.py::create_site_core() exactly like
app_sites.py does, so the same "patch where it's looked up" Solar API
fake applies. completeCheck runs the real orchestrate_assessment(),
which itself calls into repositories/analysis_cache.py's real pipeline —
mocked the same way test_assessments_router.py's stub_pipeline mocks it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from solarfit.db import get_session
from solarfit.main import app
from solarfit.providers.solar_api import SolarApiResult

BOUNDARY = {
    "type": "Polygon",
    "coordinates": [[[78.4860, 17.3845], [78.4874, 17.3845], [78.4874, 17.3855], [78.4860, 17.3855], [78.4860, 17.3845]]],
}


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _fake_solar_api(monkeypatch):
    monkeypatch.setattr(
        "solarfit.routers.sites.solar_api.resolve_for_address",
        lambda address, **kw: SolarApiResult(status="ok", boundary=BOUNDARY),
    )


def _new_check_body(**overrides):
    body = {"address": "12-2-823, Road No. 5, Jubilee Hills", "lat": 17.3850, "lng": 78.4867}
    body.update(overrides)
    return body


# --------------------------------------------------------------------- #
# create / list / get
# --------------------------------------------------------------------- #


def test_create_check_requires_auth(client):
    response = client.post("/app/checks", json=_new_check_body())
    assert response.status_code == 401


def test_create_check_returns_site_shape(client, make_auth_header):
    headers = make_auth_header(role="customer", owner_org=None)
    response = client.post("/app/checks", json=_new_check_body(), headers=headers)
    assert response.status_code == 201
    body = response.json()
    assert body["siteType"] == "ROOFTOP_RESIDENTIAL"
    assert body["latestAssessment"] is None
    assert body["boundary"] is not None


def test_individual_without_owner_org_can_create_a_check(client, make_auth_header):
    """The whole point of the synthetic owner_org scheme: a signup with
    no company name (owner_org=None) still gets a working checks flow,
    even though app_sites.py's own endpoints would 403 for them."""
    headers = make_auth_header(role="customer", owner_org=None)
    response = client.post("/app/checks", json=_new_check_body(), headers=headers)
    assert response.status_code == 201


def test_list_and_get_check_round_trip(client, make_auth_header):
    headers = make_auth_header(role="customer", owner_org=None)
    created = client.post("/app/checks", json=_new_check_body(), headers=headers).json()

    listed = client.get("/app/checks", headers=headers).json()
    assert [c["id"] for c in listed] == [created["id"]]

    fetched = client.get(f"/app/checks/{created['id']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["id"] == created["id"]


def test_checks_are_scoped_per_user_not_shared(client, make_auth_header):
    alice = make_auth_header(role="customer", owner_org=None, email="alice@example.com")
    bob = make_auth_header(role="customer", owner_org=None, email="bob@example.com")
    client.post("/app/checks", json=_new_check_body(), headers=alice)

    assert len(client.get("/app/checks", headers=alice).json()) == 1
    assert len(client.get("/app/checks", headers=bob).json()) == 0


def test_get_unknown_check_is_404(client, make_auth_header):
    headers = make_auth_header(role="customer", owner_org=None)
    response = client.get("/app/checks/00000000-0000-0000-0000-000000000000", headers=headers)
    assert response.status_code == 404


def test_get_another_users_check_is_404(client, make_auth_header):
    alice = make_auth_header(role="customer", owner_org=None, email="alice2@example.com")
    bob = make_auth_header(role="customer", owner_org=None, email="bob2@example.com")
    created = client.post("/app/checks", json=_new_check_body(), headers=alice).json()

    response = client.get(f"/app/checks/{created['id']}", headers=bob)
    assert response.status_code == 404


# --------------------------------------------------------------------- #
# complete
# --------------------------------------------------------------------- #


def test_complete_check_runs_the_real_engine_and_persists(client, make_auth_header, monkeypatch, db_session):
    """orchestrate_assessment() and complete_check()'s own save both open
    a real solarfit.db.session_scope() internally rather than using the
    injected/overridden get_session dependency — same pattern
    test_app_admin_engine.py's obstacle-reject tests hit — so both need
    pointing at the test's own transactional db_session, or the site
    created through the HTTP client above (uncommitted) is invisible to
    them."""
    from contextlib import contextmanager

    from solarfit.domain.assessment import VisionRefinement

    @contextmanager
    def _fake_session_scope():
        yield db_session

    monkeypatch.setattr("solarfit.routers.assessments.session_scope", _fake_session_scope)
    monkeypatch.setattr("solarfit.routers.app_checks.session_scope", _fake_session_scope)

    headers = make_auth_header(role="customer", owner_org=None)
    created = client.post("/app/checks", json=_new_check_body(), headers=headers).json()

    monkeypatch.setattr(
        "solarfit.repositories.analysis_cache.get_or_create_analysis",
        lambda lat, lng, site_type, params: type(
            "A",
            (),
            {
                "boundary": BOUNDARY,
                "usable_area_m2": None,
                "vision_refinement": VisionRefinement(confidence=0.9, obstacles=[], obstruction_notes=[]),
                "panorama": None,
                "ml_score": None,
                "cache_hit": False,
                "reused_from_analysis_id": None,
            },
        )(),
    )

    response = client.post(f"/app/checks/{created['id']}/complete", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["latestAssessment"] is not None
    assert body["latestAssessment"]["verdict"] in {
        "SUITABLE",
        "SUITABLE_SUBJECT_TO_SURVEY",
        "CONDITIONAL",
        "INSUFFICIENT_DATA",
        "NOT_SUITABLE",
    }

    # Persisted, not just returned once — a second read still shows it.
    refetched = client.get(f"/app/checks/{created['id']}", headers=headers).json()
    assert refetched["latestAssessment"] is not None


def test_complete_unknown_check_is_404(client, make_auth_header):
    headers = make_auth_header(role="customer", owner_org=None)
    response = client.post(
        "/app/checks/00000000-0000-0000-0000-000000000000/complete", headers=headers
    )
    assert response.status_code == 404


# --------------------------------------------------------------------- #
# check -> vendor-job handoff
# --------------------------------------------------------------------- #


def _canned_assessment_response(site_id, site_type, verdict):
    from solarfit.domain.constraint import CapacityResult
    from solarfit.routers.assessments import AssessmentResponse

    return AssessmentResponse(
        site_id=site_id,
        site_type=site_type,
        verdict=verdict,
        score=0.5,
        confidence=0.6,
        binding_constraint="gate:pending",
        reasons=["Needs an in-person survey."],
        limitations="",
        capacity=CapacityResult(recommended_kwp=4.0, status="ok"),
        boundary=BOUNDARY,
        usable_area_m2=40.0,
        engine_version="test",
        constraint_pack_version="test",
    )


def _complete_with_canned_verdict(client, headers, monkeypatch, db_session, site_type, verdict):
    from contextlib import contextmanager

    @contextmanager
    def _fake_session_scope():
        yield db_session

    monkeypatch.setattr("solarfit.routers.app_checks.session_scope", _fake_session_scope)

    created = client.post(
        "/app/checks", json=_new_check_body(siteType=site_type), headers=headers
    ).json()

    monkeypatch.setattr(
        "solarfit.routers.app_checks.orchestrate_assessment",
        lambda check_id: _canned_assessment_response(check_id, site_type, verdict),
    )

    response = client.post(f"/app/checks/{created['id']}/complete", headers=headers)
    assert response.status_code == 200
    return created["id"]


def _vendor_job_for_site(db_session, site_id):
    import uuid

    from sqlalchemy import select

    from solarfit.repositories.vendors import VendorJobRow

    return db_session.scalars(
        select(VendorJobRow).where(VendorJobRow.site_id == uuid.UUID(site_id))
    ).first()


def test_survey_verdict_queues_an_unassigned_vendor_job(client, make_auth_header, monkeypatch, db_session):
    headers = make_auth_header(role="customer", owner_org=None)
    check_id = _complete_with_canned_verdict(
        client, headers, monkeypatch, db_session, "ROOFTOP_RESIDENTIAL", "SUITABLE_SUBJECT_TO_SURVEY"
    )

    job = _vendor_job_for_site(db_session, check_id)
    assert job is not None
    assert job.vendor_id is None
    assert job.status == "queued"
    assert job.payout_inr > 0
    assert job.estimated_capacity_kwp == 4.0


def test_non_survey_verdict_does_not_queue_a_vendor_job(client, make_auth_header, monkeypatch, db_session):
    headers = make_auth_header(role="customer", owner_org=None)
    check_id = _complete_with_canned_verdict(
        client, headers, monkeypatch, db_session, "ROOFTOP_RESIDENTIAL", "SUITABLE"
    )

    assert _vendor_job_for_site(db_session, check_id) is None


def test_survey_job_requirements_include_usn_for_billing_linked_site_type(
    client, make_auth_header, monkeypatch, db_session
):
    headers = make_auth_header(role="customer", owner_org=None)
    check_id = _complete_with_canned_verdict(
        client, headers, monkeypatch, db_session, "ROOFTOP_RESIDENTIAL", "SUITABLE_SUBJECT_TO_SURVEY"
    )

    job = _vendor_job_for_site(db_session, check_id)
    assert job.requirements == [
        "Capture boundary polygon",
        "Upload panorama photo",
        "Confirm USN via bill OCR",
        "Note shading obstructions",
    ]


def test_survey_job_requirements_omit_usn_for_non_billing_linked_site_type(
    client, make_auth_header, monkeypatch, db_session
):
    # ROOFTOP_GOVT is the one RoofSiteType not in BILLING_LINKED_SITE_TYPES
    # (only ROOFTOP_RESIDENTIAL/ROOFTOP_CI are — USN-05).
    headers = make_auth_header(role="customer", owner_org=None)
    check_id = _complete_with_canned_verdict(
        client, headers, monkeypatch, db_session, "ROOFTOP_GOVT", "SUITABLE_SUBJECT_TO_SURVEY"
    )

    job = _vendor_job_for_site(db_session, check_id)
    assert job.requirements == [
        "Capture boundary polygon",
        "Upload panorama photo",
        "Note shading obstructions",
    ]


# --------------------------------------------------------------------- #
# profile
# --------------------------------------------------------------------- #


def test_get_profile_requires_auth(client):
    response = client.get("/app/customer/profile")
    assert response.status_code == 401


def test_get_profile_returns_camelcase(client, make_auth_header):
    headers = make_auth_header(role="customer", owner_org=None, name="Priya Raman")
    response = client.get("/app/customer/profile", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Priya Raman"
    assert body["notifyOnComplete"] is True
    assert body["phone"] is None


def test_update_profile_persists_changes(client, make_auth_header):
    headers = make_auth_header(role="customer", owner_org=None)
    response = client.patch(
        "/app/customer/profile",
        json={"phone": "+91 98765 43210", "notifyOnComplete": False},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["phone"] == "+91 98765 43210"
    assert body["notifyOnComplete"] is False

    refetched = client.get("/app/customer/profile", headers=headers).json()
    assert refetched["phone"] == "+91 98765 43210"


def test_update_profile_ignores_email(client, make_auth_header):
    headers = make_auth_header(role="customer", owner_org=None, email="original@example.com")
    response = client.patch(
        "/app/customer/profile", json={"phone": "+91 90000 00000"}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["email"] == "original@example.com"
