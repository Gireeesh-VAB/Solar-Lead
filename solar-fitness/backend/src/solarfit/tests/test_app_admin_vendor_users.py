"""Owner: karthik (App Platform & Foundation).

Tests for routers/app_admin_vendors.py's vendor-sub-user endpoints
(GET/POST /{vendor_id}/users, PATCH /{vendor_id}/users/{user_id}/status) —
same seeding pattern test_app_admin_vendors.py uses.
"""

import pytest
from fastapi.testclient import TestClient

from solarfit.db import get_session
from solarfit.main import app
from solarfit.repositories.vendors import VendorRow


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _vendor(db_session, **overrides) -> VendorRow:
    defaults = {
        "name": "Acme Surveys",
        "verification_status": "verified",
        "availability": True,
        "accuracy_score": 0.92,
        "service_area": {"region": "Telangana", "districts": ["Hyderabad"]},
        "payout_method_type": "UPI",
        "payout_masked_account": "acme@upi",
        "documents": ["license.pdf"],
    }
    defaults.update(overrides)
    row = VendorRow(**defaults)
    db_session.add(row)
    db_session.flush()
    return row


def test_list_users_requires_admin_role(client, make_auth_header, db_session):
    vendor = _vendor(db_session)
    r = client.get(f"/app/admin/vendors/{vendor.id}/users", headers=make_auth_header(role="vendor"))
    assert r.status_code == 403


def test_list_users_empty_for_new_vendor(client, make_auth_header, db_session):
    vendor = _vendor(db_session)
    r = client.get(f"/app/admin/vendors/{vendor.id}/users", headers=make_auth_header(role="admin"))
    assert r.status_code == 200
    assert r.json() == []


def test_create_user_then_appears_in_list(client, make_auth_header, db_session):
    vendor = _vendor(db_session)
    headers = make_auth_header(role="admin")

    r = client.post(
        f"/app/admin/vendors/{vendor.id}/users",
        headers=headers,
        json={"name": "Field Surveyor", "email": "surveyor@acme.example"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["loginEmail"] == "surveyor@acme.example"
    assert body["temporaryPassword"]
    assert body["user"]["status"] == "active"

    r = client.get(f"/app/admin/vendors/{vendor.id}/users", headers=headers)
    assert [u["email"] for u in r.json()] == ["surveyor@acme.example"]


def test_create_user_duplicate_email_is_409(client, make_auth_header, db_session):
    vendor = _vendor(db_session)
    headers = make_auth_header(role="admin")
    payload = {"name": "Field Surveyor", "email": "dup@acme.example"}

    r = client.post(f"/app/admin/vendors/{vendor.id}/users", headers=headers, json=payload)
    assert r.status_code == 201

    r = client.post(f"/app/admin/vendors/{vendor.id}/users", headers=headers, json=payload)
    assert r.status_code == 409


def test_create_user_unknown_vendor_is_404(client, make_auth_header):
    r = client.post(
        "/app/admin/vendors/00000000-0000-0000-0000-000000000000/users",
        headers=make_auth_header(role="admin"),
        json={"name": "Field Surveyor", "email": "new@acme.example"},
    )
    assert r.status_code == 404


def test_set_user_status_deactivates(client, make_auth_header, db_session):
    vendor = _vendor(db_session)
    headers = make_auth_header(role="admin")
    create = client.post(
        f"/app/admin/vendors/{vendor.id}/users",
        headers=headers,
        json={"name": "Field Surveyor", "email": "toggle@acme.example"},
    )
    user_id = create.json()["user"]["id"]

    r = client.patch(
        f"/app/admin/vendors/{vendor.id}/users/{user_id}/status",
        headers=headers,
        json={"status": "inactive"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "inactive"


def test_set_user_status_wrong_vendor_is_404(client, make_auth_header, db_session):
    vendor_a = _vendor(db_session, name="Vendor A")
    vendor_b = _vendor(db_session, name="Vendor B")
    headers = make_auth_header(role="admin")
    create = client.post(
        f"/app/admin/vendors/{vendor_a.id}/users",
        headers=headers,
        json={"name": "Field Surveyor", "email": "scoped@acme.example"},
    )
    user_id = create.json()["user"]["id"]

    r = client.patch(
        f"/app/admin/vendors/{vendor_b.id}/users/{user_id}/status",
        headers=headers,
        json={"status": "inactive"},
    )
    assert r.status_code == 404
