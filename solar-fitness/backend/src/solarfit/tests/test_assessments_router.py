"""Tests for routers/assessments.py — the core-assessment slice of §9.8
Interface (API-01..05), tasks 12 and 13 of Person 4's list.

This is the one place all of Person 4's REAL modules (fitness.py,
ml_score.py, calibration.py) run genuinely un-mocked, integrated
together — only P1/P2/P3's still-stub dependencies are monkeypatched.
DB-touching pieces (calibration state, training-sample capture) run
against in-memory SQLite, same pattern as every prior phase.
"""

from typing import ClassVar

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

import solarfit.routers.assessments as router_module
from solarfit.domain.assessment import AnalysisResult, MLScore, PanoramaResult, VisionRefinement
from solarfit.domain.constraint import CapacityResult, Ceiling, Gate
from solarfit.main import app
from solarfit.repositories.calibration import CalibrationRecord, UtilisationFactorProposal
from solarfit.repositories.ml_models import MLModelVersion, MLTrainingSample


@pytest.fixture
def db_backed_dependencies(sqlite_engine, monkeypatch):
    """fitness.py has no DB, but ml_score.py's record_training_sample()
    and calibration.py's get_calibration_confidence_adjustment() both
    do — both run for real in this test file, so both need tables."""
    from solarfit.engine import ml_score as ml_score_module
    from solarfit.repositories import calibration as calibration_module

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
    monkeypatch.setattr(calibration_module, "session_scope", lambda: session_local())
    monkeypatch.setattr(ml_score_module, "session_scope", lambda: session_local())
    return session_local


def _make_ceiling_fn(calls: list, name: str, kwp: float):
    def _fn(*args, **kwargs):
        calls.append(name)
        return Ceiling(constraint=name, ceiling_kwp=kwp, reason=f"{name} reason", status="ok")

    return _fn


def _make_gate_fn(calls: list, name: str, status: str = "PASS"):
    def _fn(*args, **kwargs):
        calls.append(name)
        return Gate(gate=name, status=status, detail=f"{name} detail")

    return _fn


