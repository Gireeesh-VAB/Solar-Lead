"""Tests for routers/app_assessments.py — the "Assessments, frontend-
shaped & secured" roadmap workstream (2 endpoints).

orchestrate_assessment() itself is already covered end-to-end by
test_assessments_router.py — here it's monkeypatched to a canned
AssessmentResponse, same discipline as that file's own "stub pipeline"
approach, so these tests verify THIS router's own logic (auth, owner_org
scoping, persistence, frontend-shape mapping) rather than re-testing the
orchestration pipeline. repositories/assessments.py's own table has no
PostGIS columns, so it runs against an in-memory SQLite engine, same
pattern as calibration/ml_models.
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from solarfit.domain.constraint import CapacityResult, Ceiling
from solarfit.domain.site import Site
from solarfit.main import app
from solarfit.repositories.assessments import AssessmentRow
from solarfit.routers import app_assessments
from solarfit.routers.assessments import AssessmentResponse


@pytest.fixture
def assessments_session_factory(sqlite_engine, monkeypatch):
    AssessmentRow.metadata.create_all(sqlite_engine, tables=[AssessmentRow.__table__])
    session_local = sessionmaker(bind=sqlite_engine)
    monkeypatch.setattr(app_assessments, "session_scope", lambda: session_local())
    return session_local


def _make_site(**overrides) -> Site:
    defaults = {
        "id": "site-1",
        "site_type": "ROOFTOP_RESIDENTIAL",
        "name": "Test Site",
        "owner_org": "Test Org",
        "jurisdiction": "AP",
        "centroid": {"type": "Point", "coordinates": [78.4867, 17.3850]},
        "boundary": None,
        "exclusions": None,
        "geometry_source": "solar_api",
        "imagery_date": datetime.now(UTC),
        "imagery_quality": "HIGH",
        "geometry_confidence": 0.9,
        "shading": None,
        "usn": None,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return Site(**defaults)


def _make_response(**overrides) -> AssessmentResponse:
    defaults = {
        "site_id": "site-1",
        "site_type": "ROOFTOP_RESIDENTIAL",
        "verdict": "SUITABLE",
        "score": 0.82,
        "confidence": 0.75,
        "binding_constraint": "net_metering_cap",
        "reasons": ["Binding constraint: net_metering_cap."],
        "limitations": "This is a pre-feasibility estimate.",
        "capacity": CapacityResult(
            recommended_kwp=4.0,
            max_technical_kwp=6.0,
            binding_constraint="net_metering_cap",
            headroom_kwp=2.0,
            ceilings=[
                Ceiling(
                    constraint="net_metering_cap",
                    ceiling_kwp=4.0,
                    reason="Net metering cap for residential",
                    kind="regulatory",
                    status="ok",
                ),
            ],
            status="ok",
        ),
        "boundary": {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]},
        "usable_area_m2": 80.0,
        "vision_refinement": None,
        "panorama_url": None,
        "ml_suitability_score": None,
        "ml_model_version": None,
        "cache_hit": False,
        "reused_from_analysis_id": None,
        "usn": None,
        "engine_version": "0.1.0",
        "constraint_pack_version": "rooftop_v1",
    }
    defaults.update(overrides)
    return AssessmentResponse(**defaults)


@pytest.fixture
def fake_pipeline(monkeypatch):
    site = _make_site()
    response = _make_response()
    monkeypatch.setattr(app_assessments.sites_repo, "get", lambda session, site_id: site if site_id == site.id else None)
    monkeypatch.setattr(app_assessments, "orchestrate_assessment", lambda site_id: response)
    return {"site": site, "response": response}


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _as_user(role: str, owner_org: str | None = "Test Org"):
    from solarfit.auth_users import AuthenticatedUser

    return AuthenticatedUser(id="user-1", email="u@example.com", role=role, name="U", owner_org=owner_org)


# ---------------------------------------------------------------------------
# POST /app/assessments/{id}
# ---------------------------------------------------------------------------


def test_post_assessment_requires_auth(client, fake_pipeline, assessments_session_factory):
    response = client.post("/app/assessments/site-1")
    assert response.status_code == 401


def test_post_assessment_returns_frontend_shaped_body(client, fake_pipeline, assessments_session_factory):
    from solarfit.auth_users import current_user

    app.dependency_overrides[current_user] = lambda: _as_user("customer")

    response = client.post("/app/assessments/site-1")

    assert response.status_code == 200
    body = response.json()
    assert body["siteId"] == "site-1"
    assert body["confidence"] == "High"  # 0.75 >= 0.7
    assert body["bindingConstraint"] == {
        "name": "net_metering_cap",
        "reason": "Net metering cap for residential",
        "kind": "regulatory",
    }
    assert "deltaKwp" not in str(body.get("visionRefinement"))
    assert "generation" not in body
    assert "id" in body


def test_post_assessment_persists_a_row(client, fake_pipeline, assessments_session_factory):
    from solarfit.auth_users import current_user

    app.dependency_overrides[current_user] = lambda: _as_user("customer")

    client.post("/app/assessments/site-1")

    with assessments_session_factory() as session:
        rows = list(session.query(AssessmentRow).all())
        assert len(rows) == 1
        assert rows[0].owner_org == "Test Org"
        assert rows[0].site_id == "site-1"


def test_post_assessment_unknown_site_is_404(client, fake_pipeline, assessments_session_factory):
    from solarfit.auth_users import current_user

    app.dependency_overrides[current_user] = lambda: _as_user("customer")

    response = client.post("/app/assessments/does-not-exist")

    assert response.status_code == 404


def test_post_assessment_other_orgs_site_is_404_not_403(client, fake_pipeline, assessments_session_factory):
    """404, not 403 — matches test_sites_api.py::test_another_tenants_site_is_404_not_403's
    precedent: don't leak that a site exists to someone with no access to it."""
    from solarfit.auth_users import current_user

    app.dependency_overrides[current_user] = lambda: _as_user("customer", owner_org="Someone Else's Org")

    response = client.post("/app/assessments/site-1")

    assert response.status_code == 404


