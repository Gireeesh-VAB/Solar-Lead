"""Owner: keerthana (Vendor domain, customer-account admin, jurisdictions).

GET /app/jurisdictions honestly returns the one jurisdiction override
that actually exists (AP) — packs/registry.py's _jurisdiction_overrides()
is the source of truth this list mirrors.
"""

import pytest
from fastapi.testclient import TestClient

from solarfit.db import get_session
from solarfit.main import app


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_requires_auth(client):
    r = client.get("/app/jurisdictions")
    assert r.status_code == 401


def test_lists_the_one_real_jurisdiction(client, make_auth_header):
    r = client.get("/app/jurisdictions", headers=make_auth_header(role="customer"))
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    j = body[0]
    assert j["jurisdiction"] == "AP"
    assert j["state"] == "Andhra Pradesh"
    assert j["version"] == "in_ap_v1"
    assert j["rules"] == [
        {
            "name": "net_metering_cap",
            "kind": "regulatory",
            "description": "Stricter net-metering export ratio than the national rooftop_v1 default.",
        }
    ]
