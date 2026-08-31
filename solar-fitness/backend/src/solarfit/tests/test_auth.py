"""API-06 — API-key auth and per-tenant rate limiting. Person 1."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import box as shapely_box
from shapely.geometry import mapping

from solarfit import auth
from solarfit.config import get_settings
from solarfit.db import get_session
from solarfit.main import app

LON, LAT = 78.4867, 17.3850


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def issued(db_session):
    org = f"org-{uuid4().hex[:8]}"
    raw, row = auth.create_api_key(db_session, owner_org=org, name="test key")
    return raw, row, org


def _payload():
    return {
        "site_type": "ROOFTOP_RESIDENTIAL",
        "name": "Keyed roof",
        "jurisdiction": "IN-TG",
        "boundary": mapping(shapely_box(LON, LAT, LON + 0.0005, LAT + 0.0005)),
    }


# --------------------------------------------------------------------- #
# key storage
# --------------------------------------------------------------------- #


def test_only_a_hash_is_stored(issued):
    raw, row, _ = issued
    assert row.key_hash != raw
    assert len(row.key_hash) == 64
    assert raw not in row.key_hash


def test_prefix_is_stored_in_clear_for_identification(issued):
    raw, row, _ = issued
    assert row.prefix == raw[: auth.PREFIX_LENGTH]
    assert raw.startswith("sk_")


def test_two_keys_are_never_the_same(db_session):
    a, _ = auth.create_api_key(db_session, owner_org="o", name="a")
    b, _ = auth.create_api_key(db_session, owner_org="o", name="b")
    assert a != b


def test_resolve_finds_a_live_key(db_session, issued):
    raw, row, _ = issued
    assert auth.resolve_api_key(db_session, raw).id == row.id


def test_revoked_key_does_not_resolve(db_session, issued):
    raw, row, _ = issued
    row.revoked_at = datetime.now(UTC)
    db_session.flush()
    assert auth.resolve_api_key(db_session, raw) is None


def test_unknown_key_does_not_resolve(db_session):
    assert auth.resolve_api_key(db_session, "sk_nonsense") is None


# --------------------------------------------------------------------- #
# the dependency, through real requests
# --------------------------------------------------------------------- #


def test_valid_key_authenticates_and_scopes_to_its_tenant(client, issued):
    raw, _, org = issued
    r = client.post("/sites", json=_payload(), headers={"X-API-Key": raw})
    assert r.status_code == 201, r.text
    assert r.json()["site"]["owner_org"] == org


def test_a_key_cannot_read_another_tenants_site(client, db_session, issued):
    raw, _, _ = issued
    created = client.post("/sites", json=_payload(), headers={"X-API-Key": raw}).json()

    other_raw, _ = auth.create_api_key(db_session, owner_org=f"org-{uuid4().hex[:8]}", name="other")
    r = client.get(f"/sites/{created['site']['id']}", headers={"X-API-Key": other_raw})
    assert r.status_code == 404


def test_invalid_key_is_401(client):
    r = client.post("/sites", json=_payload(), headers={"X-API-Key": "sk_not_real"})
    assert r.status_code == 401
    assert "invalid or revoked" in r.json()["detail"]


def test_revoked_key_is_401_with_the_same_message(client, db_session, issued):
    """Distinguishing 'unknown' from 'revoked' would tell an attacker
    which of their guesses used to be a real key."""
    raw, row, _ = issued
    row.revoked_at = datetime.now(UTC)
    db_session.flush()

    r = client.post("/sites", json=_payload(), headers={"X-API-Key": raw})
    assert r.status_code == 401
    assert "invalid or revoked" in r.json()["detail"]


def test_no_credentials_at_all_is_401(client, monkeypatch):
    monkeypatch.setenv("ALLOW_HEADER_TENANT", "false")
    get_settings.cache_clear()
    try:
        r = client.post("/sites", json=_payload())
        assert r.status_code == 401
        assert r.headers.get("www-authenticate") == "ApiKey"
    finally:
        get_settings.cache_clear()


def test_header_tenant_is_refused_when_the_escape_hatch_is_off(client, monkeypatch):
    """The X-Owner-Org fallback exists for local development only. With
    it off, a caller naming their own tenant gets nowhere."""
    monkeypatch.setenv("ALLOW_HEADER_TENANT", "false")
    get_settings.cache_clear()
    try:
        r = client.post("/sites", json=_payload(), headers={"X-Owner-Org": "org-anything"})
        assert r.status_code == 401
    finally:
        get_settings.cache_clear()


def test_last_used_is_recorded(client, db_session, issued):
    raw, row, _ = issued
    assert row.last_used_at is None
    client.post("/sites", json=_payload(), headers={"X-API-Key": raw})
    db_session.refresh(row)
    assert row.last_used_at is not None


def test_key_also_authenticates_the_import_endpoint(client, issued):
    import json as _json

    raw, _, _ = issued
    doc = _json.dumps(
        {"type": "FeatureCollection",
         "features": [{"type": "Feature", "geometry": _payload()["boundary"], "properties": {}}]}
    ).encode()
    r = client.post(
        "/v1/imports",
        headers={"X-API-Key": raw},
        files={"file": ("a.geojson", doc, "application/json")},
    )
    assert r.status_code == 207
    assert r.json()["imported"] == 1


# --------------------------------------------------------------------- #
# rate limiting
# --------------------------------------------------------------------- #


def test_requests_under_the_limit_are_allowed():
    key_id = f"test-{uuid4().hex}"
    for _ in range(5):
        allowed, _ = auth.check_rate_limit(key_id, limit_per_minute=10)
        assert allowed


def test_the_limit_is_enforced():
    key_id = f"test-{uuid4().hex}"
    results = [auth.check_rate_limit(key_id, limit_per_minute=3)[0] for _ in range(5)]
    assert results[:3] == [True, True, True]
    assert results[3:] == [False, False]


def test_remaining_counts_down():
    key_id = f"test-{uuid4().hex}"
    _, first = auth.check_rate_limit(key_id, limit_per_minute=5)
    _, second = auth.check_rate_limit(key_id, limit_per_minute=5)
    assert first == 4
    assert second == 3


def test_separate_keys_have_separate_budgets():
    a, b = f"test-{uuid4().hex}", f"test-{uuid4().hex}"
    for _ in range(3):
        auth.check_rate_limit(a, limit_per_minute=3)
    assert auth.check_rate_limit(b, limit_per_minute=3)[0] is True


def test_exceeding_the_limit_returns_429(client, db_session):
    raw, _ = auth.create_api_key(
        db_session, owner_org=f"org-{uuid4().hex[:8]}", name="tight", rate_limit_per_minute=2
    )
    codes = [
        client.get("/sites", headers={"X-API-Key": raw}).status_code for _ in range(4)
    ]
    assert codes[:2] == [200, 200]
    assert 429 in codes[2:]


def test_rate_limiter_fails_open_when_redis_is_down(monkeypatch):
    """A limiter that hard-fails the API when its cache dies has turned a
    nice-to-have into a single point of failure."""
    monkeypatch.setattr(auth, "_redis", lambda: None)
    allowed, remaining = auth.check_rate_limit("anything", limit_per_minute=1)
    assert allowed
    assert remaining == 1
