"""§9.8 Interface — the sites surface, end to end. Person 1.

Exercises the real app against the real database: HTTP in, validated
geometry stored, usable area out.
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import box as shapely_box
from shapely.geometry import mapping

from solarfit.db import get_session
from solarfit.main import app

LON, LAT = 78.4867, 17.3850
ORG = "org-alpha"
HEADERS = {"X-Owner-Org": ORG}


@pytest.fixture
def client(db_session):
    """App wired to the test transaction, so API writes roll back too."""
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _poly(size: float = 0.0005, dlon: float = 0.0, dlat: float = 0.0) -> dict:
    return mapping(shapely_box(LON + dlon, LAT + dlat, LON + dlon + size, LAT + dlat + size))


def _payload(**kwargs) -> dict:
    return {
        "site_type": "ROOFTOP_RESIDENTIAL",
        "name": "Test roof",
        "jurisdiction": "IN-TG",
        "boundary": _poly(),
        **kwargs,
    }


# --------------------------------------------------------------------- #
# the Day 1 slice: polygon in, square metres out
# --------------------------------------------------------------------- #


def test_create_site_returns_a_usable_area(client):
    response = client.post("/sites", json=_payload(), headers=HEADERS)
    assert response.status_code == 201, response.text

    body = response.json()
    assert body["site"]["site_type"] == "ROOFTOP_RESIDENTIAL"
    assert body["site"]["geometry_source"] == "manual_polygon"
    assert body["current_version"] == 1
    assert body["usable_area_m2"] > 0
    # Never planar degrees — a square-degree number would be ~1e-7.
    assert body["boundary_area_m2"] > 1_000
    assert body["usable_area_m2"] < body["boundary_area_m2"]


def test_centroid_is_derived_from_the_boundary_when_omitted(client):
    body = client.post("/sites", json=_payload(), headers=HEADERS).json()
    assert body["site"]["centroid"]["coordinates"][0] == pytest.approx(LON, abs=1e-3)


def test_confidence_is_scored_on_create(client):
    """GEO-09 — a 4-corner box drawn by an operator, not a detailed trace."""
    body = client.post("/sites", json=_payload(), headers=HEADERS).json()
    confidence = body["site"]["geometry_confidence"]
    assert 0.0 < confidence < 1.0


def test_site_without_geometry_has_no_usable_area(client):
    """INSUFFICIENT_DATA, deliberately not zero."""
    payload = _payload(boundary=None, centroid={"type": "Point", "coordinates": [LON, LAT]})
    body = client.post("/sites", json=payload, headers=HEADERS).json()
    assert body["usable_area_m2"] is None
    assert body["current_version"] == 0


# --------------------------------------------------------------------- #
# GEO-07 / GEO-08 — rejected, never silently repaired
# --------------------------------------------------------------------- #


def test_self_intersecting_boundary_is_rejected(client):
    bowtie = {
        "type": "Polygon",
        "coordinates": [
            [
                [LON, LAT],
                [LON + 0.0005, LAT + 0.0005],
                [LON + 0.0005, LAT],
                [LON, LAT + 0.0005],
                [LON, LAT],
            ]
        ],
    }
    response = client.post("/sites", json=_payload(boundary=bowtie), headers=HEADERS)
    assert response.status_code == 422
    assert "self-intersecting" in response.json()["detail"]


def test_implausibly_large_boundary_is_rejected(client):
    huge = mapping(shapely_box(LON, LAT, LON + 0.5, LAT + 0.5))  # ~55 km square
    response = client.post("/sites", json=_payload(boundary=huge), headers=HEADERS)
    assert response.status_code == 422
    assert "implausibly large" in response.json()["detail"]


def test_exclusion_outside_the_boundary_is_rejected(client):
    payload = _payload(exclusions=[_poly(size=0.0002, dlon=0.01)])  # ~1 km away
    response = client.post("/sites", json=payload, headers=HEADERS)
    assert response.status_code == 422
    assert "outside" in response.json()["detail"]


def test_exclusion_inside_the_boundary_reduces_usable_area(client):
    clean = client.post("/sites", json=_payload(), headers=HEADERS).json()
    with_obstacle = client.post(
        "/sites",
        json=_payload(exclusions=[_poly(size=0.0002, dlon=0.0001, dlat=0.0001)]),
        headers=HEADERS,
    ).json()

    assert with_obstacle["usable_area_m2"] < clean["usable_area_m2"]


# --------------------------------------------------------------------- #
# tenant scoping
# --------------------------------------------------------------------- #


def test_missing_tenant_header_is_401(client):
    assert client.post("/sites", json=_payload()).status_code == 401


def test_another_tenants_site_is_404_not_403(client):
    """A 403 would confirm the id exists — itself a cross-tenant leak."""
    created = client.post("/sites", json=_payload(), headers=HEADERS).json()
    site_id = created["site"]["id"]

    assert client.get(f"/sites/{site_id}", headers=HEADERS).status_code == 200
    assert client.get(f"/sites/{site_id}", headers={"X-Owner-Org": "org-beta"}).status_code == 404


def test_list_only_returns_the_callers_sites(client):
    # Unique orgs per run: `sites` is shared with whatever else exists in
    # this database, so asserting against a fixed org would be testing
    # table emptiness rather than tenant scoping.
    alpha = {"X-Owner-Org": f"org-alpha-{uuid4().hex[:8]}"}
    beta = {"X-Owner-Org": f"org-beta-{uuid4().hex[:8]}"}

    client.post("/sites", json=_payload(name="Alpha roof"), headers=alpha)
    client.post("/sites", json=_payload(name="Beta roof"), headers=beta)

    assert [s["site"]["name"] for s in client.get("/sites", headers=alpha).json()] == [
        "Alpha roof"
    ]
    assert [s["site"]["name"] for s in client.get("/sites", headers=beta).json()] == ["Beta roof"]


def test_malformed_id_is_404_not_500(client):
    assert client.get("/sites/not-a-uuid", headers=HEADERS).status_code == 404


# --------------------------------------------------------------------- #
# SITE-05 — history is visible
# --------------------------------------------------------------------- #


def test_versions_endpoint_exposes_the_history(client):
    created = client.post("/sites", json=_payload(), headers=HEADERS).json()
    history = client.get(f"/sites/{created['site']['id']}/versions", headers=HEADERS).json()

    assert len(history) == 1
    assert history[0]["version_no"] == 1
    assert history[0]["source"] == "manual_polygon"
    assert history[0]["actor"] == ORG


# --------------------------------------------------------------------- #
# SITE-02 / USN-05 — enforced at the API boundary, not just in the unit
# --------------------------------------------------------------------- #


def test_usn_on_a_government_site_is_rejected_by_the_endpoint(client):
    """Regression: `usn` was absent from SiteCreate, so Pydantic dropped
    it before the schema check ran and the site was created anyway. The
    prohibition only means anything if it holds over HTTP."""
    payload = _payload(site_type="ROOFTOP_GOVT", usn="1234567890")
    r = client.post("/sites", json=payload, headers=HEADERS)
    assert r.status_code == 422
    assert "not billing-linked" in r.json()["detail"]


def test_usn_on_a_residential_site_is_accepted_by_the_endpoint(client):
    r = client.post("/sites", json=_payload(usn="1234567890"), headers=HEADERS)
    assert r.status_code == 201


def test_government_site_without_usn_is_fine(client):
    r = client.post("/sites", json=_payload(site_type="ROOFTOP_GOVT"), headers=HEADERS)
    assert r.status_code == 201
