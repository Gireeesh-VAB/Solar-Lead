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
from pyproj import Transformer
from shapely.geometry import box as shapely_box
from shapely.geometry import mapping
from shapely.ops import transform
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

import solarfit.routers.assessments as router_module
from solarfit.domain.assessment import AnalysisResult, MLScore, PanoramaResult, VisionRefinement
from solarfit.domain.constraint import CapacityResult, Ceiling, Gate
from solarfit.engine.area import compute_usable_area_m2
from solarfit.main import app
from solarfit.repositories.calibration import CalibrationRecord, UtilisationFactorProposal
from solarfit.repositories.ml_models import MLModelVersion, MLTrainingSample

# Same Hyderabad origin make_site()'s default centroid uses — a real,
# metre-sized boundary here (not a 10-degree-wide box) so
# compute_usable_area_m2() (now called for real by orchestrate_assessment,
# not stubbed) produces a sane, non-astronomical figure.
_ORIGIN_LON, _ORIGIN_LAT = 78.4867, 17.3850


def _square_4326(side_m: float) -> dict:
    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32644", always_xy=True).transform
    to_wgs84 = Transformer.from_crs("EPSG:32644", "EPSG:4326", always_xy=True).transform
    x0, y0 = to_utm(_ORIGIN_LON, _ORIGIN_LAT)
    square = shapely_box(x0, y0, x0 + side_m, y0 + side_m)
    return mapping(transform(to_wgs84, square))


class _ImmediateAsyncResult:
    """Fakes the Celery AsyncResult get_or_create_analysis()/
    orchestrate_assessment() get back from .delay() — .get(timeout=...)
    just returns the value immediately, since these tests mock .delay()
    itself rather than running a real worker/broker."""

    def __init__(self, value):
        self._value = value

    def get(self, timeout=None):
        return self._value


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
        boundary=_square_4326(20.0),
        usable_area_m2=80.0,  # unused now — orchestrate_assessment computes this for real, see below
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
    # Computed for real (AREA-01..06) against analysis.boundary — not the
    # stubbed AnalysisResult.usable_area_m2, which orchestrate_assessment
    # no longer reads (see routers/assessments.py's comment on why).
    expected_usable_area_m2 = compute_usable_area_m2(
        stub_pipeline["site"].model_copy(update={"boundary": stub_pipeline["analysis"].boundary})
    )
    assert expected_usable_area_m2 > 0.0
    assert result.usable_area_m2 == pytest.approx(expected_usable_area_m2)
    assert result.vision_refinement is not None
    assert result.panorama_url == "https://example.com/panorama.png"
    assert result.cache_hit is False
    assert result.usn is None  # not set on the fixture site
    assert result.engine_version  # API-04
    assert result.constraint_pack_version == "rooftop_v1"  # API-04


def test_orchestrate_assessment_site_not_found(db_backed_dependencies, stub_pipeline):
    with pytest.raises(router_module.SiteNotFoundError):
        router_module.orchestrate_assessment("does-not-exist")


