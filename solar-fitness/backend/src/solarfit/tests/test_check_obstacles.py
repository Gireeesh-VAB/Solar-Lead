"""§16 Testing — GET /app/checks/{id}/obstacles (OBS-04).

The distinction this endpoint exists to preserve: a roof with no
obstacles and a roof nothing has ever looked at are NOT the same answer.
Obstacle detection (OBS-01/02) runs through a vision-LLM call that needs
an OPENAI_API_KEY; without one the pipeline reports insufficient_data and
finds nothing. Drawing that as "no obstacles — clear roof" would be a lie
of omission, and it is the customer's usable area that would be
overstated as a result.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from solarfit.db import get_session
from solarfit.engine.area import compute_usable_area_m2
from solarfit.main import app
from solarfit.providers.solar_api import MaskVectorization, SolarApiResult
from solarfit.repositories import sites as sites_repo

# A square roughly 4 m across, in the shape OBS-04 stores.
POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [
            [78.48670, 17.38500],
            [78.48674, 17.38500],
            [78.48674, 17.38504],
            [78.48670, 17.38504],
            [78.48670, 17.38500],
        ]
    ],
}


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def auth(make_auth_header):
    return make_auth_header(role="customer", owner_org=None)


@pytest.fixture
def check_id(client, auth):
    """A real owned check — the endpoint is ownership-gated.

    The request body always supplies lat/lng, so create_site_core() takes
    the resolve_for_location branch, not resolve_for_address — both are
    faked here (previously only resolve_for_address was, so this test
    silently depended on a real Solar API call over the network to reach
    the boundary=None state it actually wants)."""
    fake_result = SolarApiResult(status="no_coverage", boundary=None)
    with (
        patch("solarfit.routers.sites.solar_api.resolve_for_address", return_value=fake_result),
        patch("solarfit.routers.sites.solar_api.resolve_for_location", return_value=fake_result),
        patch(
            "solarfit.routers.sites.solar_api.extract_roof_polygon_from_mask",
            return_value=MaskVectorization(polygon=None, competing_regions=0),
        ),
    ):
        response = client.post(
            "/app/checks",
            json={"address": "Somewhere, Hyderabad", "lat": 17.385, "lng": 78.4867},
            headers=auth,
        )
    return response.json()["id"]


def test_obstacles_requires_auth(client, check_id):
    assert client.get(f"/app/checks/{check_id}/obstacles").status_code == 401


def test_another_tenants_check_is_404(client, auth, check_id, make_auth_header):
    other = make_auth_header(role="customer", owner_org=None)
    assert client.get(f"/app/checks/{check_id}/obstacles", headers=other).status_code == 404


def test_no_detector_configured_is_reported_not_silently_empty(client, auth, check_id):
    """The regression this guards: an empty list rendered as a clear roof
    when detection has never run."""
    settings = MagicMock(openai_api_key="")
    with (
        patch.object(sites_repo, "applied_obstacles", return_value=[]),
        patch("solarfit.routers.app_checks.get_settings", return_value=settings),
    ):
        body = client.get(f"/app/checks/{check_id}/obstacles", headers=auth).json()

    assert body["obstacles"] == []
    assert body["detected"] is False  # nothing looked
    assert body["reason"]


def test_detector_configured_but_clear_roof_is_detected_true(client, auth, check_id):
    """The other half of the same distinction: a detector that ran and
    found nothing genuinely means a clear roof."""
    settings = MagicMock(openai_api_key="sk-real-key")
    with (
        patch.object(sites_repo, "applied_obstacles", return_value=[]),
        patch("solarfit.routers.app_checks.get_settings", return_value=settings),
    ):
        body = client.get(f"/app/checks/{check_id}/obstacles", headers=auth).json()

    assert body["obstacles"] == []
    assert body["detected"] is True
    assert body["reason"] is None


def test_applied_obstacles_are_returned_as_drawable_rings(client, auth, check_id):
    with patch.object(
        sites_repo, "applied_obstacles", return_value=[("obs-1", POLYGON, "water_tank", 0.95, "obstacle_detection")]
    ):
        body = client.get(f"/app/checks/{check_id}/obstacles", headers=auth).json()

    assert body["detected"] is True
    assert len(body["obstacles"]) == 1
    obstacle = body["obstacles"][0]
    assert obstacle["id"] == "obs-1"
    assert obstacle["type"] == "water_tank"
    assert obstacle["confidence"] == 0.95
    # Ring order is preserved and the lng/lat swap actually happened.
    assert len(obstacle["polygon"]) == 5
    assert obstacle["polygon"][0] == {"lat": 17.385, "lng": 78.4867}


def test_a_degenerate_polygon_is_dropped_not_drawn(client, auth, check_id):
    """Two points cannot be an area. Rendering it would put a stray line
    across the customer's roof."""
    degenerate = {"type": "Polygon", "coordinates": [[[78.4867, 17.385], [78.4868, 17.385]]]}
    with patch.object(sites_repo, "applied_obstacles", return_value=[("bad", degenerate, None, None, "obstacle_detection")]):
        body = client.get(f"/app/checks/{check_id}/obstacles", headers=auth).json()

    assert body["obstacles"] == []


