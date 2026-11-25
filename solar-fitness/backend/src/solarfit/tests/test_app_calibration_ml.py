"""Tests for routers/app_calibration_ml.py — the "Calibration & ML
approval" roadmap workstream (4 endpoints, admin-only).

Auth (current_user()/require_role()) is exercised for real against the
transactional db_session fixture, same pattern as test_auth_users.py's
router tests. calibration.py/ml_score.py's own session_scope() is
monkeypatched to an in-memory SQLite engine, same pattern as
test_calibration.py/test_ml_score.py — calibration_records,
utilisation_factor_proposals, ml_training_samples, and ml_model_versions
have no PostGIS columns, so this is a faithful substitute.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from solarfit.db import get_session
from solarfit.engine import ml_score
from solarfit.main import app
from solarfit.repositories import calibration
from solarfit.repositories.calibration import CalibrationRecord, UtilisationFactorProposal
from solarfit.repositories.ml_models import MLModelVersion, MLTrainingSample


@pytest.fixture
def calibration_ml_session_factory(sqlite_engine, monkeypatch):
    CalibrationRecord.metadata.create_all(
        sqlite_engine,
        tables=[
            CalibrationRecord.__table__,
            UtilisationFactorProposal.__table__,
            MLTrainingSample.__table__,
            MLModelVersion.__table__,
        ],
    )
    session_local = sessionmaker(bind=sqlite_engine)
    monkeypatch.setattr(calibration, "session_scope", lambda: session_local())
    monkeypatch.setattr(ml_score, "session_scope", lambda: session_local())
    return session_local


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed_records(session_factory, site_type: str, ratios: list[float]):
    from datetime import UTC, datetime
    from uuid import uuid4

    with session_factory() as session:
        for ratio in ratios:
            remote = 100.0
            session.add(
                CalibrationRecord(
                    id=str(uuid4()),
                    site_id=str(uuid4()),
                    site_type=site_type,
                    region="AP",
                    geometry_source="solar_api",
                    remote_area_m2=remote,
                    measured_area_m2=remote * ratio,
                    variance_pct=ratio - 1.0,
                    flagged_superseded=False,
                    created_at=datetime.now(UTC),
                )
            )
        session.commit()


def _make_proposal(calibration_ml_session_factory) -> str:
    _seed_records(calibration_ml_session_factory, "ROOFTOP_RESIDENTIAL", [1.10] * 25)
    proposal = calibration.propose_utilisation_factor_update("ROOFTOP_RESIDENTIAL")
    return proposal["proposal_id"]


def _make_model_version(calibration_ml_session_factory, fake_object_storage) -> str:
    from .test_ml_score import _seed_samples

    _seed_samples(calibration_ml_session_factory, n_groups=20)
    result = ml_score.train()
    return result["version_id"]


@pytest.fixture
def fake_object_storage(monkeypatch):
    store: dict[str, bytes] = {}
    monkeypatch.setattr(ml_score, "_upload_model_artifact", lambda key, data: store.__setitem__(key, data))
    monkeypatch.setattr(ml_score, "_download_model_artifact", lambda key: store[key])
    return store


# ---------------------------------------------------------------------------
# Auth gating — every route requires an admin
# ---------------------------------------------------------------------------


def test_approve_calibration_proposal_requires_auth(client, calibration_ml_session_factory):
    response = client.post("/app/admin/calibration-proposals/some-id/approve")
    assert response.status_code == 401


def test_approve_calibration_proposal_requires_admin_role(
    client, calibration_ml_session_factory, make_auth_header
):
    headers = make_auth_header(role="customer")
    response = client.post("/app/admin/calibration-proposals/some-id/approve", headers=headers)
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# List endpoints — closes the "approve/reject with no way to list" gap
# ---------------------------------------------------------------------------


def test_list_calibration_proposals_requires_admin_role(client, calibration_ml_session_factory, make_auth_header):
    response = client.get("/app/admin/calibration-proposals", headers=make_auth_header(role="customer"))
    assert response.status_code == 403


def test_list_calibration_proposals_returns_camelcase(client, calibration_ml_session_factory, make_auth_header):
    proposal_id = _make_proposal(calibration_ml_session_factory)
    headers = make_auth_header(role="admin")

    response = client.get("/app/admin/calibration-proposals", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == proposal_id
    assert body[0]["jurisdiction"] == "ROOFTOP_RESIDENTIAL"  # documented closest-honest-field mapping
    assert body[0]["status"] == "proposed"
    assert body[0]["sampleSize"] == 25
    assert "proposedAt" in body[0]


def test_list_model_versions_requires_admin_role(client, calibration_ml_session_factory, make_auth_header):
    response = client.get("/app/admin/model-versions", headers=make_auth_header(role="customer"))
    assert response.status_code == 403


def test_list_model_versions_returns_camelcase(
    client, calibration_ml_session_factory, fake_object_storage, make_auth_header
):
    version_id = _make_model_version(calibration_ml_session_factory, fake_object_storage)
    headers = make_auth_header(role="admin")

    response = client.get("/app/admin/model-versions", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == version_id
    assert body[0]["status"] == "proposed"
    assert isinstance(body[0]["metrics"], list)
    assert "proposedAt" in body[0]


# ---------------------------------------------------------------------------
# Calibration proposals
# ---------------------------------------------------------------------------


def test_approve_calibration_proposal_returns_200(client, calibration_ml_session_factory, make_auth_header):
    proposal_id = _make_proposal(calibration_ml_session_factory)
    headers = make_auth_header(role="admin")

    response = client.post(f"/app/admin/calibration-proposals/{proposal_id}/approve", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["proposalId"] == proposal_id


def test_reject_calibration_proposal_returns_200(client, calibration_ml_session_factory, make_auth_header):
    proposal_id = _make_proposal(calibration_ml_session_factory)
    headers = make_auth_header(role="admin")

    response = client.post(f"/app/admin/calibration-proposals/{proposal_id}/reject", headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


def test_approve_unknown_calibration_proposal_is_404(client, calibration_ml_session_factory, make_auth_header):
    headers = make_auth_header(role="admin")
    response = client.post("/app/admin/calibration-proposals/does-not-exist/approve", headers=headers)
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# ML model versions
# ---------------------------------------------------------------------------


def test_approve_model_version_returns_200(
    client, calibration_ml_session_factory, fake_object_storage, make_auth_header
):
    version_id = _make_model_version(calibration_ml_session_factory, fake_object_storage)
    headers = make_auth_header(role="admin")

    response = client.post(f"/app/admin/model-versions/{version_id}/approve", headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "approved"


def test_reject_model_version_returns_200(
    client, calibration_ml_session_factory, fake_object_storage, make_auth_header
):
    version_id = _make_model_version(calibration_ml_session_factory, fake_object_storage)
    headers = make_auth_header(role="admin")

    response = client.post(f"/app/admin/model-versions/{version_id}/reject", headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


def test_approve_unknown_model_version_is_404(client, calibration_ml_session_factory, make_auth_header):
    headers = make_auth_header(role="admin")
    response = client.post("/app/admin/model-versions/does-not-exist/approve", headers=headers)
    assert response.status_code == 404
