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

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from solarfit.db import get_session
from solarfit.main import app
from solarfit.providers.solar_api import MaskVectorization, SolarApiResult
from solarfit.providers.validation import geometry_confidence

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
    # _new_check_body() always supplies lat/lng, so create_site_core()
    # takes the resolve_for_location branch, not resolve_for_address —
    # both are faked here so no test in this file makes a real Solar API
    # call (this was previously a gap: only resolve_for_address was
    # mocked, so every check-creation test silently hit the live network
    # via resolve_for_location and depended on it succeeding to pass).
    monkeypatch.setattr(
        "solarfit.routers.sites.solar_api.resolve_for_address",
        lambda address, **kw: SolarApiResult(status="ok", boundary=BOUNDARY),
    )
    monkeypatch.setattr(
        "solarfit.routers.sites.solar_api.resolve_for_location",
        lambda lat, lng, **kw: SolarApiResult(status="ok", boundary=BOUNDARY),
    )
    # GEO-04's mask upgrade (Phase 2) makes its own, separate Solar API +
    # GeoTIFF download call — faked off here too, so it degrades to the
    # BOUNDARY rectangle above (already what every test in this file
    # asserts against) rather than reaching the network.
    monkeypatch.setattr(
        "solarfit.routers.sites.solar_api.extract_roof_polygon_from_mask",
        lambda lat, lng, **kw: MaskVectorization(polygon=None, competing_regions=0),
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


def test_without_a_mask_the_check_falls_back_to_the_bounding_box(client, make_auth_header):
    """The fixture's extract_roof_polygon_from_mask fake returns None by
    default — this is the "Solar API has no mask at this location/tier"
    path every real check hits some of the time, and it must land the
    site on the same solar_api + approximate=True state it always has."""
    headers = make_auth_header(role="customer", owner_org=None)
    response = client.post("/app/checks", json=_new_check_body(), headers=headers)

    body = response.json()
    assert body["geometrySource"] == "solar_api"
    assert body["boundaryIsApproximate"] is True


def test_a_real_mask_upgrades_the_stored_boundary(client, make_auth_header, monkeypatch):
    """GEO-04's Phase 2 upgrade: when the mask vectorises to a real
    polygon, that — not the bounding box — is what gets stored, tagged
    with the new source, and reported as no longer approximate."""
    mask_polygon = {
        "type": "Polygon",
        "coordinates": [
            [
                [78.48660, 17.38490],
                [78.48664, 17.38490],
                [78.48664, 17.38492],
                [78.48662, 17.38494],
                [78.48660, 17.38492],
                [78.48660, 17.38490],
            ]
        ],
    }
    monkeypatch.setattr(
        "solarfit.routers.sites.solar_api.extract_roof_polygon_from_mask",
        lambda lat, lng, **kw: MaskVectorization(polygon=mask_polygon, competing_regions=0),
    )
    headers = make_auth_header(role="customer", owner_org=None)

    response = client.post("/app/checks", json=_new_check_body(), headers=headers)

    body = response.json()
    assert response.status_code == 201
    assert body["geometrySource"] == "solar_api_mask"
    assert body["boundaryIsApproximate"] is False
    # More than a 4-corner rectangle — the actual shape came through.
    assert len(body["boundary"]) > 4
    assert body["competingBuildingsNearby"] == 0


def test_competing_buildings_nearby_is_surfaced_when_the_mask_found_others(
    client, make_auth_header, monkeypatch
):
    """The building-confidence signal: other disconnected mask regions
    near the pin, even when one of them was still selected as the roof."""
    mask_polygon = {
        "type": "Polygon",
        "coordinates": [
            [
                [78.48660, 17.38490],
                [78.48664, 17.38490],
                [78.48664, 17.38492],
                [78.48662, 17.38494],
                [78.48660, 17.38492],
                [78.48660, 17.38490],
            ]
        ],
    }
    monkeypatch.setattr(
        "solarfit.routers.sites.solar_api.extract_roof_polygon_from_mask",
        lambda lat, lng, **kw: MaskVectorization(polygon=mask_polygon, competing_regions=2),
    )
    headers = make_auth_header(role="customer", owner_org=None)

    response = client.post("/app/checks", json=_new_check_body(), headers=headers)

    assert response.status_code == 201
    assert response.json()["competingBuildingsNearby"] == 2


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


def test_admin_can_read_any_customers_check(client, make_auth_header):
    """Admin's own "Feasibility" review button (opens the customer's own
    result page via GET /app/checks/{id}) needs this — same "admin can
    read any site" precedent app_sites.py::get_site() already has,
    extended to this router's read-only endpoints via
    _readable_check_or_404()."""
    alice = make_auth_header(role="customer", owner_org=None, email="alice3@example.com")
    admin = make_auth_header(role="admin", owner_org=None, email="admin3@example.com")
    created = client.post("/app/checks", json=_new_check_body(), headers=alice).json()

    response = client.get(f"/app/checks/{created['id']}", headers=admin)

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_a_random_vendor_still_cannot_read_someone_elses_check(client, make_auth_header):
    """_readable_check_or_404() deliberately widens ADMIN access only —
    a vendor with no assigned job on this check must still get 404, same
    as before."""
    alice = make_auth_header(role="customer", owner_org=None, email="alice4@example.com")
    vendor = make_auth_header(role="vendor", owner_org=None, email="vendor4@example.com")
    created = client.post("/app/checks", json=_new_check_body(), headers=alice).json()

    response = client.get(f"/app/checks/{created['id']}", headers=vendor)
    assert response.status_code == 404


# --------------------------------------------------------------------- #
# resolve-building — StartCheckWizard's click-to-locate step
# --------------------------------------------------------------------- #


def test_resolve_building_requires_auth(client):
    response = client.get("/app/checks/resolve-building", params={"lat": 17.385, "lng": 78.4867})
    assert response.status_code == 401


def test_resolve_building_route_is_not_swallowed_by_check_id_route(client, make_auth_header):
    """Registration-order regression guard: /checks/{check_id} is a plain
    string path param and was registered first historically — if
    resolve-building's route were registered after it, this request
    would 404 as "check not found" (malformed UUID) instead of resolving
    a building."""
    headers = make_auth_header(role="customer", owner_org=None)
    response = client.get(
        "/app/checks/resolve-building", params={"lat": 17.385, "lng": 78.4867}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_resolve_building_prefers_the_mask_polygon_when_available(client, make_auth_header, monkeypatch):
    mask_polygon = {
        "type": "Polygon",
        "coordinates": [
            [
                [78.48660, 17.38490],
                [78.48664, 17.38490],
                [78.48664, 17.38492],
                [78.48662, 17.38494],
                [78.48660, 17.38492],
                [78.48660, 17.38490],
            ]
        ],
    }
    monkeypatch.setattr(
        "solarfit.routers.app_checks.solar_api.extract_roof_polygon_from_mask",
        lambda lat, lng, **kw: MaskVectorization(polygon=mask_polygon, competing_regions=1),
    )
    monkeypatch.setattr(
        "solarfit.routers.app_checks.solar_api.resolve_for_location",
        lambda lat, lng, **kw: SolarApiResult(status="ok", boundary=BOUNDARY, roof_area_m2=42.0),
    )
    headers = make_auth_header(role="customer", owner_org=None)

    response = client.get(
        "/app/checks/resolve-building", params={"lat": 17.385, "lng": 78.4867}, headers=headers
    )

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["source"] == "solar_api_mask"
    assert body["competingBuildingsNearby"] == 1
    assert len(body["boundary"]) > 4  # the real mask shape, not the 4-corner rectangle


def test_resolve_building_centroid_matches_the_boundary_actually_returned(
    client, make_auth_header, monkeypatch
):
    """Regression: when the mask polygon is close enough to Building
    Insights' own answer to be trusted (see the disagreement-guard test
    below for the opposite case), the response's centroid must describe
    the boundary actually being returned — never Building Insights'
    centroid left over from the rectangle that got replaced, which is
    what made a correctly-drawn crop rectangle appear to jump within the
    next wizard step."""
    # A mask polygon a few metres from Building Insights' own centroid —
    # a real outline naturally differs from a bounding-box's arbitrary
    # centre for the SAME building, well inside the trust tolerance.
    mask_polygon = {
        "type": "Polygon",
        "coordinates": [
            [
                [78.48661, 17.38491],
                [78.48664, 17.38491],
                [78.48664, 17.38493],
                [78.48661, 17.38493],
                [78.48661, 17.38491],
            ]
        ],
    }
    building_insights_centroid = {"type": "Point", "coordinates": [78.4867, 17.3850]}  # inside BOUNDARY
    monkeypatch.setattr(
        "solarfit.routers.app_checks.solar_api.extract_roof_polygon_from_mask",
        lambda lat, lng, **kw: MaskVectorization(polygon=mask_polygon, competing_regions=0),
    )
    monkeypatch.setattr(
        "solarfit.routers.app_checks.solar_api.resolve_for_location",
        lambda lat, lng, **kw: SolarApiResult(
            status="ok", boundary=BOUNDARY, centroid=building_insights_centroid, roof_area_m2=42.0
        ),
    )
    headers = make_auth_header(role="customer", owner_org=None)

    response = client.get(
        "/app/checks/resolve-building", params={"lat": 17.385, "lng": 78.4867}, headers=headers
    )

    body = response.json()
    assert body["status"] == "ok"
    assert body["source"] == "solar_api_mask"
    centroid = body["centroid"]
    # The returned centroid must sit near the MASK polygon (~78.486625,
    # ~17.38492), not exactly at Building Insights' own centroid
    # (78.4867, 17.3850), confirming it was recomputed from the boundary
    # actually returned rather than reused verbatim.
    assert centroid["lng"] == pytest.approx(78.486625, abs=0.0001)
    assert centroid["lat"] == pytest.approx(17.38492, abs=0.0001)


def test_resolve_building_rejects_a_mask_region_that_disagrees_with_building_insights(
    client, make_auth_header, monkeypatch
):
    """Regression: in a dense block, _select_building_region() picks
    whichever mask region is nearest the click point — independent of,
    and not cross-checked against, Building Insights' own building
    match. When the two clearly disagree (here, ~2.8km apart — nowhere
    near the same building), the mask's pick must be rejected and the
    response must fall back to Building Insights' own (coarser, but
    correctly-located) rectangle — never hand a customer a real-looking
    outline that belongs to an entirely different building."""
    mask_polygon = {
        "type": "Polygon",
        "coordinates": [
            [
                [78.5100, 17.4000],
                [78.5104, 17.4000],
                [78.5104, 17.4004],
                [78.5100, 17.4004],
                [78.5100, 17.4000],
            ]
        ],
    }
    building_insights_centroid = {"type": "Point", "coordinates": [78.4867, 17.3850]}
    monkeypatch.setattr(
        "solarfit.routers.app_checks.solar_api.extract_roof_polygon_from_mask",
        lambda lat, lng, **kw: MaskVectorization(polygon=mask_polygon, competing_regions=2),
    )
    monkeypatch.setattr(
        "solarfit.routers.app_checks.solar_api.resolve_for_location",
        lambda lat, lng, **kw: SolarApiResult(
            status="ok", boundary=BOUNDARY, centroid=building_insights_centroid, roof_area_m2=42.0
        ),
    )
    headers = make_auth_header(role="customer", owner_org=None)

    response = client.get(
        "/app/checks/resolve-building", params={"lat": 17.385, "lng": 78.4867}, headers=headers
    )

    body = response.json()
    assert body["status"] == "ok"
    # Rejected the disagreeing mask polygon — kept Building Insights' own
    # rectangle and centroid instead.
    assert body["source"] == "solar_api"
    assert len(body["boundary"]) == 5  # BOUNDARY's closed 4-corner ring
    assert body["centroid"]["lng"] == pytest.approx(78.4867, abs=0.0001)
    assert body["centroid"]["lat"] == pytest.approx(17.3850, abs=0.0001)
    # The "other buildings nearby" signal is still surfaced even though
    # the mask's own pick was rejected — a customer near several
    # buildings is entitled to know that either way.
    assert body["competingBuildingsNearby"] == 2


def test_resolve_building_surfaces_the_imagery_date_for_the_precision_caveat(
    client, make_auth_header, monkeypatch
):
    """The frontend's "Adjust boundary" step warns the customer when
    detection ran on old/lower-tier imagery — this is the one field that
    warning is computed from, so it must actually reach the response."""
    monkeypatch.setattr(
        "solarfit.routers.app_checks.solar_api.extract_roof_polygon_from_mask",
        lambda lat, lng, **kw: MaskVectorization(polygon=None, competing_regions=0),
    )
    monkeypatch.setattr(
        "solarfit.routers.app_checks.solar_api.resolve_for_location",
        lambda lat, lng, **kw: SolarApiResult(
            status="ok",
            boundary=BOUNDARY,
            imagery_date=datetime(2023, 3, 15),
            roof_area_m2=42.0,
        ),
    )
    headers = make_auth_header(role="customer", owner_org=None)

    response = client.get(
        "/app/checks/resolve-building", params={"lat": 17.385, "lng": 78.4867}, headers=headers
    )

    body = response.json()
    assert body["imageryDate"].startswith("2023-03-15")


def test_resolve_building_falls_back_to_the_rectangle_without_a_mask(client, make_auth_header, monkeypatch):
    monkeypatch.setattr(
        "solarfit.routers.app_checks.solar_api.extract_roof_polygon_from_mask",
        lambda lat, lng, **kw: MaskVectorization(polygon=None, competing_regions=0),
    )
    monkeypatch.setattr(
        "solarfit.routers.app_checks.solar_api.resolve_for_location",
        lambda lat, lng, **kw: SolarApiResult(status="ok", boundary=BOUNDARY, roof_area_m2=42.0),
    )
    headers = make_auth_header(role="customer", owner_org=None)

    response = client.get(
        "/app/checks/resolve-building", params={"lat": 17.385, "lng": 78.4867}, headers=headers
    )

    body = response.json()
    assert body["status"] == "ok"
    assert body["source"] == "solar_api"
    # BOUNDARY's GeoJSON ring is closed (repeats its first point) — this
    # endpoint passes the ring through as-is, same convention
    # get_check_obstacles already uses for its own polygons.
    assert len(body["boundary"]) == 5


def test_resolve_building_reports_the_real_roof_pitch_at_the_pin(client, make_auth_header, monkeypatch):
    raw = {
        "solarPotential": {
            "roofSegmentStats": [
                {
                    "pitchDegrees": 18.6,
                    "azimuthDegrees": 135.0,
                    "planeHeightAtCenterMeters": 142.3,
                    "boundingBox": {
                        "sw": {"latitude": 17.384, "longitude": 78.486},
                        "ne": {"latitude": 17.386, "longitude": 78.488},
                    },
                    "stats": {"areaMeters2": 30.0, "groundAreaMeters2": 28.0},
                }
            ]
        }
    }
    monkeypatch.setattr(
        "solarfit.routers.app_checks.solar_api.extract_roof_polygon_from_mask",
        lambda lat, lng, **kw: MaskVectorization(polygon=None, competing_regions=0),
    )
    monkeypatch.setattr(
        "solarfit.routers.app_checks.solar_api.resolve_for_location",
        lambda lat, lng, **kw: SolarApiResult(
            status="ok", boundary=BOUNDARY, roof_area_m2=42.0, imagery_quality="HIGH", raw=raw
        ),
    )
    headers = make_auth_header(role="customer", owner_org=None)

    response = client.get(
        "/app/checks/resolve-building", params={"lat": 17.385, "lng": 78.4867}, headers=headers
    )

    body = response.json()
    assert response.status_code == 200
    assert body["roofPitch"]["pitchDeg"] == 18.6
    assert body["roofPitch"]["orientation"] == "SE"
    assert body["roofPitch"]["planeHeightM"] == 142.3
    assert body["roofPitch"]["confidence"] == "high"


def test_resolve_building_omits_roof_pitch_without_segment_data(client, make_auth_header, monkeypatch):
    monkeypatch.setattr(
        "solarfit.routers.app_checks.solar_api.extract_roof_polygon_from_mask",
        lambda lat, lng, **kw: MaskVectorization(polygon=None, competing_regions=0),
    )
    monkeypatch.setattr(
        "solarfit.routers.app_checks.solar_api.resolve_for_location",
        lambda lat, lng, **kw: SolarApiResult(status="ok", boundary=BOUNDARY, roof_area_m2=42.0, raw={}),
    )
    headers = make_auth_header(role="customer", owner_org=None)

    response = client.get(
        "/app/checks/resolve-building", params={"lat": 17.385, "lng": 78.4867}, headers=headers
    )

    assert response.json()["roofPitch"] is None


def test_resolve_building_reports_no_coverage_for_empty_land(client, make_auth_header, monkeypatch):
    monkeypatch.setattr(
        "solarfit.routers.app_checks.solar_api.resolve_for_location",
        lambda lat, lng, **kw: SolarApiResult(status="no_coverage", detail="no building covered here"),
    )
    headers = make_auth_header(role="customer", owner_org=None)

    response = client.get(
        "/app/checks/resolve-building", params={"lat": 0.0, "lng": 0.0}, headers=headers
    )

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "no_coverage"
    assert body["boundary"] is None


def test_resolve_building_surfaces_a_solar_api_error_as_503(client, make_auth_header, monkeypatch):
    from solarfit.providers.solar_api import SolarApiError

    def _boom(lat, lng, **kw):
        raise SolarApiError("missing API key")

    monkeypatch.setattr("solarfit.routers.app_checks.solar_api.resolve_for_location", _boom)
    headers = make_auth_header(role="customer", owner_org=None)

    response = client.get(
        "/app/checks/resolve-building", params={"lat": 17.385, "lng": 78.4867}, headers=headers
    )

    assert response.status_code == 503


# --------------------------------------------------------------------- #
# confirmed_boundary / map_metadata at check creation — StartCheckWizard
# --------------------------------------------------------------------- #

# A hand-cropped L-shape, deliberately smaller in area than BOUNDARY's
# ~0.0014deg-square rectangle and missing its NE corner — the concrete
# shape the precedence test below proves survives into the packed layout.
CONFIRMED_L_SHAPE = [
    {"lat": 17.3845, "lng": 78.4860},
    {"lat": 17.3845, "lng": 78.4874},
    {"lat": 17.3850, "lng": 78.4874},
    {"lat": 17.3850, "lng": 78.4867},
    {"lat": 17.3855, "lng": 78.4867},
    {"lat": 17.3855, "lng": 78.4860},
]


def test_create_check_with_confirmed_boundary_is_stored_as_manual_polygon(client, make_auth_header):
    headers = make_auth_header(role="customer", owner_org=None)
    body = _new_check_body(confirmedBoundary=CONFIRMED_L_SHAPE)

    response = client.post("/app/checks", json=body, headers=headers)

    out = response.json()
    assert response.status_code == 201
    assert out["geometrySource"] == "manual_polygon"
    assert out["boundaryIsApproximate"] is False
    assert len(out["boundary"]) == len(CONFIRMED_L_SHAPE)


def test_create_check_with_usn_persists_it_confirmed(client, make_auth_header):
    """USN-01 at intake — reuses providers/usn_ocr.py::capture_manual(),
    the same validator the post-analysis manual-entry path uses."""
    headers = make_auth_header(role="customer", owner_org=None)
    body = _new_check_body(usn="ABC123XYZ")

    response = client.post("/app/checks", json=body, headers=headers)

    out = response.json()
    assert response.status_code == 201
    assert out["usn"] == "ABC123XYZ"
    assert out["usnStatus"] == "confirmed"


def test_create_check_with_malformed_usn_is_rejected(client, make_auth_header):
    headers = make_auth_header(role="customer", owner_org=None)
    body = _new_check_body(usn="a")  # far short of the 6-20 char format

    response = client.post("/app/checks", json=body, headers=headers)

    assert response.status_code == 422


def test_create_check_without_usn_is_unaffected(client, make_auth_header):
    headers = make_auth_header(role="customer", owner_org=None)
    response = client.post("/app/checks", json=_new_check_body(), headers=headers)
    out = response.json()
    assert response.status_code == 201
    assert out["usn"] is None
    assert out["usnStatus"] == "not_started"


def test_create_check_with_self_intersecting_confirmed_boundary_is_rejected(client, make_auth_header):
    headers = make_auth_header(role="customer", owner_org=None)
    bowtie = [
        {"lat": 17.3845, "lng": 78.4860},
        {"lat": 17.3855, "lng": 78.4874},
        {"lat": 17.3845, "lng": 78.4874},
        {"lat": 17.3855, "lng": 78.4860},
    ]
    body = _new_check_body(confirmedBoundary=bowtie)

    response = client.post("/app/checks", json=body, headers=headers)

    assert response.status_code == 422


def test_create_check_without_confirmed_boundary_is_unaffected(client, make_auth_header):
    """The existing NewCheckForm caller never sends confirmedBoundary —
    must keep landing on the Solar API rectangle exactly as before."""
    headers = make_auth_header(role="customer", owner_org=None)
    response = client.post("/app/checks", json=_new_check_body(), headers=headers)
    out = response.json()
    assert response.status_code == 201
    assert out["geometrySource"] == "solar_api"


# --------------------------------------------------------------------- #
# GEO-09 — _apply_manual_boundary() must recompute geometry_confidence
# fresh for the new manual_polygon boundary, not inherit whatever the
# prior version's source/confidence was.
# --------------------------------------------------------------------- #

_MANUAL_EDIT_POINTS = [
    {"lat": 17.38490, "lng": 78.48660},
    {"lat": 17.38490, "lng": 78.48664},
    {"lat": 17.38494, "lng": 78.48664},
    {"lat": 17.38494, "lng": 78.48660},
]


def _manual_edit_expected_confidence(imagery_date_iso: str | None) -> float:
    """Independently recomputes what _apply_manual_boundary() SHOULD
    store for _MANUAL_EDIT_POINTS, the same way the endpoint itself
    does — used to cross-check the API's own returned value, not just
    assert it "changed"."""
    boundary = {
        "type": "Polygon",
        "coordinates": [
            [[p["lng"], p["lat"]] for p in _MANUAL_EDIT_POINTS]
            + [[_MANUAL_EDIT_POINTS[0]["lng"], _MANUAL_EDIT_POINTS[0]["lat"]]]
        ],
    }
    imagery_date = datetime.fromisoformat(imagery_date_iso) if imagery_date_iso else None
    return geometry_confidence(source="manual_polygon", imagery_date=imagery_date, boundary=boundary)


def test_case4_manual_edit_from_a_solar_api_mask_boundary_recomputes_confidence(
    client, make_auth_header, monkeypatch
):
    """Case 4. A check created from a real solar_api_mask boundary (base
    confidence 0.68), then manually edited — the resulting manual_polygon
    version must carry a FRESHLY computed confidence (base 0.75 + its own
    penalties), never the solar_api_mask figure carried forward."""
    mask_polygon = {
        "type": "Polygon",
        "coordinates": [
            [
                [78.48660, 17.38490],
                [78.48664, 17.38490],
                [78.48664, 17.38492],
                [78.48662, 17.38494],
                [78.48660, 17.38492],
                [78.48660, 17.38490],
            ]
        ],
    }
    monkeypatch.setattr(
        "solarfit.routers.sites.solar_api.extract_roof_polygon_from_mask",
        lambda lat, lng, **kw: MaskVectorization(polygon=mask_polygon, competing_regions=0),
    )
    headers = make_auth_header(role="customer", owner_org=None)

    created = client.post("/app/checks", json=_new_check_body(), headers=headers).json()
    check_id = created["id"]
    assert created["geometrySource"] == "solar_api_mask"
    mask_confidence = created["geometryConfidence"]

    response = client.put(
        f"/app/checks/{check_id}/boundary", json={"points": _MANUAL_EDIT_POINTS}, headers=headers
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["geometrySource"] == "manual_polygon"
    # Not just "changed" — matches an independent recomputation exactly,
    # proving it was actually recalculated rather than nudged/copied.
    expected = _manual_edit_expected_confidence(updated["imageryDate"])
    assert updated["geometryConfidence"] == pytest.approx(expected, abs=0.001)
    assert updated["geometryConfidence"] != pytest.approx(mask_confidence, abs=0.001)


def test_case5_re_editing_a_manual_boundary_recomputes_confidence_again(client, make_auth_header):
    """Case 5. A SECOND manual edit (editing an already-manual_polygon
    boundary) must also recompute fresh — not freeze at whatever the
    first manual edit happened to compute, and not just carry that
    forward either."""
    headers = make_auth_header(role="customer", owner_org=None)
    created = client.post("/app/checks", json=_new_check_body(), headers=headers).json()
    check_id = created["id"]

    first_edit = client.put(
        f"/app/checks/{check_id}/boundary", json={"points": _MANUAL_EDIT_POINTS}, headers=headers
    ).json()
    assert first_edit["geometrySource"] == "manual_polygon"

    second_points = [
        {"lat": 17.38590, "lng": 78.48760},
        {"lat": 17.38590, "lng": 78.48764},
        {"lat": 17.38596, "lng": 78.48764},
        {"lat": 17.38596, "lng": 78.48760},
    ]
    second_response = client.put(
        f"/app/checks/{check_id}/boundary", json={"points": second_points}, headers=headers
    )

    assert second_response.status_code == 200
    second_edit = second_response.json()
    assert second_edit["geometrySource"] == "manual_polygon"

    second_boundary = {
        "type": "Polygon",
        "coordinates": [
            [[p["lng"], p["lat"]] for p in second_points]
            + [[second_points[0]["lng"], second_points[0]["lat"]]]
        ],
    }
    imagery_date = (
        datetime.fromisoformat(second_edit["imageryDate"]) if second_edit["imageryDate"] else None
    )
    expected = geometry_confidence(
        source="manual_polygon", imagery_date=imagery_date, boundary=second_boundary
    )
    assert second_edit["geometryConfidence"] == pytest.approx(expected, abs=0.001)


def test_case5_version_history_still_records_each_edit_independently(client, make_auth_header, db_session):
    """Case 5, continued: SITE-05's append-only version history must
    still work after this fix — each manual edit is its own new version,
    and an earlier version's own stored confidence is never rewritten by
    a later edit (only the site's CURRENT row moves)."""
    from solarfit.repositories import sites as sites_repo

    headers = make_auth_header(role="customer", owner_org=None)
    created = client.post("/app/checks", json=_new_check_body(), headers=headers).json()
    check_id = created["id"]

    client.put(f"/app/checks/{check_id}/boundary", json={"points": _MANUAL_EDIT_POINTS}, headers=headers)

    history = sites_repo.versions(db_session, check_id)
    assert len(history) == 2  # the original create + this one manual edit
    assert history[0].geometry_source == "solar_api"
    assert history[1].geometry_source == "manual_polygon"
    # The original version's own confidence is untouched by the later edit.
    assert history[0].geometry_confidence != history[1].geometry_confidence
    assert history[1].geometry_confidence == pytest.approx(
        _manual_edit_expected_confidence(
            history[1].imagery_date.isoformat() if history[1].imagery_date else None
        ),
        abs=0.001,
    )


def test_create_check_persists_map_metadata(client, make_auth_header):
    headers = make_auth_header(role="customer", owner_org=None)
    body = _new_check_body(
        mapMetadata={
            "zoom": 20,
            "mapTypeId": "satellite",
            "clickedLat": 17.3850,
            "clickedLng": 78.4867,
        }
    )

    response = client.post("/app/checks", json=body, headers=headers)

    out = response.json()
    assert response.status_code == 201
    assert out["mapViewMetadata"] == {
        "zoom": 20,
        "mapTypeId": "satellite",
        "clickedLat": 17.3850,
        "clickedLng": 78.4867,
        "selectionMethod": None,
    }


def test_create_check_persists_map_metadata_with_selection_method(client, make_auth_header):
    """StartCheckWizard's Crop vs Freehand tool — optional, additive
    provenance on the same map_metadata blob."""
    headers = make_auth_header(role="customer", owner_org=None)
    body = _new_check_body(
        mapMetadata={
            "zoom": 20,
            "mapTypeId": "satellite",
            "clickedLat": 17.3850,
            "clickedLng": 78.4867,
            "selectionMethod": "freehand",
        }
    )

    response = client.post("/app/checks", json=body, headers=headers)

    assert response.status_code == 201
    assert response.json()["mapViewMetadata"]["selectionMethod"] == "freehand"


# --------------------------------------------------------------------- #
# complete
# --------------------------------------------------------------------- #
#
# Phase 4: POST .../complete now only dispatches a background job and
# returns a job id (202) — the real work (orchestrate_assessment +
# persistence) moved into workers/tasks_assessments.py::
# run_check_assessment, run by run_check_assessment_task.delay(). These
# tests fake .delay() to run that function synchronously, in-process,
# instead of going through a real Celery broker/worker — the same
# "tests mock .delay() itself" discipline test_assessments_router.py's
# _ImmediateAsyncResult and test_analysis_cache.py already establish.


@pytest.fixture
def sync_assessment_task(monkeypatch):
    """Fakes run_check_assessment_task.delay() (dispatch) and celery_app.
    AsyncResult() (poll) so a test can drive the whole start -> poll
    round trip without a real broker. Returns the job_results dict for
    assertions that want to inspect what a job actually produced."""
    from solarfit.workers import tasks_assessments as tasks_assessments_module

    job_results: dict[str, dict] = {}
    counter = {"n": 0}

    class _FakeTaskHandle:
        def __init__(self, job_id):
            self.id = job_id

    class _FakeDelayedTask:
        def delay(self, site_id, owner_org):
            counter["n"] += 1
            job_id = f"fake-job-{counter['n']}"
            job_results[job_id] = tasks_assessments_module.run_check_assessment(
                site_id, owner_org, on_stage=lambda stage: None
            )
            return _FakeTaskHandle(job_id)

    class _FakeAsyncResult:
        def __init__(self, job_id):
            result = job_results.get(job_id)
            if result is None:
                self.state = "PENDING"
                self.info = None
                self.result = None
            else:
                self.state = "SUCCESS"
                self.info = None
                self.result = result

    class _FakeCeleryApp:
        def AsyncResult(self, job_id):
            return _FakeAsyncResult(job_id)

    monkeypatch.setattr("solarfit.routers.app_checks.run_check_assessment_task", _FakeDelayedTask())
    monkeypatch.setattr("solarfit.routers.app_checks.celery_app", _FakeCeleryApp())
    return job_results


def _complete_check_and_poll(client, headers, check_id):
    """Starts a check's assessment and polls it to completion — with
    sync_assessment_task in play the job is already finished by the time
    .delay() returns, so a single poll is enough. Returns the final
    AssessmentJobStatusOut body."""
    start = client.post(f"/app/checks/{check_id}/complete", headers=headers)
    assert start.status_code == 202
    job_id = start.json()["jobId"]
    status_response = client.get(f"/app/checks/{check_id}/complete/{job_id}", headers=headers)
    assert status_response.status_code == 200
    return status_response.json()


def test_complete_check_runs_the_real_engine_and_persists(
    client, make_auth_header, monkeypatch, db_session, sync_assessment_task
):
    """orchestrate_assessment() and run_check_assessment()'s own save both
    open a real solarfit.db.session_scope() internally rather than using
    the injected/overridden get_session dependency — same pattern
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
    monkeypatch.setattr("solarfit.db.session_scope", _fake_session_scope)

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

    job_status = _complete_check_and_poll(client, headers, created["id"])
    assert job_status["status"] == "ok"

    refetched = client.get(f"/app/checks/{created['id']}", headers=headers).json()
    assert refetched["latestAssessment"] is not None
    assert refetched["latestAssessment"]["verdict"] in {
        "SUITABLE",
        "SUITABLE_SUBJECT_TO_SURVEY",
        "CONDITIONAL",
        "INSUFFICIENT_DATA",
        "NOT_SUITABLE",
    }
    # STANDARD_LIMITATIONS ships on every real FitnessResult — must reach
    # the frontend-shaped response, not just live on the DB row.
    assert refetched["latestAssessment"]["limitations"]


def test_confirmed_boundary_outranks_the_cached_solar_api_rectangle_at_assessment_time(
    client, make_auth_header, monkeypatch, db_session, sync_assessment_task
):
    """The concrete, check-flow-specific proof for GEO-01 precedence
    (routers/assessments.py's `outranks(site.geometry_source,
    "solar_api")` check, already unit-tested generically in
    test_assessments_router.py::
    test_a_mask_derived_boundary_is_reported_not_the_cached_bounding_box):
    a check created via StartCheckWizard's confirmed_boundary must have
    its OWN (manual_polygon) boundary measured at assessment time, not
    the Solar-API-cached BOUNDARY rectangle, even though the cache
    returns a different, larger shape."""
    from contextlib import contextmanager

    from solarfit.domain.assessment import VisionRefinement

    @contextmanager
    def _fake_session_scope():
        yield db_session

    monkeypatch.setattr("solarfit.routers.assessments.session_scope", _fake_session_scope)
    monkeypatch.setattr("solarfit.db.session_scope", _fake_session_scope)

    headers = make_auth_header(role="customer", owner_org=None)
    created = client.post(
        "/app/checks", json=_new_check_body(confirmedBoundary=CONFIRMED_L_SHAPE), headers=headers
    ).json()
    assert created["geometrySource"] == "manual_polygon"

    monkeypatch.setattr(
        "solarfit.repositories.analysis_cache.get_or_create_analysis",
        lambda lat, lng, site_type, params: type(
            "A",
            (),
            {
                # Deliberately BOUNDARY, not the confirmed L-shape — proves
                # the assessment measures the site's own boundary, not this.
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

    job_status = _complete_check_and_poll(client, headers, created["id"])
    assert job_status["status"] == "ok"

    refetched = client.get(f"/app/checks/{created['id']}", headers=headers).json()
    # The assessed/reported boundary is the confirmed L-shape, not BOUNDARY.
    assert refetched["boundary"] != BOUNDARY["coordinates"][0]
    reported_points = {(round(p["lat"], 6), round(p["lng"], 6)) for p in refetched["boundary"]}
    confirmed_points = {(round(p["lat"], 6), round(p["lng"], 6)) for p in CONFIRMED_L_SHAPE}
    assert confirmed_points.issubset(reported_points)


def test_complete_unknown_check_is_404(client, make_auth_header):
    headers = make_auth_header(role="customer", owner_org=None)
    response = client.post(
        "/app/checks/00000000-0000-0000-0000-000000000000/complete", headers=headers
    )
    assert response.status_code == 404


def test_polling_status_for_an_unowned_check_is_404(client, make_auth_header, sync_assessment_task):
    """Ownership is checked against check_id, not the (opaque) job_id —
    a caller with no access to the check has no way to peek at a real
    job's status by guessing its id."""
    alice = make_auth_header(role="customer", owner_org=None, email="alice-poll@example.com")
    bob = make_auth_header(role="customer", owner_org=None, email="bob-poll@example.com")
    created = client.post("/app/checks", json=_new_check_body(), headers=alice).json()

    start = client.post(f"/app/checks/{created['id']}/complete", headers=alice)
    job_id = start.json()["jobId"]

    response = client.get(f"/app/checks/{created['id']}/complete/{job_id}", headers=bob)
    assert response.status_code == 404


def test_polling_an_unknown_job_id_reports_pending_not_an_error(client, make_auth_header, sync_assessment_task):
    """A job id the fake backend has never seen (not yet picked up by a
    worker, or simply unknown) must read as "still pending", the same
    as Celery's own real behaviour for an unrecognised task id — never
    a 404/500 that would make the processing screen show an error for
    what is actually just an ordinary race between dispatch and the
    first poll."""
    headers = make_auth_header(role="customer", owner_org=None)
    created = client.post("/app/checks", json=_new_check_body(), headers=headers).json()

    response = client.get(f"/app/checks/{created['id']}/complete/not-a-real-job-id", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "pending"


def test_no_solar_api_coverage_degrades_to_a_geometry_rejected_status(
    client, make_auth_header, monkeypatch, sync_assessment_task
):
    """GEO-04: no automatic roof data at this location is ordinary, not a
    server error. complete_check can no longer turn this into an
    immediate 422 the way the old synchronous version did — the failure
    now happens inside a background job — so it has to come back as a
    polled status instead, for the processing screen to react to."""
    from solarfit.providers.validation import GeometryRejected

    headers = make_auth_header(role="customer", owner_org=None)
    created = client.post("/app/checks", json=_new_check_body(), headers=headers).json()

    def _boom(check_id, owner_org=None, **kw):
        raise GeometryRejected("no coverage here")

    monkeypatch.setattr("solarfit.routers.assessments.orchestrate_assessment", _boom)

    job_status = _complete_check_and_poll(client, headers, created["id"])
    assert job_status["status"] == "geometry_rejected"
    assert job_status["error"]


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
    """Requires the `sync_assessment_task` fixture already be active in
    the calling test (it's what makes run_check_assessment actually run
    in-process against `db_session` instead of a real worker)."""
    from contextlib import contextmanager

    @contextmanager
    def _fake_session_scope():
        yield db_session

    monkeypatch.setattr("solarfit.db.session_scope", _fake_session_scope)

    created = client.post(
        "/app/checks", json=_new_check_body(siteType=site_type), headers=headers
    ).json()

    monkeypatch.setattr(
        "solarfit.routers.assessments.orchestrate_assessment",
        lambda check_id, owner_org=None, **kw: _canned_assessment_response(check_id, site_type, verdict),
    )

    job_status = _complete_check_and_poll(client, headers, created["id"])
    assert job_status["status"] == "ok"
    return created["id"]


def _assessment_for_site(db_session, site_id):
    from sqlalchemy import select

    from solarfit.repositories.assessments import AssessmentRow

    return db_session.scalars(
        select(AssessmentRow).where(AssessmentRow.site_id == site_id).order_by(AssessmentRow.created_at.desc())
    ).first()


def _vendor_job_for_site(db_session, site_id):
    import uuid

    from sqlalchemy import select

    from solarfit.repositories.vendors import VendorJobRow

    return db_session.scalars(
        select(VendorJobRow).where(VendorJobRow.site_id == uuid.UUID(site_id))
    ).first()


def test_survey_verdict_awaits_customer_enquiry_before_admin_review(
    client, make_auth_header, monkeypatch, db_session, sync_assessment_task
):
    """Customer -> Feasibility Check -> [customer raises an enquiry] ->
    Admin Review -> Admin Approval -> Vendor Access: completing a check
    only computes the assessment — it never creates a vendor job, and
    (per the enquiry/check separation rule) doesn't even enter the
    admin's review queue until the customer explicitly raises an
    enquiry (see raise_check_enquiry() in app_checks.py)."""
    headers = make_auth_header(role="customer", owner_org=None)
    check_id = _complete_with_canned_verdict(
        client, headers, monkeypatch, db_session, "ROOFTOP_RESIDENTIAL", "SUITABLE_SUBJECT_TO_SURVEY"
    )

    assessment = _assessment_for_site(db_session, check_id)
    assert assessment is not None
    assert assessment.review_status == "not_submitted"
    assert _vendor_job_for_site(db_session, check_id) is None


def test_suitable_verdict_also_awaits_customer_enquiry(
    client, make_auth_header, monkeypatch, db_session, sync_assessment_task
):
    headers = make_auth_header(role="customer", owner_org=None)
    check_id = _complete_with_canned_verdict(
        client, headers, monkeypatch, db_session, "ROOFTOP_RESIDENTIAL", "SUITABLE"
    )

    assessment = _assessment_for_site(db_session, check_id)
    assert assessment.review_status == "not_submitted"


def test_non_eligible_verdict_is_not_applicable_for_review(
    client, make_auth_header, monkeypatch, db_session, sync_assessment_task
):
    headers = make_auth_header(role="customer", owner_org=None)
    check_id = _complete_with_canned_verdict(
        client, headers, monkeypatch, db_session, "ROOFTOP_RESIDENTIAL", "NOT_SUITABLE"
    )

    assessment = _assessment_for_site(db_session, check_id)
    assert assessment.review_status == "not_applicable"
    assert _vendor_job_for_site(db_session, check_id) is None


# --------------------------------------------------------------------- #
# enquiry
# --------------------------------------------------------------------- #


def _seed_verified_vendor(db_session, *, district="Test District", state="Testland", available=True):
    from solarfit.repositories.vendors import VendorRow

    row = VendorRow(
        name="Acme Solar",
        verification_status="verified",
        availability=available,
        accuracy_score=0.9,
        service_area={"region": state, "districts": [district]},
        payout_method_type="UPI",
        payout_masked_account="xxxx1234",
        certifications=["MNRE"],
    )
    db_session.add(row)
    db_session.flush()
    return row


def test_raising_an_enquiry_without_a_vendor_moves_to_pending(
    client, make_auth_header, monkeypatch, db_session, sync_assessment_task
):
    headers = make_auth_header(role="customer", owner_org=None)
    check_id = _complete_with_canned_verdict(
        client, headers, monkeypatch, db_session, "ROOFTOP_RESIDENTIAL", "SUITABLE"
    )

    response = client.post(f"/app/checks/{check_id}/enquiry", json={}, headers=headers)
    assert response.status_code == 200

    assessment = _assessment_for_site(db_session, check_id)
    assert assessment.review_status == "pending"
    assert assessment.customer_selected_vendor_id is None
    assert assessment.enquiry_submitted_at is not None


def test_raising_an_enquiry_with_a_vendor_records_the_customer_selection(
    client, make_auth_header, monkeypatch, db_session, sync_assessment_task
):
    headers = make_auth_header(role="customer", owner_org=None)
    check_id = _complete_with_canned_verdict(
        client, headers, monkeypatch, db_session, "ROOFTOP_RESIDENTIAL", "SUITABLE"
    )
    vendor = _seed_verified_vendor(db_session)

    response = client.post(
        f"/app/checks/{check_id}/enquiry", json={"vendorId": str(vendor.id)}, headers=headers
    )
    assert response.status_code == 200

    assessment = _assessment_for_site(db_session, check_id)
    assert assessment.review_status == "pending"
    assert str(assessment.customer_selected_vendor_id) == str(vendor.id)


def test_raising_an_enquiry_on_an_ineligible_verdict_is_rejected(
    client, make_auth_header, monkeypatch, db_session, sync_assessment_task
):
    headers = make_auth_header(role="customer", owner_org=None)
    check_id = _complete_with_canned_verdict(
        client, headers, monkeypatch, db_session, "ROOFTOP_RESIDENTIAL", "NOT_SUITABLE"
    )

    response = client.post(f"/app/checks/{check_id}/enquiry", json={}, headers=headers)
    assert response.status_code == 409


def test_raising_an_enquiry_twice_is_a_no_op_not_a_second_enquiry(
    client, make_auth_header, monkeypatch, db_session, sync_assessment_task
):
    headers = make_auth_header(role="customer", owner_org=None)
    check_id = _complete_with_canned_verdict(
        client, headers, monkeypatch, db_session, "ROOFTOP_RESIDENTIAL", "SUITABLE"
    )
    vendor = _seed_verified_vendor(db_session)

    first = client.post(
        f"/app/checks/{check_id}/enquiry", json={"vendorId": str(vendor.id)}, headers=headers
    )
    assert first.status_code == 200

    # A second submission, even with a DIFFERENT vendor, must not change
    # the state already recorded by the first — first call wins.
    other_vendor = _seed_verified_vendor(db_session, district="Elsewhere")
    second = client.post(
        f"/app/checks/{check_id}/enquiry", json={"vendorId": str(other_vendor.id)}, headers=headers
    )
    assert second.status_code == 200

    assessment = _assessment_for_site(db_session, check_id)
    assert assessment.review_status == "pending"
    assert str(assessment.customer_selected_vendor_id) == str(vendor.id)


def test_nearby_vendors_filters_to_verified_and_available_with_district_match(
    client, make_auth_header, monkeypatch, db_session, sync_assessment_task
):
    headers = make_auth_header(role="customer", owner_org=None)
    check_id = _complete_with_canned_verdict(
        client, headers, monkeypatch, db_session, "ROOFTOP_RESIDENTIAL", "SUITABLE"
    )
    from solarfit.repositories.sites import SiteRow

    site_row = db_session.get(SiteRow, check_id)
    site_row.district = "Hyderabad"
    site_row.state = "Telangana"
    db_session.flush()

    same_district = _seed_verified_vendor(db_session, district="Hyderabad", state="Telangana")
    same_state_only = _seed_verified_vendor(db_session, district="Warangal", state="Telangana")
    unavailable = _seed_verified_vendor(db_session, district="Hyderabad", available=False)
    from solarfit.repositories.vendors import VendorRow

    unverified = VendorRow(
        name="Unverified Co",
        verification_status="pending",
        availability=True,
        accuracy_score=0.5,
        service_area={"region": "Telangana", "districts": ["Hyderabad"]},
        payout_method_type="UPI",
        payout_masked_account="xxxx0000",
    )
    db_session.add(unverified)
    db_session.flush()

    response = client.get(f"/app/checks/{check_id}/vendors", headers=headers)
    assert response.status_code == 200
    body = response.json()

    ids = {v["id"] for v in body}
    assert str(same_district.id) in ids
    assert str(same_state_only.id) in ids
    assert str(unavailable.id) not in ids
    assert str(unverified.id) not in ids

    by_id = {v["id"]: v for v in body}
    assert by_id[str(same_district.id)]["matchCategory"] == "same_district"
    assert by_id[str(same_state_only.id)]["matchCategory"] == "same_state"
    # Never a fabricated contact field.
    assert "contactPhone" not in by_id[str(same_district.id)]
    assert "contactEmail" not in by_id[str(same_district.id)]


def test_nearby_vendors_never_includes_unverified_or_unavailable(
    client, make_auth_header, monkeypatch, db_session, sync_assessment_task
):
    """Whatever vendors already exist in this environment, the endpoint
    must only ever return verified + available ones — checked as an
    invariant over the real response rather than asserting a specific
    count, since a shared dev database may already carry real seeded
    vendor rows outside this test's control."""
    headers = make_auth_header(role="customer", owner_org=None)
    check_id = _complete_with_canned_verdict(
        client, headers, monkeypatch, db_session, "ROOFTOP_RESIDENTIAL", "SUITABLE"
    )
    unavailable = _seed_verified_vendor(db_session, district="Nowhereville", available=False)
    from solarfit.repositories.vendors import VendorRow

    unverified = VendorRow(
        name="Unverified Co",
        verification_status="pending",
        availability=True,
        accuracy_score=0.5,
        service_area={"region": "Nowhere", "districts": ["Nowhereville"]},
        payout_method_type="UPI",
        payout_masked_account="xxxx0000",
    )
    db_session.add(unverified)
    db_session.flush()

    response = client.get(f"/app/checks/{check_id}/vendors", headers=headers)
    assert response.status_code == 200
    body = response.json()

    ids = {v["id"] for v in body}
    assert str(unavailable.id) not in ids
    assert str(unverified.id) not in ids
    assert all(v["verificationStatus"] == "verified" and v["availability"] for v in body)


def test_survey_job_requirements_include_usn_for_billing_linked_site_type():
    from solarfit.repositories.vendors import default_survey_requirements

    assert default_survey_requirements("ROOFTOP_RESIDENTIAL") == [
        "Capture boundary polygon",
        "Upload panorama photo",
        "Confirm USN via bill OCR",
        "Note shading obstructions",
    ]


def test_survey_job_requirements_omit_usn_for_non_billing_linked_site_type():
    # ROOFTOP_GOVT is the one RoofSiteType not in BILLING_LINKED_SITE_TYPES
    # (only ROOFTOP_RESIDENTIAL/ROOFTOP_CI are — USN-05).
    from solarfit.repositories.vendors import default_survey_requirements

    assert default_survey_requirements("ROOFTOP_GOVT") == [
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
        json={"phone": "9876543210", "notifyOnComplete": False},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["phone"] == "9876543210"
    assert body["notifyOnComplete"] is False

    refetched = client.get("/app/customer/profile", headers=headers).json()
    assert refetched["phone"] == "9876543210"


def test_update_profile_rejects_empty_name(client, make_auth_header):
    headers = make_auth_header(role="customer", owner_org=None)
    response = client.patch("/app/customer/profile", json={"name": ""}, headers=headers)
    assert response.status_code == 422


def test_update_profile_ignores_email(client, make_auth_header):
    headers = make_auth_header(role="customer", owner_org=None, email="original@example.com")
    response = client.patch(
        "/app/customer/profile", json={"phone": "9000000000"}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["email"] == "original@example.com"


@pytest.mark.parametrize("phone", ["6123456789", "7123456789", "8123456789", "9123456789"])
def test_update_profile_accepts_valid_indian_mobile_numbers(client, make_auth_header, phone):
    headers = make_auth_header(role="customer", owner_org=None)
    response = client.patch("/app/customer/profile", json={"phone": phone}, headers=headers)
    assert response.status_code == 200
    assert response.json()["phone"] == phone


def test_update_profile_trims_surrounding_whitespace(client, make_auth_header):
    headers = make_auth_header(role="customer", owner_org=None)
    response = client.patch("/app/customer/profile", json={"phone": "  9876543210  "}, headers=headers)
    assert response.status_code == 200
    assert response.json()["phone"] == "9876543210"


def test_update_profile_blank_phone_clears_it(client, make_auth_header):
    headers = make_auth_header(role="customer", owner_org=None)
    response = client.patch("/app/customer/profile", json={"phone": "   "}, headers=headers)
    assert response.status_code == 200
    assert response.json()["phone"] is None


@pytest.mark.parametrize(
    "phone",
    [
        "5123456789",  # doesn't start with 6-9
        "123456789",  # 9 digits
        "91234567891",  # 11 digits
        "91-9123456789",  # country code + separator
        "912345678a",  # letters
        "98765-43210",  # special characters
        "abcdefghij",  # letters only
    ],
)
def test_update_profile_rejects_invalid_phone_numbers(client, make_auth_header, phone):
    headers = make_auth_header(role="customer", owner_org=None)
    response = client.patch("/app/customer/profile", json={"phone": phone}, headers=headers)
    assert response.status_code == 422
    assert "valid 10-digit mobile number" in response.text
