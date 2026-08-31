"""Owner: keerthana (Vendor domain, customer-account admin, jurisdictions).

Exercises the 5 /app/admin/customers/* endpoints. There is no tenant
table — `id` in every route IS the owner_org string, and every mutation
applies to every user sharing that owner_org (see
repositories/customer_accounts.py).
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from solarfit.auth_users import hash_password
from solarfit.db import get_session
from solarfit.main import app
from solarfit.repositories import users as users_repo


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def admin_header(make_auth_header):
    return make_auth_header(role="admin")


@pytest.fixture
def customer_org(db_session):
    """Two seats, with an explicit created_at gap: Postgres's now() is
    frozen for the whole transaction, so relying on server_default=now()
    to order two rows created in the same transaction (as these are)
    would tie — set it explicitly instead of trusting insert order."""
    org = "Acme Rooftops Pvt Ltd"
    earlier = datetime.now(UTC) - timedelta(days=30)
    later = datetime.now(UTC)
    users_repo.create_user(
        db_session,
        email="owner@acme.example.com",
        password_hash=hash_password("Test1234!"),
        name="Priya Owner",
        role="customer",
        owner_org=org,
        tier="growth",
        billing_contact_email="billing@acme.example.com",
        created_at=earlier,
    )
    users_repo.create_user(
        db_session,
        email="seat2@acme.example.com",
        password_hash=hash_password("Test1234!"),
        name="Second Seat",
        role="customer",
        owner_org=org,
        created_at=later,
    )
    return org


def test_requires_auth(client):
    r = client.get("/app/admin/customers")
    assert r.status_code == 401


def test_requires_admin_role(client, make_auth_header, customer_org):
    r = client.get("/app/admin/customers", headers=make_auth_header(role="customer"))
    assert r.status_code == 403


def test_list_customers(client, admin_header, customer_org):
    r = client.get("/app/admin/customers", headers=admin_header)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    tenant = body[0]
    assert tenant["id"] == customer_org
    assert tenant["name"] == customer_org
    assert tenant["tier"] == "growth"
    assert tenant["seatCount"] == 2
    assert tenant["billingContactEmail"] == "billing@acme.example.com"
    assert {u["email"] for u in tenant["users"]} == {"owner@acme.example.com", "seat2@acme.example.com"}
    # No assessments table exists yet — honest placeholders, not fabricated.
    assert tenant["sitesAssessedThisMonth"] == 0
    assert tenant["apiCallsThisMonth"] == 0


def test_list_customers_filters_by_tier(client, admin_header, customer_org):
    r = client.get("/app/admin/customers", params={"tier": "enterprise"}, headers=admin_header)
    assert r.status_code == 200
    assert r.json() == []


def test_get_customer(client, admin_header, customer_org):
    r = client.get(f"/app/admin/customers/{customer_org}", headers=admin_header)
    assert r.status_code == 200
    assert r.json()["id"] == customer_org


def test_get_unknown_customer_is_404(client, admin_header):
    r = client.get("/app/admin/customers/does-not-exist", headers=admin_header)
    assert r.status_code == 404


def test_update_tier_applies_to_every_seat(client, admin_header, customer_org):
    r = client.patch(f"/app/admin/customers/{customer_org}/tier", json={"tier": "enterprise"}, headers=admin_header)
    assert r.status_code == 200
    assert r.json()["tier"] == "enterprise"

    follow_up = client.get(f"/app/admin/customers/{customer_org}", headers=admin_header)
    assert follow_up.json()["tier"] == "enterprise"


def test_suspend_then_reinstate(client, admin_header, customer_org):
    suspended = client.post(f"/app/admin/customers/{customer_org}/suspend", headers=admin_header)
    assert suspended.status_code == 200
    assert suspended.json()["status"] == "suspended"

    reinstated = client.post(f"/app/admin/customers/{customer_org}/reinstate", headers=admin_header)
    assert reinstated.status_code == 200
    assert reinstated.json()["status"] == "active"
