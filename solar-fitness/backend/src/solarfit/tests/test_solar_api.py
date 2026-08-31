"""GEO-04 (SOLAR_API) and SHADE-01 — Person 1.

No network and no API key: Google's HTTP layer is mocked with
httpx.MockTransport, and the response fixtures mirror the documented
Building Insights shape. The parsing decisions — which are where all the
judgement lives — are exercised directly.

The absent/BASE-tier/sparse cases get as much attention as the happy
path on purpose. GEO-04 says those must be recorded rather than raised,
and in India they are the common case, not the edge case.
"""

import httpx
import pytest

from solarfit.domain.site import ShadingEstimate, Site
from solarfit.providers import solar_api
from solarfit.providers.validation import GeometryRejected

LON, LAT = 78.4867, 17.3850


def _insights(
    *,
    quality: str = "HIGH",
    with_bbox: bool = True,
    segments: int = 3,
    max_sunshine: float | None = 1800.0,
    quantiles: list[float] | None = None,
) -> dict:
    payload: dict = {
        "name": "buildings/ChIJtest",
        "center": {"latitude": LAT, "longitude": LON},
        "imageryQuality": quality,
        "imageryDate": {"year": 2024, "month": 3, "day": 15},
        "solarPotential": {
            "maxArrayPanelsCount": 42,
            "wholeRoofStats": {
                "areaMeters2": 240.5,
                "sunshineQuantiles": quantiles
                if quantiles is not None
                else [1200.0, 1400.0, 1550.0, 1650.0, 1700.0, 1750.0, 1780.0],
            },
            "roofSegmentStats": [
                {
                    "pitchDegrees": 15.0,
                    "azimuthDegrees": 180.0,
                    "stats": {"areaMeters2": 80.0, "sunshineQuantiles": [1500.0, 1700.0]},
                }
                for _ in range(segments)
            ],
        },
    }
    if max_sunshine is not None:
        payload["solarPotential"]["maxSunshineHoursPerYear"] = max_sunshine
    if with_bbox:
        payload["boundingBox"] = {
            "sw": {"latitude": LAT, "longitude": LON},
            "ne": {"latitude": LAT + 0.0005, "longitude": LON + 0.0005},
        }
    return payload


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def _fake_key(monkeypatch):
    """A key must exist for the request to be built; its value never
    reaches a real server because the transport is mocked."""
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_SOLAR_API_KEY", "test-key")
    from solarfit.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _site(centroid: dict | None = None) -> Site:
    from datetime import UTC, datetime

    return Site(
        id="site-1",
        site_type="ROOFTOP_RESIDENTIAL",
        name="Test",
        owner_org="org",
        jurisdiction="IN-TG",
        centroid=centroid or {"type": "Point", "coordinates": [LON, LAT]},
        created_at=datetime(2026, 8, 27, tzinfo=UTC),
    )


# --------------------------------------------------------------------- #
# geometry from boundingBox
# --------------------------------------------------------------------- #


def test_bounding_box_becomes_a_closed_polygon():
    poly = solar_api.bounding_box_to_polygon(
        {"sw": {"latitude": LAT, "longitude": LON},
         "ne": {"latitude": LAT + 0.001, "longitude": LON + 0.001}}
    )
    ring = poly["coordinates"][0]
    assert poly["type"] == "Polygon"
    assert len(ring) == 5
    assert ring[0] == ring[-1]  # closed


def test_degenerate_bounding_box_is_rejected():
    with pytest.raises(GeometryRejected, match="zero or negative extent"):
        solar_api.bounding_box_to_polygon(
            {"sw": {"latitude": LAT, "longitude": LON},
             "ne": {"latitude": LAT, "longitude": LON}}
        )


def test_malformed_bounding_box_is_rejected():
    with pytest.raises(GeometryRejected, match="malformed"):
        solar_api.bounding_box_to_polygon({"sw": {"latitude": LAT}})


# --------------------------------------------------------------------- #
# SHADE-01
# --------------------------------------------------------------------- #


def test_shading_extracted_from_the_same_response():
    """No second call: the fields come out of the GEO-04 payload."""
    shading = ShadingEstimate(**solar_api.extract_shading_estimate(_insights()))
    assert shading.source == "solar_api"
    assert shading.sunshine_hours_per_year == 1800.0
    # median of the quantiles (1650) / max (1800)
    assert shading.shading_score == pytest.approx(1650.0 / 1800.0, abs=1e-3)


def test_a_well_lit_roof_scores_near_one():
    payload = _insights(max_sunshine=1800.0, quantiles=[1780.0, 1790.0, 1795.0])
    shading = ShadingEstimate(**solar_api.extract_shading_estimate(payload))
    assert shading.shading_score > 0.95


def test_a_shaded_roof_scores_low():
    payload = _insights(max_sunshine=1800.0, quantiles=[400.0, 600.0, 700.0])
    shading = ShadingEstimate(**solar_api.extract_shading_estimate(payload))
    assert shading.shading_score < 0.45


def test_missing_sunshine_data_is_unavailable_not_zero():
    """SHADE-01/04: 'we don't know' and 'fully shaded' must not collapse
    into the same number — Person 4 reads unavailable as
    INSUFFICIENT_DATA rather than scoring it."""
    payload = _insights(max_sunshine=None, quantiles=[])
    shading = ShadingEstimate(**solar_api.extract_shading_estimate(payload))
    assert shading.source == "unavailable"
    assert shading.shading_score is None


def test_zero_max_sunshine_is_unavailable_not_a_divide_by_zero():
    payload = _insights(max_sunshine=0.0)
    assert solar_api.extract_shading_estimate(payload)["source"] == "unavailable"