def test_post_assessment_admin_can_assess_any_org(client, fake_pipeline, assessments_session_factory):
    from solarfit.auth_users import current_user

    app.dependency_overrides[current_user] = lambda: _as_user("admin", owner_org=None)

    response = client.post("/app/assessments/site-1")

    assert response.status_code == 200


def test_confidence_bucket_thresholds(client, assessments_session_factory, monkeypatch):
    from solarfit.auth_users import current_user

    site = _make_site()
    monkeypatch.setattr(app_assessments.sites_repo, "get", lambda session, site_id: site)
    app.dependency_overrides[current_user] = lambda: _as_user("customer")

    for confidence, expected in [(0.9, "High"), (0.5, "Medium"), (0.1, "Low")]:
        monkeypatch.setattr(
            app_assessments, "orchestrate_assessment", lambda site_id, c=confidence: _make_response(confidence=c)
        )
        response = client.post("/app/assessments/site-1")
        assert response.json()["confidence"] == expected


def test_confidence_is_na_when_score_is_none(client, assessments_session_factory, monkeypatch):
    from solarfit.auth_users import current_user

    site = _make_site()
    monkeypatch.setattr(app_assessments.sites_repo, "get", lambda session, site_id: site)
    monkeypatch.setattr(
        app_assessments,
        "orchestrate_assessment",
        lambda site_id: _make_response(score=None, verdict="INSUFFICIENT_DATA", confidence=0.1),
    )
    app.dependency_overrides[current_user] = lambda: _as_user("customer")

    response = client.post("/app/assessments/site-1")

    assert response.json()["confidence"] == "N/A"


# ---------------------------------------------------------------------------
# GET /app/admin/assessments
# ---------------------------------------------------------------------------


def test_list_all_assessments_requires_admin(client, fake_pipeline, assessments_session_factory):
    from solarfit.auth_users import current_user

    app.dependency_overrides[current_user] = lambda: _as_user("customer")

    response = client.get("/app/admin/assessments")

    assert response.status_code == 403


def test_list_all_assessments_returns_cross_org(client, fake_pipeline, assessments_session_factory):
    from solarfit.auth_users import current_user

    app.dependency_overrides[current_user] = lambda: _as_user("customer")
    client.post("/app/assessments/site-1")

    app.dependency_overrides[current_user] = lambda: _as_user("admin", owner_org=None)
    response = client.get("/app/admin/assessments")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["ownerOrg"] == "Test Org"
