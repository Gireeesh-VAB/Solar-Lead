"""Owner: karthik (App Platform & Foundation).

Tests for routers/app_sites.py (the frontend-shaped site domain) and the
repositories/sites.py additions it depends on (composite sites, the new
address/district/state/tags columns).

POST /app/sites always triggers routers/sites.py::create_site_core()'s
address-based Solar API resolution (AppSiteCreate has no boundary field
of its own, only a required `address`) — every test that creates a site
through this endpoint monkeypatches
`solarfit.routers.sites.solar_api.resolve_for_address` rather than
hitting the real Google Solar API, the same "patch where it's looked up"
approach test_solar_api.py's own fixtures use.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from solarfit.db import get_session
from solarfit.main import app
from solarfit.providers.solar_api import SolarApiResult

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
    """Every POST /app/sites in this file resolves via this fake unless
    a test overrides it — a real boundary, no network call."""
    monkeypatch.setattr(
        "solarfit.routers.sites.solar_api.resolve_for_address",
        lambda address, **kw: SolarApiResult(status="ok", boundary=BOUNDARY),
    )


def _create_body(**overrides):
    body = {
        "name": "Test Rooftop",
        "siteType": "ROOFTOP_RESIDENTIAL",
        "address": f"{uuid4().hex[:6]} Test Street, Hyderabad",
        "district": "Hyderabad",
        "state": "Telangana",
        "lat": 17.385,
        "lng": 78.4867,
    }
    body.update(overrides)
    return body


# --------------------------------------------------------------------- #
# create + get + list
# --------------------------------------------------------------------- #


def test_create_site_returns_camelcase_frontend_shape(client, make_auth_header):
    headers = make_auth_header(role="customer")
    response = client.post("/app/sites", json=_create_body(), headers=headers)
    assert response.status_code == 201
    body = response.json()
    assert body["siteType"] == "ROOFTOP_RESIDENTIAL"
    assert body["address"] == _create_body()["address"] or body["address"]  # non-empty at least
    assert body["district"] == "Hyderabad"
    assert body["state"] == "Telangana"
    assert body["location"] == {"lat": pytest.approx(17.385), "lng": pytest.approx(78.4867)}
    assert body["boundary"] is not None and len(body["boundary"]) == 4  # closing point dropped
    assert body["tags"] == []
    assert body["usnStatus"] == "not_started"
    assert body["usn"] is None
    assert body["latestAssessment"] is None  # documented gap until omkar's assessments table


def test_create_site_requires_a_customer_account(client, make_auth_header):
    headers = make_auth_header(role="admin")
    response = client.post("/app/sites", json=_create_body(), headers=headers)
    assert response.status_code == 403


def test_create_site_requires_auth(client):
    response = client.post("/app/sites", json=_create_body())
    assert response.status_code == 401


def test_get_site_round_trips(client, make_auth_header):
    headers = make_auth_header(role="customer")
    created = client.post("/app/sites", json=_create_body(), headers=headers).json()

    response = client.get(f"/app/sites/{created['id']}", headers=headers)
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_unknown_site_is_404(client, make_auth_header):
    headers = make_auth_header(role="customer")
    response = client.get("/app/sites/00000000-0000-0000-0000-000000000000", headers=headers)
    assert response.status_code == 404


def test_get_another_customers_site_is_404(client, make_auth_header):
    owner_headers = make_auth_header(role="customer", owner_org="Owner Org")
    other_headers = make_auth_header(role="customer", owner_org="Other Org")
    created = client.post("/app/sites", json=_create_body(), headers=owner_headers).json()

    response = client.get(f"/app/sites/{created['id']}", headers=other_headers)
    assert response.status_code == 404


def test_list_sites_is_scoped_to_the_callers_owner_org(client, make_auth_header):
    mine = make_auth_header(role="customer", owner_org="Mine Org")
    theirs = make_auth_header(role="customer", owner_org="Their Org")
    client.post("/app/sites", json=_create_body(), headers=mine)
    client.post("/app/sites", json=_create_body(), headers=theirs)

    response = client.get("/app/sites", headers=mine)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1


def test_list_sites_filters_by_q_and_site_type(client, make_auth_header):
    headers = make_auth_header(role="customer")
    client.post("/app/sites", json=_create_body(name="Rooftop Alpha", siteType="ROOFTOP_RESIDENTIAL"), headers=headers)
    client.post("/app/sites", json=_create_body(name="Rooftop Beta", siteType="ROOFTOP_CI"), headers=headers)

    response = client.get("/app/sites", headers=headers, params={"q": "Alpha"})
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "Rooftop Alpha"

    response = client.get("/app/sites", headers=headers, params={"siteType": "ROOFTOP_CI"})
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["siteType"] == "ROOFTOP_CI"


def test_list_sites_paginates(client, make_auth_header):
    headers = make_auth_header(role="customer")
    for _ in range(3):
        client.post("/app/sites", json=_create_body(), headers=headers)

    response = client.get("/app/sites", headers=headers, params={"page": 1, "pageSize": 2})
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2

    response = client.get("/app/sites", headers=headers, params={"page": 2, "pageSize": 2})
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 1


def test_list_sites_verdict_filter_is_empty_until_assessments_exist(client, make_auth_header):
    headers = make_auth_header(role="customer")
    client.post("/app/sites", json=_create_body(), headers=headers)

    response = client.get("/app/sites", headers=headers, params={"verdict": "SUITABLE"})
    body = response.json()
    assert body["total"] == 0


# --------------------------------------------------------------------- #
# portfolio summary
# --------------------------------------------------------------------- #


def test_portfolio_summary_counts_sites_and_breaks_down_by_type(client, make_auth_header):
    headers = make_auth_header(role="customer")
    client.post("/app/sites", json=_create_body(siteType="ROOFTOP_RESIDENTIAL"), headers=headers)
    client.post("/app/sites", json=_create_body(siteType="ROOFTOP_CI"), headers=headers)

    response = client.get("/app/sites/portfolio-summary", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["totalSites"] == 2
    assert body["siteTypeBreakdown"] == {"ROOFTOP_RESIDENTIAL": 1, "ROOFTOP_CI": 1}
    # documented gaps — honest zeros until omkar's/keerthana's tables land
    assert body["totalCapacityKwp"] == 0.0
    assert body["activeJobs"] == 0


# --------------------------------------------------------------------- #
# composite sites
# --------------------------------------------------------------------- #


def test_create_composite_site_happy_path(client, make_auth_header):
    headers = make_auth_header(role="customer")
    site_a = client.post("/app/sites", json=_create_body(), headers=headers).json()
    site_b = client.post("/app/sites", json=_create_body(), headers=headers).json()

    response = client.post(
        "/app/composites",
        json={"name": "Feeder 12 Group", "feederOrDt": "Feeder-12", "memberSiteIds": [site_a["id"], site_b["id"]]},
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["memberSiteIds"] == [site_a["id"], site_b["id"]]
    assert body["aggregateCapacityKwp"] == 0.0  # documented gap until assessments exist


def test_create_composite_site_rejects_an_unknown_member(client, make_auth_header):
    headers = make_auth_header(role="customer")
    response = client.post(
        "/app/composites",
        json={"name": "Bad Group", "feederOrDt": "Feeder-1", "memberSiteIds": ["00000000-0000-0000-0000-000000000000"]},
        headers=headers,
    )
    assert response.status_code == 422


def test_create_composite_site_rejects_another_tenants_site(client, make_auth_header):
    mine = make_auth_header(role="customer", owner_org="Mine Org")
    theirs = make_auth_header(role="customer", owner_org="Their Org")
    their_site = client.post("/app/sites", json=_create_body(), headers=theirs).json()

    response = client.post(
        "/app/composites",
        json={"name": "Sneaky Group", "feederOrDt": "Feeder-1", "memberSiteIds": [their_site["id"]]},
        headers=mine,
    )
    assert response.status_code == 422


def test_list_composites_is_scoped_to_the_callers_owner_org(client, make_auth_header):
    mine = make_auth_header(role="customer", owner_org="Mine Org")
    theirs = make_auth_header(role="customer", owner_org="Their Org")
    my_site = client.post("/app/sites", json=_create_body(), headers=mine).json()
    their_site = client.post("/app/sites", json=_create_body(), headers=theirs).json()
    client.post(
        "/app/composites",
        json={"name": "Mine", "feederOrDt": "F1", "memberSiteIds": [my_site["id"]]},
        headers=mine,
    )
    client.post(
        "/app/composites",
        json={"name": "Theirs", "feederOrDt": "F2", "memberSiteIds": [their_site["id"]]},
        headers=theirs,
    )

    response = client.get("/app/composites", headers=mine)
    assert response.status_code == 200
    assert [c["name"] for c in response.json()] == ["Mine"]


# --------------------------------------------------------------------- #
# history
# --------------------------------------------------------------------- #


def test_site_history_includes_a_created_event(client, make_auth_header):
    headers = make_auth_header(role="customer")
    created = client.post("/app/sites", json=_create_body(), headers=headers).json()

    response = client.get(f"/app/sites/{created['id']}/history", headers=headers)
    assert response.status_code == 200
    kinds = [e["kind"] for e in response.json()]
    assert "created" in kinds


def test_site_history_is_ordered_oldest_first(client, make_auth_header):
    headers = make_auth_header(role="customer")
    created = client.post("/app/sites", json=_create_body(), headers=headers).json()

    response = client.get(f"/app/sites/{created['id']}/history", headers=headers)
    timestamps = [e["timestamp"] for e in response.json()]
    assert timestamps == sorted(timestamps)


def test_site_history_for_unknown_site_is_404(client, make_auth_header):
    headers = make_auth_header(role="customer")
    response = client.get("/app/sites/00000000-0000-0000-0000-000000000000/history", headers=headers)
    assert response.status_code == 404