def test_shading_falls_back_to_segment_quantiles():
    payload = _insights()
    payload["solarPotential"]["wholeRoofStats"].pop("sunshineQuantiles")
    shading = ShadingEstimate(**solar_api.extract_shading_estimate(payload))
    assert shading.source == "solar_api"


# --------------------------------------------------------------------- #
# GEO-04 — parsing outcomes
# --------------------------------------------------------------------- #


def test_high_quality_response_resolves():
    result = solar_api.resolve_from_payload(_insights(quality="HIGH"))
    assert result.status == "ok"
    assert result.usable
    assert result.imagery_quality == "HIGH"
    assert result.segment_count == 3
    assert result.roof_area_m2 == 240.5
    assert result.imagery_date.year == 2024
    assert result.shading.source == "solar_api"


def test_base_tier_is_recorded_not_rejected():
    """GEO-04: 'handle absent, BASE-tier and sparse responses without
    failure'. BASE is usable — it just deserves lower confidence."""
    result = solar_api.resolve_from_payload(_insights(quality="BASE"))
    assert result.status == "base_tier"
    assert result.usable
    assert result.boundary is not None


def test_response_without_a_bounding_box_is_sparse_not_an_error():
    result = solar_api.resolve_from_payload(_insights(with_bbox=False))
    assert result.status == "sparse"
    assert not result.usable
    assert "boundingBox" in result.detail
    # Shading is still harvested even though geometry failed.
    assert result.shading.source == "solar_api"


def test_building_with_no_roof_segments_is_sparse():
    result = solar_api.resolve_from_payload(_insights(segments=0))
    assert result.status == "sparse"
    assert result.segment_count == 0
    assert "no roof segments" in result.detail


def test_result_always_carries_a_status():
    for payload in (_insights(), _insights(with_bbox=False), {}):
        assert solar_api.resolve_from_payload(payload).status


# --------------------------------------------------------------------- #
# GEO-04 — HTTP outcomes
# --------------------------------------------------------------------- #


def test_no_coverage_returns_a_status_rather_than_raising():
    """404 from findClosest means 'no building here'. Common in India,
    and emphatically not an exception."""

    def handler(request):
        return httpx.Response(404, json={"error": {"message": "Requested entity was not found."}})

    result = solar_api.resolve_for_location(LAT, LON, client=_client(handler))
    assert result.status == "no_coverage"
    assert not result.usable


def test_server_error_is_recorded_as_error():
    def handler(request):
        return httpx.Response(500, json={"error": {"message": "backend error"}})

    result = solar_api.resolve_for_location(LAT, LON, client=_client(handler))
    assert result.status == "error"
    assert "backend error" in result.detail


def test_network_failure_is_recorded_not_raised():
    def handler(request):
        raise httpx.ConnectError("connection refused")

    result = solar_api.resolve_for_location(LAT, LON, client=_client(handler))
    assert result.status == "error"
    assert "failed" in result.detail


def test_successful_location_lookup():
    def handler(request):
        assert "buildingInsights:findClosest" in str(request.url)
        return httpx.Response(200, json=_insights())

    result = solar_api.resolve_for_location(LAT, LON, client=_client(handler))
    assert result.status == "ok"
    assert result.usable


# --------------------------------------------------------------------- #
# geocoding
# --------------------------------------------------------------------- #


def test_address_resolves_end_to_end():
    def handler(request):
        if "geocode" in str(request.url):
            return httpx.Response(
                200,
                json={"status": "OK",
                      "results": [{"geometry": {"location": {"lat": LAT, "lng": LON}}}]},
            )
        return httpx.Response(200, json=_insights())

    result = solar_api.resolve_for_address("Banjara Hills, Hyderabad", client=_client(handler))
    assert result.status == "ok"
    assert result.usable
    assert result.shading.source == "solar_api"


def test_unknown_address_is_reported_not_raised():
    def handler(request):
        return httpx.Response(200, json={"status": "ZERO_RESULTS", "results": []})

    result = solar_api.resolve_for_address("nowhere at all", client=_client(handler))
    assert result.status == "geocode_failed"
    assert not result.usable


def test_geocoder_error_status_raises():
    """A quota or key problem is our fault, not the address's — that one
    does raise, so it surfaces instead of looking like a bad address."""

    def handler(request):
        return httpx.Response(200, json={"status": "REQUEST_DENIED",
                                         "error_message": "key not authorised"})

    with pytest.raises(solar_api.SolarApiError, match="REQUEST_DENIED"):
        solar_api.geocode_address("anywhere", client=_client(handler))


# --------------------------------------------------------------------- #
# provider contract
# --------------------------------------------------------------------- #


def test_provider_returns_a_boundary():
    def handler(request):
        return httpx.Response(200, json=_insights())

    boundary = solar_api.resolve_via_solar_api(_site(), {"client": _client(handler)})
    assert boundary["type"] == "Polygon"


def test_provider_raises_when_nothing_resolves():
    def handler(request):
        return httpx.Response(404, json={})

    with pytest.raises(GeometryRejected, match="no_coverage"):
        solar_api.resolve_via_solar_api(_site(), {"client": _client(handler)})


def test_provider_is_registered_and_ranked_lowest():
    from solarfit.providers import base

    assert "solar_api" in [p.id for p in base.registered_providers()]
    assert base.PRECEDENCE["solar_api"] < base.PRECEDENCE["manual_polygon"]


def test_missing_key_raises_a_clear_error(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "")
    monkeypatch.setenv("GOOGLE_SOLAR_API_KEY", "")
    from solarfit.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(solar_api.SolarApiError, match="no Google API key"):
        solar_api.geocode_address("anywhere")
    get_settings.cache_clear()
