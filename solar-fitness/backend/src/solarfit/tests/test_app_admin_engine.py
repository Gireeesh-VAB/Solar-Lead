"""Owner: karthik (App Platform & Foundation).

Tests for routers/app_admin_engine.py — admin routes exposing
CACHE-04's force_refresh() and OBS-06's reject_applied_obstacle(),
neither of which had any HTTP surface before this pass despite being
real, tested engine functions.

reject_applied_obstacle() (engine/obstacles.py) opens its own real
solarfit.db.session_scope() internally rather than taking a session
parameter — same pattern test_app_imports.py's Celery-task tests hit —
so the site fixture below is created through a real, committed
session_scope() call too (matching test_analysis_cache.py's own
integration-test style) rather than through the test's transactional,
never-committed db_session, which a separate connection wouldn't see.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import box as shapely_box
from shapely.geometry import mapping

from solarfit.db import get_session, session_scope
from solarfit.main import app
from solarfit.repositories import audit as audit_repo
from solarfit.repositories import sites as sites_repo
from solarfit.repositories.analysis_cache import create as create_cache_row
from solarfit.repositories.analysis_cache import find_by_key, force_refresh, round_latlng

LON, LAT = 78.4867, 17.3850


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _poly(dlon: float = 0.0, dlat: float = 0.0, size: float = 0.0005) -> dict:
    return mapping(shapely_box(LON + dlon, LAT + dlat, LON + dlon + size, LAT + dlat + size))


def _multipoly(*polys: dict) -> dict:
    return {"type": "MultiPolygon", "coordinates": [p["coordinates"] for p in polys]}


# --------------------------------------------------------------------- #
# POST /app/admin/cache/force-refresh
# --------------------------------------------------------------------- #


def test_force_refresh_requires_admin_role(client, make_auth_header):
    headers = make_auth_header(role="customer")
    response = client.post("/app/admin/cache/force-refresh", headers=headers, json={"lat": 19.9, "lng": 80.8})
    assert response.status_code == 403


def test_force_refresh_requires_auth(client):
    response = client.post("/app/admin/cache/force-refresh", json={"lat": 19.9, "lng": 80.8})
    assert response.status_code == 401


def test_force_refresh_clears_an_existing_cache_entry(client, make_auth_header):
    lat, lng = 19.99991, 80.88882  # same key test_analysis_cache.py's clean_key uses
    lat_r, lng_r = round_latlng(lat, lng)
    force_refresh(lat, lng)
    create_cache_row(lat_rounded=lat_r, lng_rounded=lng_r, boundary=_poly())
    assert find_by_key(lat_r, lng_r) is not None

    headers = make_auth_header(role="admin")
    try:
        response = client.post("/app/admin/cache/force-refresh", headers=headers, json={"lat": lat, "lng": lng})
        assert response.status_code == 200
        assert find_by_key(lat_r, lng_r) is None
    finally:
        force_refresh(lat, lng)


def test_force_refresh_writes_an_audit_log_entry(client, make_auth_header, db_session):
    headers = make_auth_header(role="admin")
    client.post("/app/admin/cache/force-refresh", headers=headers, json={"lat": 19.9, "lng": 80.8})

    rows = audit_repo.list_audit_log(db_session, action="platform.cache_force_refresh")
    assert any("19.9" in r.target for r in rows)


# --------------------------------------------------------------------- #
# POST /app/admin/sites/{site_id}/obstacles/{obstacle_id}/reject
# --------------------------------------------------------------------- #


def _create_site_with_applied_obstacle() -> tuple[str, str]:
    """Returns (site_id, obstacle_id), committed for real so
    reject_applied_obstacle()'s own session_scope() call can see it."""
    boundary = _poly()
    obstacle_polygon = _poly(dlon=0.0001, dlat=0.0001, size=0.0001)
    with session_scope() as session:
        site = sites_repo.create(
            session,
            site_type="ROOFTOP_RESIDENTIAL",
            name="Test roof",
            owner_org="org-alpha",
            jurisdiction="IN-TG",
            centroid={"type": "Point", "coordinates": [LON, LAT]},
            boundary=boundary,
            geometry_source="solar_api",
            actor="tester",
        )
        sites_repo.new_geometry_version(
            session,
            site.id,
            exclusions=_multipoly(obstacle_polygon),
            actor="system:obstacle_detection",
            source="obstacle_detection",
            applied_obstacle_ids=["obstacle-a"],
            applied_obstacle_polygons={"obstacle-a": obstacle_polygon},
        )
    return site.id, "obstacle-a"


def test_reject_obstacle_requires_admin_role(client, make_auth_header):
    site_id, obstacle_id = _create_site_with_applied_obstacle()
    headers = make_auth_header(role="customer")

    response = client.post(f"/app/admin/sites/{site_id}/obstacles/{obstacle_id}/reject", headers=headers)
    assert response.status_code == 403


def test_reject_obstacle_requires_auth(client):
    site_id, obstacle_id = _create_site_with_applied_obstacle()
    response = client.post(f"/app/admin/sites/{site_id}/obstacles/{obstacle_id}/reject")
    assert response.status_code == 401


def test_reject_obstacle_supersedes_and_recomputes(client, make_auth_header):
    site_id, obstacle_id = _create_site_with_applied_obstacle()
    headers = make_auth_header(role="admin")

    response = client.post(f"/app/admin/sites/{site_id}/obstacles/{obstacle_id}/reject", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["siteId"] == site_id
    assert body["obstacleId"] == obstacle_id
    assert body["usableAreaM2"] is not None

    with session_scope() as session:
        history = sites_repo.versions(session, site_id)
    assert history[-1].source == "obstacle_rejected"


def test_reject_obstacle_unknown_obstacle_is_404(client, make_auth_header):
    site_id, _obstacle_id = _create_site_with_applied_obstacle()
    headers = make_auth_header(role="admin")

    response = client.post(f"/app/admin/sites/{site_id}/obstacles/nonexistent/reject", headers=headers)
    assert response.status_code == 404


def test_reject_obstacle_unknown_site_is_404(client, make_auth_header):
    headers = make_auth_header(role="admin")

    response = client.post(
        "/app/admin/sites/00000000-0000-0000-0000-000000000000/obstacles/obstacle-a/reject", headers=headers
    )
    assert response.status_code == 404


def test_reject_obstacle_writes_an_audit_log_entry(client, make_auth_header, db_session):
    site_id, obstacle_id = _create_site_with_applied_obstacle()
    headers = make_auth_header(role="admin")

    client.post(f"/app/admin/sites/{site_id}/obstacles/{obstacle_id}/reject", headers=headers)

    rows = audit_repo.list_audit_log(db_session, action="obstacle.rejected")
    assert any(r.target == f"{site_id}:{obstacle_id}" for r in rows)