def test_multiple_obstacles_all_come_back(client, auth, check_id):
    with patch.object(
        sites_repo,
        "applied_obstacles",
        return_value=[
            ("a", POLYGON, "hvac_unit", 0.8, "obstacle_detection"),
            ("b", POLYGON, "chimney", 0.7, "obstacle_detection"),
        ],
    ):
        body = client.get(f"/app/checks/{check_id}/obstacles", headers=auth).json()

    assert [o["id"] for o in body["obstacles"]] == ["a", "b"]


# ---------------------------------------------------------------------------
# POST/DELETE /app/checks/{id}/obstacles — the customer marking what's
# really on their own roof. Not a second obstacle system: it writes into
# the same applied_obstacle_ids/applied_obstacle_polygons provenance the
# OBS-04 auto-apply uses, so GET above returns detected + marked ones
# together with no special-casing.
# ---------------------------------------------------------------------------

# A ~22 m square roof, big enough that a 1.5 m marked obstacle is a
# plausible fraction of it (GEO-07's max_obstacle_area_fraction_of_boundary).
ROOF = [
    {"lat": 17.3849, "lng": 78.4866},
    {"lat": 17.3849, "lng": 78.4868},
    {"lat": 17.3851, "lng": 78.4868},
    {"lat": 17.3851, "lng": 78.4866},
]
ROOF_CENTRE = {"lat": 17.3850, "lng": 78.4867}


@pytest.fixture
def roofed_check_id(client, auth, check_id):
    response = client.put(
        f"/app/checks/{check_id}/boundary", json={"points": ROOF}, headers=auth
    )
    assert response.status_code == 200, response.text
    return check_id


def test_marking_an_obstacle_requires_auth(client, roofed_check_id):
    response = client.post(
        f"/app/checks/{roofed_check_id}/obstacles",
        json={"type": "water_tank", **ROOF_CENTRE},
    )
    assert response.status_code == 401


def test_marked_obstacle_is_returned_by_the_same_get(client, auth, roofed_check_id):
    created = client.post(
        f"/app/checks/{roofed_check_id}/obstacles",
        json={"type": "water_tank", **ROOF_CENTRE},
        headers=auth,
    )
    assert created.status_code == 201, created.text
    marked = created.json()
    assert marked["type"] == "water_tank"
    assert marked["source"] == "customer_marked"
    # A customer pointing at their own roof is a statement, not a
    # probabilistic detection — no confidence is invented for it.
    assert marked["confidence"] is None
    assert len(marked["polygon"]) == 5  # a closed square ring

    body = client.get(f"/app/checks/{roofed_check_id}/obstacles", headers=auth).json()
    assert body["detected"] is True
    assert [o["id"] for o in body["obstacles"]] == [marked["id"]]


