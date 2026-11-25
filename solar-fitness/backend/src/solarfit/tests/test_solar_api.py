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


# --------------------------------------------------------------------- #
# roof pitch at a point (StartCheckWizard Locate step)
# --------------------------------------------------------------------- #


def _segment(pitch=18.6, azimuth=135.0, bbox=None, center=None, height=142.3, area=32.0):
    seg = {
        "pitchDegrees": pitch,
        "azimuthDegrees": azimuth,
        "planeHeightAtCenterMeters": height,
        "stats": {"areaMeters2": area, "groundAreaMeters2": area * 0.9},
    }
    if bbox is not None:
        seg["boundingBox"] = bbox
    if center is not None:
        seg["center"] = center
    return seg


def test_compass_direction_matches_frontend_convention():
    assert solar_api.compass_direction(0) == "N"
    assert solar_api.compass_direction(90) == "E"
    assert solar_api.compass_direction(180) == "S"
    assert solar_api.compass_direction(135) == "SE"
    assert solar_api.compass_direction(-45) == "NW"  # wraps negative into 0..360


def test_match_roof_segment_prefers_containment_over_nearest():
    bbox_a = {"sw": {"latitude": 10.0, "longitude": 20.0}, "ne": {"latitude": 10.001, "longitude": 20.001}}
    bbox_b = {"sw": {"latitude": 10.002, "longitude": 20.002}, "ne": {"latitude": 10.003, "longitude": 20.003}}
    segments = [_segment(bbox=bbox_a), _segment(bbox=bbox_b)]

    match = solar_api.match_roof_segment(segments, lat=10.0005, lng=20.0005)
    assert match == (0, "contains")


def test_match_roof_segment_falls_back_to_nearest_center():
    segments = [
        _segment(center={"latitude": 10.0, "longitude": 20.0}),
        _segment(center={"latitude": 50.0, "longitude": 60.0}),
    ]
    match = solar_api.match_roof_segment(segments, lat=10.001, lng=20.001)
    assert match == (0, "nearest")


def test_match_roof_segment_none_when_no_segment_has_geometry():
    segments = [{"pitchDegrees": 20.0, "azimuthDegrees": 180.0}]
    assert solar_api.match_roof_segment(segments, lat=10.0, lng=20.0) is None


def test_roof_pitch_at_point_reports_the_matched_segments_real_values():
    bbox = {"sw": {"latitude": 10.0, "longitude": 20.0}, "ne": {"latitude": 10.001, "longitude": 20.001}}
    payload = {"solarPotential": {"roofSegmentStats": [_segment(pitch=18.6, azimuth=135.0, bbox=bbox)]}}

    pitch = solar_api.roof_pitch_at_point(payload, lat=10.0005, lng=20.0005, imagery_quality="HIGH")

    assert pitch is not None
    assert pitch.pitch_deg == 18.6
    assert pitch.orientation == "SE"
    assert pitch.plane_height_m == 142.3
    assert pitch.matched_by == "contains"
    assert pitch.confidence == "high"  # contains + non-BASE imagery


def test_roof_pitch_at_point_downgrades_confidence_on_base_tier():
    bbox = {"sw": {"latitude": 10.0, "longitude": 20.0}, "ne": {"latitude": 10.001, "longitude": 20.001}}
    payload = {"solarPotential": {"roofSegmentStats": [_segment(bbox=bbox)]}}

    pitch = solar_api.roof_pitch_at_point(payload, lat=10.0005, lng=20.0005, imagery_quality="BASE")

    assert pitch is not None
    assert pitch.matched_by == "contains"
    assert pitch.confidence == "medium"  # contains, but BASE tier


def test_roof_pitch_at_point_is_none_without_segments():
    payload = {"solarPotential": {"roofSegmentStats": []}}
    assert solar_api.roof_pitch_at_point(payload, lat=10.0, lng=20.0, imagery_quality="HIGH") is None


def test_roof_pitch_at_point_never_fabricates_a_missing_pitch():
    """A segment with geometry but no pitch/azimuth (never seen from the
    real API, but not impossible from a degraded response) must not
    produce a pitch — GEO-04's 'record, don't fabricate' rule applies
    here too."""
    bbox = {"sw": {"latitude": 10.0, "longitude": 20.0}, "ne": {"latitude": 10.001, "longitude": 20.001}}
    payload = {
        "solarPotential": {
            "roofSegmentStats": [{"boundingBox": bbox, "stats": {"areaMeters2": 10.0}}]
        }
    }
    assert solar_api.roof_pitch_at_point(payload, lat=10.0005, lng=20.0005, imagery_quality="HIGH") is None


