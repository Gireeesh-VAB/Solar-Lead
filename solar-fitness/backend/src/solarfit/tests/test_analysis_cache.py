"""§16 Testing — 'Cache' row, and the Day-1 verification for §9.14
Result Cache (CACHE-01..05).

Runs against the real solarfit-postgres-1 container (see
infra/docker-compose.yml) — these are integration tests, not unit
tests with a fake DB, since the whole point of this layer is real
PostGIS round-tripping.
"""

from unittest.mock import patch

import pytest
from sqlalchemy.exc import IntegrityError

from solarfit.repositories.analysis_cache import (
    create,
    find_by_key,
    force_refresh,
    get_or_create_analysis,
    round_latlng,
)

BOUNDARY = {
    "type": "Polygon",
    "coordinates": [[[78.222, 17.111], [78.223, 17.111], [78.223, 17.112], [78.222, 17.112], [78.222, 17.111]]],
}


@pytest.fixture
def clean_key():
    """A rounded lat/long key guaranteed empty before and after the test."""
    lat, lng = 19.99991, 80.88882
    lat_r, lng_r = round_latlng(lat, lng)
    force_refresh(lat, lng)
    yield lat, lng, lat_r, lng_r
    force_refresh(lat, lng)


def test_round_latlng_uses_config_pack_precision():
    # rooftop_v1.yaml's placeholder cache_precision is 5 (see packages/config-packs).
    assert round_latlng(17.123456789, 78.987654321) == (17.12346, 78.98765)


def test_round_latlng_explicit_precision_overrides_config():
    assert round_latlng(17.123456789, 78.987654321, precision=2) == (17.12, 78.99)


def test_create_then_find_by_key_is_a_hit(clean_key):
    _lat, _lng, lat_r, lng_r = clean_key

    assert find_by_key(lat_r, lng_r) is None  # CACHE-01/02: miss before anything is stored

    created = create(
        lat_rounded=lat_r,
        lng_rounded=lng_r,
        boundary=BOUNDARY,
        vision_refinement={"confidence": 0.8, "obstruction_notes": [], "obstacles": []},
        weather_snapshot={"cloud_cover": 5},
        panorama_url="https://example.com/panorama.glb",
        ml_suitability_score=0.65,
        ml_model_version="v0-test",
    )
    assert created.cache_hit is False

    found = find_by_key(lat_r, lng_r)
    assert found is not None
    assert found.cache_hit is True  # CACHE-05: a hit is always recorded as a hit
    assert found.reused_from_analysis_id is not None
    assert found.boundary["type"] == "Polygon"
    assert found.vision_refinement.confidence == 0.8
    assert found.panorama.url == "https://example.com/panorama.glb"
    assert found.ml_score.score == 0.65


def test_different_rounding_buckets_never_collide(clean_key):
    lat, lng, lat_r, lng_r = clean_key
    create(lat_rounded=lat_r, lng_rounded=lng_r, boundary=BOUNDARY)

    # A neighbouring key (different rounded bucket) must still be a miss.
    other_lat_r, other_lng_r = round_latlng(lat + 1.0, lng + 1.0)
    assert find_by_key(other_lat_r, other_lng_r) is None


def test_force_refresh_clears_an_existing_entry(clean_key):
    lat, lng, lat_r, lng_r = clean_key
    create(lat_rounded=lat_r, lng_rounded=lng_r, boundary=BOUNDARY)
    assert find_by_key(lat_r, lng_r) is not None

    force_refresh(lat, lng)  # CACHE-04: explicit, admin-triggered only

    assert find_by_key(lat_r, lng_r) is None


def test_get_or_create_analysis_cache_hit_makes_zero_downstream_calls(clean_key):
    lat, lng, lat_r, lng_r = clean_key
    create(lat_rounded=lat_r, lng_rounded=lng_r, boundary=BOUNDARY)

    with (
        patch("solarfit.providers.solar_api.resolve_via_solar_api") as geo,
        patch("solarfit.providers.vision.refine_with_vision_model") as vis,
        patch("solarfit.providers.weather.fetch_weather") as weather,
        patch("solarfit.engine.panorama.generate_panorama") as viz,
        patch("solarfit.engine.ml_score.score_with_ml_model") as ml,
    ):
        result = get_or_create_analysis(lat, lng, "ROOFTOP_RESIDENTIAL", params={})

    assert result.cache_hit is True  # CACHE-02: zero external calls on a hit
    geo.assert_not_called()
    vis.assert_not_called()
    weather.assert_not_called()
    viz.assert_not_called()
    ml.assert_not_called()


class _ImmediateAsyncResult:
    """Fakes the Celery AsyncResult get_or_create_analysis() gets back
    from .delay() — .get(timeout=...) just returns the value immediately,
    since these tests mock .delay() itself rather than running a real
    worker/broker."""

    def __init__(self, value):
        self._value = value

    def get(self, timeout=None):
        return self._value


# Plain dicts, matching what refine_vision_task/generate_panorama_task
# actually return (each ends in a .model_dump() call — see
# workers/celery_app.py) — not VisionRefinement/PanoramaResult objects,
# since that's the real task boundary shape get_or_create_analysis()
# receives from .get().
_FAKE_REFINEMENT_DICT = {
    "corrected_boundary": None,
    "obstruction_notes": [],
    "obstacles": [],
    "confidence": 0.5,
    "status": "ok",
}
_FAKE_PANORAMA_DICT = {
    "url": "https://example.com/p2.glb",
    "status": "ok",
    "reason": None,
    "generated_at": None,
    "version": None,
}