def test_marking_an_obstacle_grows_the_exclusions(client, auth, roofed_check_id, db_session):
    before = sites_repo.get(db_session, roofed_check_id).exclusions
    client.post(
        f"/app/checks/{roofed_check_id}/obstacles",
        json={"type": "hvac_unit", **ROOF_CENTRE},
        headers=auth,
    )
    after = sites_repo.get(db_session, roofed_check_id).exclusions

    # This is what actually shrinks usable area: AREA-04 subtracts
    # site.exclusions from the boundary.
    assert after and after != before
    assert after["coordinates"]


def test_marking_an_obstacle_really_shrinks_the_usable_area(
    client, auth, roofed_check_id, db_session
):
    """The whole point of the feature, asserted end to end rather than
    reasoned about: the customer's tap has to reach AREA-04, which is the
    number that drives capacity, panel count and savings."""
    before = compute_usable_area_m2(sites_repo.get(db_session, roofed_check_id))
    client.post(
        f"/app/checks/{roofed_check_id}/obstacles",
        json={"type": "water_tank", **ROOF_CENTRE},
        headers=auth,
    )
    after = compute_usable_area_m2(sites_repo.get(db_session, roofed_check_id))

    # A 1.5 m square, buffered out by the pack's obstacle_setback_m — so
    # strictly more than the square's own 2.25 m², and nowhere near the
    # whole roof.
    assert after < before
    assert 2.25 < (before - after) < 0.25 * before


def test_a_tap_outside_the_roof_is_rejected(client, auth, roofed_check_id):
    response = client.post(
        f"/app/checks/{roofed_check_id}/obstacles",
        json={"type": "chimney", "lat": 17.4000, "lng": 78.5000},
        headers=auth,
    )
    assert response.status_code == 422


def test_removing_a_marked_obstacle_takes_it_back_out(client, auth, roofed_check_id):
    obstacle_id = client.post(
        f"/app/checks/{roofed_check_id}/obstacles",
        json={"type": "vent", **ROOF_CENTRE},
        headers=auth,
    ).json()["id"]

    deleted = client.delete(
        f"/app/checks/{roofed_check_id}/obstacles/{obstacle_id}", headers=auth
    )
    assert deleted.status_code == 204

    settings = MagicMock(openai_api_key="sk-real-key")
    with patch("solarfit.routers.app_checks.get_settings", return_value=settings):
        body = client.get(f"/app/checks/{roofed_check_id}/obstacles", headers=auth).json()
    assert body["obstacles"] == []


def test_a_customer_cannot_remove_an_ai_detected_obstacle(
    client, auth, roofed_check_id, db_session
):
    """OBS-06 reversal of a pipeline detection is an audited admin path
    (engine/obstacles.py::reject_applied_obstacle), not a customer tap."""
    detected_polygon = {
        "type": "Polygon",
        "coordinates": [
            [
                [78.48668, 17.38498],
                [78.48670, 17.38498],
                [78.48670, 17.38500],
                [78.48668, 17.38500],
                [78.48668, 17.38498],
            ]
        ],
    }
    sites_repo.new_geometry_version(
        db_session,
        roofed_check_id,
        exclusions={"type": "MultiPolygon", "coordinates": [detected_polygon["coordinates"]]},
        actor="system:obstacle_detection",
        source="obstacle_detection",
        applied_obstacle_ids=["ai-1"],
        applied_obstacle_polygons={
            "ai-1": {"polygon": detected_polygon, "type": "antenna", "confidence": 0.9}
        },
    )
    db_session.flush()

    response = client.delete(f"/app/checks/{roofed_check_id}/obstacles/ai-1", headers=auth)
    assert response.status_code == 403


def test_removing_an_unknown_obstacle_is_404(client, auth, roofed_check_id):
    response = client.delete(
        f"/app/checks/{roofed_check_id}/obstacles/not-a-real-id", headers=auth
    )
    assert response.status_code == 404