@pytest.fixture
def stub_pipeline(monkeypatch, make_site):
    """Monkeypatches every P1/P2/P3 dependency orchestrate_assessment()
    calls into, representing what a real pipeline will eventually
    produce. Returns call-tracking lists so tests can assert the
    producers actually ran (e.g. even on a cache hit)."""
    site = make_site(id="site-1", site_type="ROOFTOP_RESIDENTIAL")
    monkeypatch.setattr(
        router_module.sites_repo,
        "get",
        lambda session, site_id: site if site_id == site.id else None,
    )

    analysis = AnalysisResult(
        boundary={"type": "Polygon", "coordinates": [[[0, 0], [0, 10], [10, 10], [10, 0], [0, 0]]]},
        usable_area_m2=80.0,
        capacity=None,
        vision_refinement=VisionRefinement(confidence=0.9, obstacles=[], obstruction_notes=[]),
        panorama=PanoramaResult(status="ok", url="https://example.com/panorama.png"),
        ml_score=MLScore(status="insufficient_data", score=None, model_version=None),
        cache_hit=False,
        reused_from_analysis_id=None,
    )

    get_or_create_calls: list = []

    def _fake_get_or_create(lat, lng, site_type, params):
        get_or_create_calls.append((lat, lng, site_type))
        return analysis

    monkeypatch.setattr(router_module.analysis_cache_repo, "get_or_create_analysis", _fake_get_or_create)

    ceiling_calls: list = []
    monkeypatch.setattr(router_module.universal, "usable_area_ceiling", _make_ceiling_fn(ceiling_calls, "usable_area_ceiling", 6.0))
    monkeypatch.setattr(router_module.universal, "evacuation_headroom_ceiling", _make_ceiling_fn(ceiling_calls, "evacuation_headroom_ceiling", 10.0))
    monkeypatch.setattr(router_module.rooftop, "net_metering_cap", _make_ceiling_fn(ceiling_calls, "net_metering_cap", 4.0))
    monkeypatch.setattr(router_module.rooftop, "consumption_offset_ceiling", _make_ceiling_fn(ceiling_calls, "consumption_offset_ceiling", 5.0))
    monkeypatch.setattr(router_module.rooftop, "transformer_headroom_ceiling", _make_ceiling_fn(ceiling_calls, "transformer_headroom_ceiling", 8.0))
    monkeypatch.setattr(router_module.rooftop, "subsidy_tier_cap", _make_ceiling_fn(ceiling_calls, "subsidy_tier_cap", 4.5))

    gate_calls: list = []
    monkeypatch.setattr(router_module.universal, "minimum_viable_size_gate", _make_gate_fn(gate_calls, "minimum_viable_size_gate"))
    monkeypatch.setattr(router_module.rooftop, "structural_gate", _make_gate_fn(gate_calls, "structural_gate"))

    def _fake_resolve_capacity(ceilings):
        usable = [c for c in ceilings if c.ceiling_kwp is not None]
        binding = min(usable, key=lambda c: c.ceiling_kwp)
        return CapacityResult(
            recommended_kwp=binding.ceiling_kwp,
            max_technical_kwp=max(c.ceiling_kwp for c in usable),
            binding_constraint=binding.constraint,
            headroom_kwp=1.0,
            ceilings=ceilings,
            unit_basis="DC",
            status="ok",
        )

    monkeypatch.setattr(router_module.resolver, "resolve_capacity", _fake_resolve_capacity)
    monkeypatch.setattr(
        router_module.generation,
        "estimate_generation_kwh",
        lambda site, kwp, params=None: {"performance_ratio": 0.8, "annual_kwh": kwp * 1400},
    )
    monkeypatch.setattr(
        router_module.weather_provider,
        "fetch_weather",
        lambda lat, lng: {"irradiance": 800.0, "cloud_cover": 20.0, "temperature": 30.0},
    )

    return {
        "site": site,
        "analysis": analysis,
        "get_or_create_calls": get_or_create_calls,
        "ceiling_calls": ceiling_calls,
        "gate_calls": gate_calls,
    }


# ---------------------------------------------------------------------------
# orchestrate_assessment()
# ---------------------------------------------------------------------------


def test_orchestrate_assessment_full_response(db_backed_dependencies, stub_pipeline):
    result = router_module.orchestrate_assessment("site-1")

    assert result.site_id == "site-1"
    assert result.site_type == "ROOFTOP_RESIDENTIAL"
    assert result.verdict is not None
    assert result.confidence > 0.0
    assert result.binding_constraint  # never empty, FIT-06
    assert result.capacity.recommended_kwp == 4.0  # net_metering_cap is the binding ceiling
    assert result.boundary == stub_pipeline["analysis"].boundary
    assert result.usable_area_m2 == 80.0
    assert result.vision_refinement is not None
    assert result.panorama_url == "https://example.com/panorama.png"
    assert result.cache_hit is False
    assert result.usn is None  # not set on the fixture site
    assert result.engine_version  # API-04
    assert result.constraint_pack_version == "rooftop_v1"  # API-04


def test_orchestrate_assessment_site_not_found(db_backed_dependencies, stub_pipeline):
    with pytest.raises(router_module.SiteNotFoundError):
        router_module.orchestrate_assessment("does-not-exist")


def test_cache_hit_still_recomputes_capacity_and_fitness(db_backed_dependencies, stub_pipeline):
    """The key architectural guarantee: even when Person 3's cache
    already has geometry/vision/weather/panorama/ml, capacity and
    fitness are still computed fresh every call."""
    stub_pipeline["analysis"].cache_hit = True

    result = router_module.orchestrate_assessment("site-1")

    assert result.cache_hit is True
    # Constraint/gate producers still ran despite the cache hit:
    assert len(stub_pipeline["ceiling_calls"]) == 6
    assert len(stub_pipeline["gate_calls"]) == 2


