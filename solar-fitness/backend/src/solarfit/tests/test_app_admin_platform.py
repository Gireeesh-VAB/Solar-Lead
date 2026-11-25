"""Owner: karthik (App Platform & Foundation).

Tests for repositories/audit.py (write_audit_log/list_audit_log) and
routers/app_admin_platform.py's three admin-only endpoints.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from solarfit.db import get_session
from solarfit.main import app
from solarfit.repositories import audit as audit_repo
from solarfit.repositories import sites as sites_repo


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# --------------------------------------------------------------------- #
# repositories/audit.py
# --------------------------------------------------------------------- #


def test_write_audit_log_persists_a_row(db_session):
    row = audit_repo.write_audit_log(
        db_session, actor="admin@example.com", action="platform.test", target="thing-1", details="did a thing"
    )
    assert row.id is not None
    assert row.actor == "admin@example.com"
    assert row.details == "did a thing"


def test_write_audit_log_details_defaults_to_none(db_session):
    row = audit_repo.write_audit_log(db_session, actor="admin@example.com", action="platform.test", target="thing-1")
    assert row.details is None


def test_list_audit_log_orders_by_created_at_descending(db_session):
    # Postgres's now() is transaction-scoped, so two writes inside this
    # test's single transactional db_session would otherwise share one
    # created_at — set explicit, distinct timestamps to actually exercise
    # the ORDER BY clause rather than relying on insertion order.
    older = audit_repo.write_audit_log(db_session, actor="a@example.com", action="act.one", target="t1")
    newer = audit_repo.write_audit_log(db_session, actor="a@example.com", action="act.two", target="t2")
    older.created_at = datetime(2020, 1, 1, tzinfo=UTC)
    newer.created_at = datetime(2020, 1, 2, tzinfo=UTC)
    db_session.flush()

    rows = audit_repo.list_audit_log(db_session)
    ids = [r.id for r in rows]
    assert ids.index(newer.id) < ids.index(older.id)


def test_list_audit_log_filters_by_actor_and_action(db_session):
    audit_repo.write_audit_log(db_session, actor="a@example.com", action="act.one", target="t1")
    audit_repo.write_audit_log(db_session, actor="b@example.com", action="act.two", target="t2")

    by_actor = audit_repo.list_audit_log(db_session, actor="a@example.com")
    assert {r.actor for r in by_actor} == {"a@example.com"}

    by_action = audit_repo.list_audit_log(db_session, action="act.two")
    assert {r.action for r in by_action} == {"act.two"}


def test_list_audit_log_q_matches_target_or_details(db_session):
    audit_repo.write_audit_log(db_session, actor="a@example.com", action="act.one", target="site-abc", details=None)
    audit_repo.write_audit_log(db_session, actor="a@example.com", action="act.two", target="other", details="mentions abc here")
    audit_repo.write_audit_log(db_session, actor="a@example.com", action="act.three", target="unrelated", details="nope")

    rows = audit_repo.list_audit_log(db_session, q="abc")
    targets = {r.target for r in rows}
    assert targets == {"site-abc", "other"}


# --------------------------------------------------------------------- #
# GET /app/admin/audit-log
# --------------------------------------------------------------------- #


def test_audit_log_endpoint_requires_admin_role(client, make_auth_header):
    headers = make_auth_header(role="customer")
    response = client.get("/app/admin/audit-log", headers=headers)
    assert response.status_code == 403


def test_audit_log_endpoint_requires_auth(client):
    response = client.get("/app/admin/audit-log")
    assert response.status_code == 401


def test_audit_log_endpoint_returns_camelcase_entries(client, make_auth_header, db_session):
    audit_repo.write_audit_log(db_session, actor="a@example.com", action="platform.test", target="t1", details="hi")
    headers = make_auth_header(role="admin")

    response = client.get("/app/admin/audit-log", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body) >= 1
    entry = next(e for e in body if e["target"] == "t1")
    assert entry["actor"] == "a@example.com"
    assert entry["details"] == "hi"
    assert "timestamp" in entry


def test_audit_log_endpoint_filters_by_query_params(client, make_auth_header, db_session):
    audit_repo.write_audit_log(db_session, actor="a@example.com", action="platform.rotate", target="Google Maps API")
    audit_repo.write_audit_log(db_session, actor="a@example.com", action="platform.other", target="unrelated")
    headers = make_auth_header(role="admin")

    response = client.get("/app/admin/audit-log", headers=headers, params={"action": "platform.rotate"})
    assert response.status_code == 200
    body = response.json()
    assert all(e["action"] == "platform.rotate" for e in body)


# --------------------------------------------------------------------- #
# GET /app/admin/platform-health
# --------------------------------------------------------------------- #


def test_platform_health_requires_admin_role(client, make_auth_header):
    headers = make_auth_header(role="vendor")
    response = client.get("/app/admin/platform-health", headers=headers)
    assert response.status_code == 403


def test_platform_health_returns_expected_shape(client, make_auth_header):
    headers = make_auth_header(role="admin")
    response = client.get("/app/admin/platform-health", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["uptimePct"] == 99.9  # documented placeholder — no uptime monitoring exists yet
    assert body["incidentsThisMonth"] == 0  # honest zero — nothing writes "platform.incident" yet
    assert len(body["quotas"]) == 4
    for quota in body["quotas"]:
        # `used` is a real count of this month's activity (see
        # _QUOTA_LIMITS's docstring) — not asserted as exactly 0, since a
        # shared dev database may already have sites/assessments from
        # this month. test_platform_health_quota_used_reflects_real_activity
        # below verifies it actually moves with real data.
        assert quota["used"] >= 0
        assert quota["limit"] > 0
        assert quota["unit"]


def test_platform_health_counts_incidents_this_month(client, make_auth_header, db_session):
    audit_repo.write_audit_log(db_session, actor="system", action="platform.incident", target="api-outage")
    headers = make_auth_header(role="admin")

    response = client.get("/app/admin/platform-health", headers=headers)
    assert response.json()["incidentsThisMonth"] == 1


def test_platform_health_quota_used_reflects_real_activity(client, make_auth_header, db_session):
    """Google Maps API's `used` is a real count of sites created this
    month — creating one more site must move it, not stay pinned at a
    hardcoded value."""
    headers = make_auth_header(role="admin")

    def maps_used() -> int:
        body = client.get("/app/admin/platform-health", headers=headers).json()
        return next(q["used"] for q in body["quotas"] if q["service"] == "Google Maps API")

    before = maps_used()
    sites_repo.create(
        db_session,
        site_type="ROOFTOP_RESIDENTIAL",
        name="Quota Test Rooftop",
        owner_org="Test Org",
        jurisdiction="IN-TG",
        centroid={"type": "Point", "coordinates": [78.4867, 17.3850]},
    )
    after = maps_used()
    assert after == before + 1


# --------------------------------------------------------------------- #
# POST /app/admin/api-keys/rotate
# --------------------------------------------------------------------- #


def test_rotate_api_key_requires_admin_role(client, make_auth_header):
    headers = make_auth_header(role="customer")
    response = client.post("/app/admin/api-keys/rotate", headers=headers, json={"service": "Google Maps API"})
    assert response.status_code == 403


def test_rotate_api_key_returns_service_and_timestamp(client, make_auth_header):
    headers = make_auth_header(role="admin")
    response = client.post("/app/admin/api-keys/rotate", headers=headers, json={"service": "Google Maps API"})
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "Google Maps API"
    assert "rotatedAt" in body


def test_rotate_api_key_writes_an_audit_log_entry(client, make_auth_header, db_session):
    headers = make_auth_header(role="admin")
    client.post("/app/admin/api-keys/rotate", headers=headers, json={"service": "Weather API"})

    rows = audit_repo.list_audit_log(db_session, action="platform.api_key_rotation_requested")
    assert any(r.target == "Weather API" for r in rows)


def test_rotate_api_key_rejects_empty_service(client, make_auth_header):
    headers = make_auth_header(role="admin")
    response = client.post("/app/admin/api-keys/rotate", headers=headers, json={"service": ""})
    assert response.status_code == 422