# --------------------------------------------------------------------- #
# GEO-10 — roof-segment match tolerance (small Google-side boundingBox
# offsets should not automatically read as "nearest"/low confidence)
# --------------------------------------------------------------------- #

_METERS_PER_DEG_LAT = 111_320.0


def _meters_per_deg_lng(lat: float) -> float:
    import math

    return _METERS_PER_DEG_LAT * math.cos(math.radians(lat))


def _offset_point_m(lat: float, lng: float, *, north_m: float = 0.0, east_m: float = 0.0):
    """A (lat, lng) shifted by the given metre offsets — flat-plane
    approximation, accurate to well under 1% at these small offsets and
    this latitude, which is precise enough for tolerance-boundary tests
    that deliberately sit a few metres clear on either side."""
    return (
        lat + north_m / _METERS_PER_DEG_LAT,
        lng + east_m / _meters_per_deg_lng(lat),
    )


def test_match_roof_segment_point_exactly_on_bbox_edge_still_contains():
    bbox = {"sw": {"latitude": 10.0, "longitude": 20.0}, "ne": {"latitude": 10.001, "longitude": 20.001}}
    segments = [_segment(bbox=bbox)]
    assert solar_api.match_roof_segment(segments, lat=10.0, lng=20.0) == (0, "contains")


def test_match_roof_segment_tolerates_small_offset_within_configured_tolerance(monkeypatch):
    monkeypatch.setattr("solarfit.packs.config_pack.get_roof_segment_match_tolerance_m", lambda **kw: 5.0)
    bbox = {"sw": {"latitude": LAT, "longitude": LON}, "ne": {"latitude": LAT + 0.001, "longitude": LON + 0.001}}
    segments = [_segment(bbox=bbox)]

    lat, lng = _offset_point_m(LAT, LON, north_m=-2.0)  # 2m south of the bbox, tolerance is 5m
    assert solar_api.match_roof_segment(segments, lat=lat, lng=lng) == (0, "tolerated_contains")


def test_match_roof_segment_beyond_tolerance_falls_back_to_nearest(monkeypatch):
    monkeypatch.setattr("solarfit.packs.config_pack.get_roof_segment_match_tolerance_m", lambda **kw: 5.0)
    bbox = {"sw": {"latitude": LAT, "longitude": LON}, "ne": {"latitude": LAT + 0.001, "longitude": LON + 0.001}}
    center = {"latitude": LAT + 0.0005, "longitude": LON + 0.0005}
    segments = [_segment(bbox=bbox, center=center)]

    lat, lng = _offset_point_m(LAT, LON, north_m=-8.0)  # 8m south of the bbox, tolerance is 5m
    assert solar_api.match_roof_segment(segments, lat=lat, lng=lng) == (0, "nearest")


@pytest.mark.parametrize(
    ("north_m", "east_m"),
    [
        (-2.0, 0.0),  # 2m south of the bbox
        (2.0, 0.0),  # 2m north
        (0.0, -2.0),  # 2m west
        (0.0, 2.0),  # 2m east
        (-2.0, -2.0),  # 2m off diagonally (SW corner)
    ],
)
def test_match_roof_segment_tolerance_applies_symmetrically(monkeypatch, north_m, east_m):
    monkeypatch.setattr("solarfit.packs.config_pack.get_roof_segment_match_tolerance_m", lambda **kw: 5.0)
    bbox = {"sw": {"latitude": LAT, "longitude": LON}, "ne": {"latitude": LAT + 0.001, "longitude": LON + 0.001}}
    segments = [_segment(bbox=bbox)]

    # Anchor the offset from whichever corner/edge it pushes away from, so
    # the same north_m/east_m signs read the same way on every side.
    anchor_lat = LAT if north_m <= 0 else LAT + 0.001
    anchor_lng = LON if east_m <= 0 else LON + 0.001
    lat, lng = _offset_point_m(anchor_lat, anchor_lng, north_m=north_m, east_m=east_m)

    assert solar_api.match_roof_segment(segments, lat=lat, lng=lng) == (0, "tolerated_contains")