def test_calibration_state_wired_in_for_real(db_backed_dependencies, stub_pipeline, monkeypatch):
    calls = []
    from solarfit.repositories import calibration as calibration_module

    original = calibration_module.get_calibration_confidence_adjustment

    def _tracking(site_type, geometry_source=None):
        calls.append((site_type, geometry_source))
        return original(site_type, geometry_source)

    monkeypatch.setattr(router_module.calibration, "get_calibration_confidence_adjustment", _tracking)

    router_module.orchestrate_assessment("site-1")

    assert calls == [("ROOFTOP_RESIDENTIAL", "solar_api")]


def test_training_sample_recorded_for_real(db_backed_dependencies, stub_pipeline):
    router_module.orchestrate_assessment("site-1")

    with db_backed_dependencies() as session:
        rows = list(session.scalars(select(MLTrainingSample)).all())
        assert len(rows) == 1
        assert rows[0].site_id == "site-1"
        assert rows[0].label_source == "fit_score"


def test_training_sample_not_recorded_when_insufficient_data(db_backed_dependencies, stub_pipeline, monkeypatch):
    monkeypatch.setattr(
        router_module.resolver,
        "resolve_capacity",
        lambda ceilings: CapacityResult(recommended_kwp=None, status="INSUFFICIENT_DATA"),
    )

    result = router_module.orchestrate_assessment("site-1")

    assert result.score is None
    with db_backed_dependencies() as session:
        rows = list(session.scalars(select(MLTrainingSample)).all())
        assert len(rows) == 0


# ---------------------------------------------------------------------------
# Sync endpoint
# ---------------------------------------------------------------------------


def test_post_assessment_returns_200_with_full_body(db_backed_dependencies, stub_pipeline):
    client = TestClient(app)

    response = client.post("/v1/assessments/site-1")

    assert response.status_code == 200
    body = response.json()
    assert body["site_id"] == "site-1"
    assert body["constraint_pack_version"] == "rooftop_v1"


def test_post_assessment_returns_404_for_unknown_site(db_backed_dependencies, stub_pipeline):
    client = TestClient(app)

    response = client.post("/v1/assessments/does-not-exist")

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Batch — API-03
# ---------------------------------------------------------------------------


def test_batch_task_isolates_per_site_failures(db_backed_dependencies, stub_pipeline):
    from solarfit.workers.tasks_assessments import run_batch_assessment

    results = run_batch_assessment.run(["site-1", "does-not-exist"])

    by_id = {r["site_id"]: r for r in results}
    assert by_id["site-1"]["status"] == "ok"
    assert by_id["does-not-exist"]["status"] == "not_found"


def test_post_batch_assessment_returns_job_id(db_backed_dependencies, stub_pipeline, monkeypatch):
    from solarfit.workers.tasks_assessments import run_batch_assessment as batch_task

    class FakeAsyncTask:
        id = "job-123"

    monkeypatch.setattr(batch_task, "delay", lambda site_ids: FakeAsyncTask())

    client = TestClient(app)
    response = client.post("/v1/assessments/batch", json={"site_ids": ["site-1"]})

    assert response.status_code == 200
    assert response.json() == {"job_id": "job-123"}


def test_get_batch_assessment_status_maps_celery_state(db_backed_dependencies, stub_pipeline, monkeypatch):
    class FakeAsyncResult:
        status = "SUCCESS"
        result: ClassVar = [{"site_id": "site-1", "status": "ok", "result": {}}]

        def successful(self):
            return True

    monkeypatch.setattr(router_module.celery_app, "AsyncResult", lambda job_id: FakeAsyncResult())

    client = TestClient(app)
    response = client.get("/v1/assessments/batch/job-123")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "SUCCESS"
    assert body["results"] == [{"site_id": "site-1", "status": "ok", "result": {}}]
