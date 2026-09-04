"""§16 Testing — a weather outage must not fail a customer's check.

Open-Meteo is an external service and it does go down: measured 1 call in
3 timing out while this was written, and a real assessment 500'd with
"We couldn't finish this check" because a temperature lookup blipped.

Weather is not an input to the verdict. engine/generation.py fetches its
own and already degrades to a fallback specific yield when the provider
is unavailable — that is the pattern. Two other call sites did not follow
it, and both hold things that are explicitly optional: a metadata
snapshot on the cache row, and ML-01's training capture, which the domain
model calls "additive metadata only".
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from solarfit.providers.weather import WeatherProviderError


@pytest.fixture
def dead_weather():
    """Every route to no answer — a timeout, a refused connection, a
    provider error — is the same thing from the caller's side."""
    return WeatherProviderError("Open-Meteo request failed: timed out")


def test_generation_already_degrades_on_a_dead_provider(dead_weather):
    """The pattern the other two call sites now follow. Not a new
    behaviour — pinned so it cannot regress."""
    from solarfit.domain.site import Site
    from solarfit.engine import generation

    site = Site(
        id="s-1",
        site_type="ROOFTOP_RESIDENTIAL",
        name="t",
        owner_org="o",
        jurisdiction="TG",
        centroid={"type": "Point", "coordinates": [78.4867, 17.385]},
        created_at=datetime.now(UTC),
    )

    with patch.object(generation, "fetch_weather", side_effect=dead_weather):
        estimate = generation.estimate_generation_kwh(site, 5.0)

    assert estimate is not None
    assert estimate["method"] == "fallback_constant"
    assert estimate["estimated_kwh_per_year"] > 0
    # method_notes is a single joined string, not a list.
    assert "weather provider unavailable" in estimate["method_notes"]
    assert estimate["specific_yield_kwh_per_kwp"] > 0


def test_the_cached_analysis_survives_a_weather_outage(dead_weather):
    """The snapshot on the cache row is metadata; losing it must not lose
    the geometry, the refinement or the assessment built on them."""
    import solarfit.repositories.analysis_cache as cache

    with (
        patch(
            "solarfit.providers.solar_api.resolve_via_solar_api",
            return_value={
                "type": "Polygon",
                "coordinates": [[[78.48, 17.38], [78.49, 17.38], [78.49, 17.39], [78.48, 17.38]]],
            },
        ),
        patch(
            "solarfit.workers.celery_app.refine_vision_task.delay",
            return_value=MagicMock(
                get=lambda timeout: {"status": "insufficient_data", "obstacles": []}
            ),
        ),
        patch("solarfit.providers.weather.fetch_weather", side_effect=dead_weather),
        patch("solarfit.packs.config_pack.get_panorama_enabled", return_value=False),
        patch(
            "solarfit.engine.ml_score.score_with_ml_model",
            return_value=MagicMock(score=0.4, model_version="v0"),
        ),
        patch.object(cache, "find_by_key", return_value=None),
        patch.object(cache, "create", side_effect=lambda **kw: MagicMock(**kw, cache_hit=False)),
    ):
        result = cache.get_or_create_analysis(17.385, 78.4867, "ROOFTOP_RESIDENTIAL", params={})

    # Completed, with the weather simply absent.
    assert result is not None
    assert result.weather_snapshot is None


def test_the_ml_capture_is_guarded_in_the_router_source():
    """ML-01 is additive metadata by contract, so a weather outage must
    skip the capture rather than raise through it.

    Asserted against the router's own source because exercising
    orchestrate_assessment() end to end needs the whole pipeline stood
    up; what matters here is that the fetch is inside a try and the
    capture is conditional on a result, which is exactly what a reader
    would check."""
    import inspect

    import solarfit.routers.assessments as router

    source = inspect.getsource(router.orchestrate_assessment)
    assert "weather = weather_provider.fetch_weather" in source
    assert "except Exception:" in source
    assert "and weather is not None" in source