def test_match_roof_segment_prefers_closer_of_two_qualifying_tolerant_segments(monkeypatch):
    """Ambiguous case (#6): two segments both within tolerance must pick
    the geometrically closer one deterministically, not whichever comes
    first in the list."""
    monkeypatch.setattr("solarfit.packs.config_pack.get_roof_segment_match_tolerance_m", lambda **kw: 5.0)
    # Pin sits at (LAT, LON). Both boxes' longitude range starts exactly at
    # LON, so the pin is due south of each — a pure, easy-to-verify
    # north-south distance to each box's own southern edge.
    near_south_edge_lat, _ = _offset_point_m(LAT, LON, north_m=2.0)  # box starts 2m north of the pin
    near_north_edge_lat, _ = _offset_point_m(LAT, LON, north_m=7.0)
    far_south_edge_lat, _ = _offset_point_m(LAT, LON, north_m=4.0)  # a second box, 4m north of the pin
    far_north_edge_lat, _ = _offset_point_m(LAT, LON, north_m=9.0)
    _, east_edge_lng = _offset_point_m(LAT, LON, east_m=5.0)
    near_bbox = {
        "sw": {"latitude": near_south_edge_lat, "longitude": LON},
        "ne": {"latitude": near_north_edge_lat, "longitude": east_edge_lng},
    }
    far_bbox = {
        "sw": {"latitude": far_south_edge_lat, "longitude": LON},
        "ne": {"latitude": far_north_edge_lat, "longitude": east_edge_lng},
    }
    # Farther segment listed FIRST — proves selection isn't just "first match".
    segments = [_segment(bbox=far_bbox), _segment(bbox=near_bbox)]

    match = solar_api.match_roof_segment(segments, lat=LAT, lng=LON)
    assert match == (1, "tolerated_contains")


def test_match_roof_segment_real_world_11m_offset_is_not_swallowed_by_default_tolerance():
    """Regression fixture for the investigated case: a real Building
    Insights boundingBox measured ~11m from a pin that was visually on
    the roof. The default tolerance (5m, GEO-10) is deliberately NOT
    tuned to absorb this — it must still fall back to 'nearest', proving
    this fix doesn't just paper over that one example."""
    bbox = {
        "sw": {"latitude": 17.4419585, "longitude": 78.3961317},
        "ne": {"latitude": 17.4420703, "longitude": 78.3962556},
    }
    center = {"latitude": 17.442013, "longitude": 78.3961923}
    segments = [_segment(bbox=bbox, center=center)]

    match = solar_api.match_roof_segment(segments, lat=17.441859002122328, lng=78.39619610185244)
    assert match == (0, "nearest")


def test_roof_pitch_at_point_tolerated_contains_is_medium_regardless_of_imagery(monkeypatch):
    monkeypatch.setattr("solarfit.packs.config_pack.get_roof_segment_match_tolerance_m", lambda **kw: 5.0)
    bbox = {"sw": {"latitude": LAT, "longitude": LON}, "ne": {"latitude": LAT + 0.001, "longitude": LON + 0.001}}
    payload = {"solarPotential": {"roofSegmentStats": [_segment(bbox=bbox)]}}
    lat, lng = _offset_point_m(LAT, LON, north_m=-2.0)

    high_tier = solar_api.roof_pitch_at_point(payload, lat=lat, lng=lng, imagery_quality="HIGH")
    base_tier = solar_api.roof_pitch_at_point(payload, lat=lat, lng=lng, imagery_quality="BASE")

    assert high_tier is not None and high_tier.matched_by == "tolerated_contains"
    assert high_tier.confidence == "medium"  # never "high" — it wasn't an exact match
    assert base_tier is not None and base_tier.matched_by == "tolerated_contains"
    assert base_tier.confidence == "medium"  # never "low" — the offset was validated as small


def test_roof_pitch_at_point_nearest_confidence_by_imagery_tier():
    """Pins the full truth table's remaining two combos: a genuine
    nearest-only match is 'medium' on good imagery and only drops to
    'low' when the imagery is BASE tier too."""
    segments = [_segment(center={"latitude": 10.0, "longitude": 20.0})]
    payload = {"solarPotential": {"roofSegmentStats": segments}}

    good_imagery = solar_api.roof_pitch_at_point(payload, lat=15.0, lng=25.0, imagery_quality="HIGH")
    base_imagery = solar_api.roof_pitch_at_point(payload, lat=15.0, lng=25.0, imagery_quality="BASE")

    assert good_imagery is not None and good_imagery.matched_by == "nearest"
    assert good_imagery.confidence == "medium"
    assert base_imagery is not None and base_imagery.matched_by == "nearest"
    assert base_imagery.confidence == "low"