def test_orchestrate_assessment_usable_area_survives_the_real_cache_pipeline(
    db_backed_dependencies, monkeypatch, make_site
):
    """Regression test for the bug where usable_area_m2 was silently
    always 0.0: unlike stub_pipeline (which replaces
    get_or_create_analysis entirely), this only mocks the deep external
    calls inside it — solar_api/vision/weather/panorama/ml — and lets
    the real get_or_create_analysis() + real site_analysis_cache table
    run, same integration pattern as test_analysis_cache.py. If
    orchestrate_assessment ever goes back to reading
    analysis.usable_area_m2 directly, this fails with 0.0/None instead
    of a real positive number."""
    from unittest.mock import patch

    from solarfit.repositories.analysis_cache import force_refresh

    lat, lng = 12.3456, 76.5432  # distinct from every other test's key
    force_refresh(lat, lng)

    site = make_site(
        id="site-real-cache",
        site_type="ROOFTOP_RESIDENTIAL",
        centroid={"type": "Point", "coordinates": [lng, lat]},
    )
    monkeypatch.setattr(
        router_module.sites_repo, "get", lambda session, site_id: site if site_id == site.id else None
    )

    boundary = _square_4326(25.0)
    refinement_dict = {
        "corrected_boundary": None,
        "obstruction_notes": [],
        "obstacles": [],
        "confidence": 0.9,
        "status": "ok",
    }
    panorama_dict = {"url": None, "status": "not_generated", "reason": None, "generated_at": None, "version": None}
    try:
        with (
            patch("solarfit.providers.solar_api.resolve_via_solar_api", return_value=boundary),
            patch(
                "solarfit.workers.celery_app.refine_vision_task.delay",
                return_value=_ImmediateAsyncResult(refinement_dict),
            ),
            patch("solarfit.providers.weather.fetch_weather", return_value={"cloud_cover": 20}),
            patch(
                "solarfit.workers.celery_app.generate_panorama_task.delay",
                return_value=_ImmediateAsyncResult(panorama_dict),
            ),
            patch(
                "solarfit.engine.ml_score.score_with_ml_model",
                return_value=type("M", (), {"score": None, "model_version": None})(),
            ),
        ):
            result = router_module.orchestrate_assessment(site.id)

        expected = compute_usable_area_m2(site.model_copy(update={"boundary": boundary}))
        assert expected > 0.0
        assert result.usable_area_m2 == pytest.approx(expected)
    finally:
        force_refresh(lat, lng)


def test_orchestrate_assessment_dispatches_obstacle_apply_with_the_real_site_id(
    db_backed_dependencies, stub_pipeline, monkeypatch
):
    """Regression test for the bug where obstacle auto-apply was handed
    a synthetic, non-persisted site id from inside the cache pipeline
    (see analysis_cache.py's note) — every write threw and silently
    degraded to advisory-only. orchestrate_assessment must dispatch
    apply_obstacles_task with THIS site's real id, and pick up whatever
    exclusion change the task persisted before computing usable area."""
    from solarfit.domain.assessment import Obstacle

    # A small square inside the same 20m boundary stub_pipeline's
    # analysis uses (_square_4326 always starts at the same corner) —
    # geographically real, so compute_usable_area_m2's difference()
    # below is meaningful rather than a degenerate cross-continent noop.
    obstacle_polygon = _square_4326(5.0)
    obstacle = Obstacle(type="water_tank", confidence=0.95, bounding_polygon=obstacle_polygon)
    stub_pipeline["analysis"].vision_refinement.obstacles = [obstacle]

    # A second, distinct Site the refetch-after-apply should pick up —
    # different exclusions, so usable_area_m2 must be computed against
    # THIS one, not the pre-apply site from the top of the function.
    site_after_apply = stub_pipeline["site"].model_copy(
        update={"exclusions": {"type": "MultiPolygon", "coordinates": [obstacle.bounding_polygon["coordinates"]]}}
    )
    get_calls: list = []

    def _tracking_get(session, site_id):
        get_calls.append(site_id)
        if site_id != stub_pipeline["site"].id:
            return None
        return stub_pipeline["site"] if len(get_calls) == 1 else site_after_apply

    monkeypatch.setattr(router_module.sites_repo, "get", _tracking_get)

    delay_calls: list = []

    def _fake_delay(site_id, obstacles_payload):
        delay_calls.append((site_id, obstacles_payload))
        applied = [{**o, "applied": True} for o in obstacles_payload]
        return _ImmediateAsyncResult({"site_id": site_id, "obstacles": applied})

    import solarfit.workers.celery_app as celery_app_module

    monkeypatch.setattr(celery_app_module.apply_obstacles_task, "delay", _fake_delay)

    result = router_module.orchestrate_assessment("site-1")

    assert len(delay_calls) == 1
    called_site_id, called_payload = delay_calls[0]
    assert called_site_id == "site-1"  # the REAL site id, never a synthetic cache one
    assert called_payload[0]["type"] == "water_tank"
    assert get_calls.count("site-1") == 2  # fetched once at the top, refetched after apply
    assert result.vision_refinement.obstacles[0].applied is True

    expected = compute_usable_area_m2(site_after_apply.model_copy(update={"boundary": stub_pipeline["analysis"].boundary}))
    assert result.usable_area_m2 == pytest.approx(expected)
    # And it's genuinely smaller than if the exclusion had never been
    # picked up — proves the refetch-after-apply actually matters, not
    # just that the two numbers happen to match.
    before_apply = compute_usable_area_m2(
        stub_pipeline["site"].model_copy(update={"boundary": stub_pipeline["analysis"].boundary})
    )
    assert result.usable_area_m2 < before_apply


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


