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
from solarfit.main import app
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
    """A real owned check — the endpoint is ownership-gated."""
    with patch(
        "solarfit.routers.sites.solar_api.resolve_for_address",
        return_value=MagicMock(status="ok", boundary=None, shading=None),
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
    with patch.object(sites_repo, "applied_obstacles", return_value=[("obs-1", POLYGON)]):
        body = client.get(f"/app/checks/{check_id}/obstacles", headers=auth).json()

    assert body["detected"] is True
    assert len(body["obstacles"]) == 1
    obstacle = body["obstacles"][0]
    assert obstacle["id"] == "obs-1"
    # Ring order is preserved and the lng/lat swap actually happened.
    assert len(obstacle["polygon"]) == 5
    assert obstacle["polygon"][0] == {"lat": 17.385, "lng": 78.4867}


def test_a_degenerate_polygon_is_dropped_not_drawn(client, auth, check_id):
    """Two points cannot be an area. Rendering it would put a stray line
    across the customer's roof."""
    degenerate = {"type": "Polygon", "coordinates": [[[78.4867, 17.385], [78.4868, 17.385]]]}
    with patch.object(sites_repo, "applied_obstacles", return_value=[("bad", degenerate)]):
        body = client.get(f"/app/checks/{check_id}/obstacles", headers=auth).json()

    assert body["obstacles"] == []


def test_multiple_obstacles_all_come_back(client, auth, check_id):
    with patch.object(
        sites_repo, "applied_obstacles", return_value=[("a", POLYGON), ("b", POLYGON)]
    ):
        body = client.get(f"/app/checks/{check_id}/obstacles", headers=auth).json()

    assert [o["id"] for o in body["obstacles"]] == ["a", "b"]