def test_get_or_create_analysis_cache_miss_calls_the_full_pipeline_once(clean_key):
    lat, lng, _lat_r, _lng_r = clean_key

    with (
        patch("solarfit.providers.solar_api.resolve_via_solar_api", return_value=BOUNDARY) as geo,
        patch(
            "solarfit.workers.celery_app.refine_vision_task.delay",
            return_value=_ImmediateAsyncResult(_FAKE_REFINEMENT_DICT),
        ) as vis,
        patch("solarfit.providers.weather.fetch_weather", return_value={"cloud_cover": 20}) as weather,
        patch(
            "solarfit.workers.celery_app.generate_panorama_task.delay",
            return_value=_ImmediateAsyncResult(_FAKE_PANORAMA_DICT),
        ) as viz,
        patch(
            "solarfit.engine.ml_score.score_with_ml_model",
            return_value=type("M", (), {"score": 0.42, "model_version": "v0"})(),
        ) as ml,
    ):
        result = get_or_create_analysis(lat, lng, "ROOFTOP_RESIDENTIAL", params={})

    assert result.cache_hit is False  # CACHE-03: pipeline ran exactly once, on the miss
    geo.assert_called_once()
    vis.assert_called_once_with(lat, lng, BOUNDARY)  # VIS-05: dispatched, not called inline
    weather.assert_called_once()
    viz.assert_called_once()  # VIZ-05: dispatched, not called inline
    ml.assert_called_once()
    # Obstacle classification/apply is no longer done here (moved to
    # orchestrate_assessment(), which has a real site to apply against) —
    # the raw detection just passes through untouched.
    assert result.vision_refinement.obstacles == []


def test_get_or_create_analysis_cache_miss_runs_the_real_solar_api_provider(clean_key):
    """Regression test: `resolve_via_solar_api()` itself runs for real
    here (only `resolve_for_location`, the true external-HTTP boundary,
    is faked) — every other test in this file mocks
    `resolve_via_solar_api` directly, which is exactly why a prior bug
    (passing site=None into it, since this function's real call site
    always hands it an empty params dict) went uncaught: the real
    site.centroid access inside resolve_via_solar_api() never actually
    ran against anything. This test exercises that access for real."""
    lat, lng, _lat_r, _lng_r = clean_key

    from solarfit.providers.solar_api import SolarApiResult

    with (
        patch(
            "solarfit.providers.solar_api.resolve_for_location",
            return_value=SolarApiResult(status="ok", boundary=BOUNDARY),
        ) as resolve_location,
        patch(
            "solarfit.workers.celery_app.refine_vision_task.delay",
            return_value=_ImmediateAsyncResult(_FAKE_REFINEMENT_DICT),
        ),
        patch("solarfit.providers.weather.fetch_weather", return_value={"cloud_cover": 20}),
        patch(
            "solarfit.workers.celery_app.generate_panorama_task.delay",
            return_value=_ImmediateAsyncResult({**_FAKE_PANORAMA_DICT, "url": None}),
        ),
        patch(
            "solarfit.engine.ml_score.score_with_ml_model",
            return_value=type("M", (), {"score": None, "model_version": None})(),
        ),
    ):
        result = get_or_create_analysis(lat, lng, "ROOFTOP_RESIDENTIAL", params={})

    assert result.cache_hit is False
    assert result.boundary == BOUNDARY
    # resolve_for_location must have been reached with the real (lat, lng)
    # — proves the synthetic geo-lookup Site's centroid carried them
    # through resolve_via_solar_api() correctly, not a None crash.
    resolve_location.assert_called_once()
    called_lat, called_lng = resolve_location.call_args[0][:2]
    assert called_lat == pytest.approx(lat)
    assert called_lng == pytest.approx(lng)


def test_get_or_create_analysis_recovers_from_concurrent_insert_race(clean_key):
    lat, lng, lat_r, lng_r = clean_key

    # A row "another process" inserted concurrently, for the exception
    # handler's find_by_key() re-check to discover.
    create(lat_rounded=lat_r, lng_rounded=lng_r, boundary=BOUNDARY)
    concurrent_hit = find_by_key(lat_r, lng_r)
    assert concurrent_hit is not None

    with (
        # First call (the initial check) sees a miss, same as the real race;
        # second call (inside the except handler) discovers the concurrent row.
        patch("solarfit.repositories.analysis_cache.find_by_key", side_effect=[None, concurrent_hit]),
        patch(
            "solarfit.repositories.analysis_cache.create",
            side_effect=IntegrityError("INSERT", {}, Exception("duplicate key value")),
        ),
        patch("solarfit.providers.solar_api.resolve_via_solar_api", return_value=BOUNDARY),
        patch(
            "solarfit.workers.celery_app.refine_vision_task.delay",
            return_value=_ImmediateAsyncResult(_FAKE_REFINEMENT_DICT),
        ),
        patch("solarfit.providers.weather.fetch_weather", return_value={}),
        patch(
            "solarfit.workers.celery_app.generate_panorama_task.delay",
            return_value=_ImmediateAsyncResult({**_FAKE_PANORAMA_DICT, "url": None}),
        ),
        patch(
            "solarfit.engine.ml_score.score_with_ml_model",
            return_value=type("M", (), {"score": None, "model_version": None})(),
        ),
    ):
        result = get_or_create_analysis(lat, lng, "ROOFTOP_RESIDENTIAL", params={})

    # CACHE-02/05: a location someone else just cached must come back as a
    # hit, never as a crash or a silently-overwritten second row.
    assert result.cache_hit is True
    assert result.reused_from_analysis_id == concurrent_hit.reused_from_analysis_id

    # A second call for the same location must now be a hit with no further calls.
    with patch("solarfit.providers.solar_api.resolve_via_solar_api") as geo2:
        second = get_or_create_analysis(lat, lng, "ROOFTOP_RESIDENTIAL", params={})
    assert second.cache_hit is True
    geo2.assert_not_called()