# stub_pipeline's make_site() defaults to owner_org="Test Org" (see conftest.py).
_HEADERS = {"X-Owner-Org": "Test Org"}


def test_post_assessment_returns_200_with_full_body(db_backed_dependencies, stub_pipeline):
    client = TestClient(app)

    response = client.post("/v1/assessments/site-1", headers=_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["site_id"] == "site-1"
    assert body["constraint_pack_version"] == "rooftop_v1"


def test_post_assessment_requires_auth(db_backed_dependencies, stub_pipeline):
    """API-06 — the gap this phase closes: previously this endpoint had
    no authentication at all."""
    client = TestClient(app)

    response = client.post("/v1/assessments/site-1")

    assert response.status_code == 401


def test_post_assessment_returns_404_for_another_tenants_site(db_backed_dependencies, stub_pipeline):
    """404, not 403 — confirming the id exists at all would itself leak
    cross-tenant information (same reasoning as sites.py's _owned_or_404)."""
    client = TestClient(app)

    response = client.post("/v1/assessments/site-1", headers={"X-Owner-Org": "Someone Else's Org"})

    assert response.status_code == 404


def test_post_assessment_returns_404_for_unknown_site(db_backed_dependencies, stub_pipeline):
    client = TestClient(app)

    response = client.post("/v1/assessments/does-not-exist", headers=_HEADERS)

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
    response = client.post("/v1/assessments/batch", json={"site_ids": ["site-1"]}, headers=_HEADERS)

    assert response.status_code == 200
    assert response.json() == {"job_id": "job-123"}


def test_post_batch_assessment_requires_auth(db_backed_dependencies, stub_pipeline):
    client = TestClient(app)

    response = client.post("/v1/assessments/batch", json={"site_ids": ["site-1"]})

    assert response.status_code == 401


def test_post_batch_assessment_rejects_a_site_from_another_tenant(db_backed_dependencies, stub_pipeline, monkeypatch):
    from solarfit.workers.tasks_assessments import run_batch_assessment as batch_task

    dispatched = []
    monkeypatch.setattr(batch_task, "delay", lambda site_ids: dispatched.append(site_ids))

    client = TestClient(app)
    response = client.post(
        "/v1/assessments/batch", json={"site_ids": ["site-1"]}, headers={"X-Owner-Org": "Someone Else's Org"}
    )

    assert response.status_code == 404
    assert dispatched == []  # never enqueued — the ownership check runs before dispatch


def test_get_batch_assessment_status_requires_auth(db_backed_dependencies, stub_pipeline):
    client = TestClient(app)

    response = client.get("/v1/assessments/batch/job-123")

    assert response.status_code == 401


def test_get_batch_assessment_status_maps_celery_state(db_backed_dependencies, stub_pipeline, monkeypatch):
    class FakeAsyncResult:
        status = "SUCCESS"
        result: ClassVar = [{"site_id": "site-1", "status": "ok", "result": {}}]

        def successful(self):
            return True

    monkeypatch.setattr(router_module.celery_app, "AsyncResult", lambda job_id: FakeAsyncResult())

    client = TestClient(app)
    response = client.get("/v1/assessments/batch/job-123", headers=_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "SUCCESS"
    assert body["results"] == [{"site_id": "site-1", "status": "ok", "result": {}}]
