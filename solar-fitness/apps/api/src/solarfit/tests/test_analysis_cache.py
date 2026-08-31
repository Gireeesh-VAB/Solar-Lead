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


class _FakeRefinement:
    """Mimics VisionRefinement closely enough for the mocked pipeline:
    a real .obstacles list attribute (get_or_create_analysis reads/
    reassigns it around the OBS-04/05 apply_or_flag() call) plus
    .model_dump() reflecting whatever .obstacles currently holds."""

    def __init__(self):
        self.confidence = 0.5
        self.obstruction_notes: list[str] = []
        self.obstacles: list = []

    def model_dump(self):
        return {
            "confidence": self.confidence,
            "obstruction_notes": self.obstruction_notes,
            "obstacles": self.obstacles,
        }


def test_get_or_create_analysis_cache_miss_calls_the_full_pipeline_once(clean_key):
    lat, lng, _lat_r, _lng_r = clean_key

    with (
        patch("solarfit.providers.solar_api.resolve_via_solar_api", return_value=BOUNDARY) as geo,
        patch("solarfit.providers.vision.fetch_rgb_imagery", return_value=b"fake-geotiff-bytes") as fetch_img,
        patch("solarfit.providers.vision.crop_to_boundary", return_value=b"fake-png-bytes") as crop,
        patch(
            "solarfit.providers.vision.refine_with_vision_model",
            return_value=_FakeRefinement(),
        ) as vis,
        patch("solarfit.engine.obstacles.apply_or_flag", return_value=[]) as obs,
        patch("solarfit.providers.weather.fetch_weather", return_value={"cloud_cover": 20}) as weather,
        patch(
            "solarfit.engine.panorama.generate_panorama",
            return_value=type("P", (), {"url": "https://example.com/p2.glb"})(),
        ) as viz,
        patch(
            "solarfit.engine.ml_score.score_with_ml_model",
            return_value=type("M", (), {"score": 0.42, "model_version": "v0"})(),
        ) as ml,
    ):
        result = get_or_create_analysis(lat, lng, "ROOFTOP_RESIDENTIAL", params={})

    assert result.cache_hit is False  # CACHE-03: pipeline ran exactly once, on the miss
    geo.assert_called_once()
    fetch_img.assert_called_once()
    crop.assert_called_once()
    vis.assert_called_once()
    obs.assert_called_once()
    synthetic_site = obs.call_args[0][0]
    assert synthetic_site.boundary == BOUNDARY  # the synthetic Site carries the resolved boundary
    # Item 3: placeholder identity fields must be an unmistakable poison
    # marker, never a plausible-looking value like "unknown".
    assert synthetic_site.owner_org == "SYNTHETIC_CACHE_SITE_NOT_REAL_DATA"
    assert synthetic_site.jurisdiction == "SYNTHETIC_CACHE_SITE_NOT_REAL_DATA"
    weather.assert_called_once()
    viz.assert_called_once()
    ml.assert_called_once()


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
        patch("solarfit.providers.vision.fetch_rgb_imagery", return_value=b"fake-geotiff-bytes"),
        patch("solarfit.providers.vision.crop_to_boundary", return_value=b"fake-png-bytes"),
        patch("solarfit.providers.vision.refine_with_vision_model", return_value=_FakeRefinement()),
        patch("solarfit.engine.obstacles.apply_or_flag", return_value=[]),
        patch("solarfit.providers.weather.fetch_weather", return_value={}),
        patch("solarfit.engine.panorama.generate_panorama", return_value=type("P", (), {"url": None})()),
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
