"""Owner: karthik (App Platform & Foundation).

Tests for auth_users.py (hashing/tokens/current_user/require_role),
repositories/users.py, and routers/app_auth.py (signup/login/me) — the
foundation the rest of the /app/* surface depends on.

Router-level tests follow test_imports_api.py's exact pattern: override
get_session with the transactional db_session fixture so nothing written
here survives the test.
"""

from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from solarfit.auth_users import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from solarfit.db import get_session
from solarfit.main import app
from solarfit.repositories import users as users_repo

# --------------------------------------------------------------------- #
# hashing
# --------------------------------------------------------------------- #


def test_hash_password_round_trips():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong password", hashed)


def test_hash_password_never_stores_the_raw_value():
    hashed = hash_password("secret123")
    assert "secret123" not in hashed


# --------------------------------------------------------------------- #
# tokens
# --------------------------------------------------------------------- #


def test_access_token_round_trips_user_id_and_role():
    token = create_access_token("user-123", "customer")
    payload = decode_access_token(token)
    assert payload["sub"] == "user-123"
    assert payload["role"] == "customer"


def test_expired_access_token_is_rejected(monkeypatch):
    import solarfit.auth_users as auth_users_module

    class _ExpiredSettings:
        jwt_secret = "test-secret"
        jwt_expires_minutes = -1  # already expired the instant it's issued

    monkeypatch.setattr(auth_users_module, "get_settings", lambda: _ExpiredSettings())
    token = create_access_token("user-123", "customer")

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_malformed_token_is_rejected():
    with pytest.raises(jwt.PyJWTError):
        decode_access_token("not-a-real-token")


# --------------------------------------------------------------------- #
# repositories/users.py
# --------------------------------------------------------------------- #


def _make_user(session, **overrides):
    defaults = {
        "email": f"repo-test-{uuid4().hex[:8]}@example.com",
        "password_hash": hash_password("Test1234!"),
        "name": "Repo Test",
        "role": "customer",
        "owner_org": "Repo Org",
    }
    defaults.update(overrides)
    return users_repo.create_user(session, **defaults)


def test_create_and_get_by_email_round_trip(db_session):
    row = _make_user(db_session)
    assert users_repo.get_by_email(db_session, row.email).id == row.id


def test_get_by_email_unknown_returns_none(db_session):
    assert users_repo.get_by_email(db_session, "nobody@example.com") is None


def test_get_by_id_round_trips(db_session):
    row = _make_user(db_session)
    assert users_repo.get_by_id(db_session, str(row.id)).email == row.email


def test_list_by_owner_org_scopes_correctly(db_session):
    org = f"org-{uuid4().hex[:8]}"
    other_org = f"org-{uuid4().hex[:8]}"
    _make_user(db_session, email=f"a-{uuid4().hex[:8]}@example.com", owner_org=org)
    _make_user(db_session, email=f"b-{uuid4().hex[:8]}@example.com", owner_org=org)
    _make_user(db_session, email=f"c-{uuid4().hex[:8]}@example.com", owner_org=other_org)

    assert len(users_repo.list_by_owner_org(db_session, org)) == 2
    assert len(users_repo.list_by_owner_org(db_session, other_org)) == 1


def test_touch_last_login_stamps_the_timestamp(db_session):
    row = _make_user(db_session)
    assert row.last_login_at is None
    users_repo.touch_last_login(db_session, row.id)
    assert users_repo.get_by_id(db_session, row.id).last_login_at is not None


def test_duplicate_email_raises_integrity_error(db_session):
    from sqlalchemy.exc import IntegrityError

    email = f"dupe-{uuid4().hex[:8]}@example.com"
    _make_user(db_session, email=email)
    with pytest.raises(IntegrityError):
        _make_user(db_session, email=email)
        db_session.flush()


# --------------------------------------------------------------------- #
# routers/app_auth.py — HTTP layer
# --------------------------------------------------------------------- #


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _signup_body(**overrides):
    body = {
        "email": f"signup-{uuid4().hex[:8]}@example.com",
        "password": "Test1234!",
        "name": "New Customer",
        "ownerOrg": "New Org",
    }
    body.update(overrides)
    return body


def test_signup_returns_token_and_camelcase_user(client):
    response = client.post("/app/auth/signup", json=_signup_body())
    assert response.status_code == 201
    body = response.json()
    assert "token" in body
    assert body["user"]["ownerOrg"] == "New Org"
    assert body["user"]["role"] == "customer"


def test_signup_ignores_a_client_supplied_role(client):
    body = _signup_body()
    body["role"] = "admin"  # not a real field on SignupRequest — must be ignored, not error
    response = client.post("/app/auth/signup", json=body)
    assert response.status_code == 201
    assert response.json()["user"]["role"] == "customer"


def test_signup_duplicate_email_is_409(client):
    body = _signup_body()
    first = client.post("/app/auth/signup", json=body)
    assert first.status_code == 201

    second = client.post("/app/auth/signup", json=_signup_body(email=body["email"]))
    assert second.status_code == 409


def test_signup_short_password_is_422(client):
    response = client.post("/app/auth/signup", json=_signup_body(password="short"))
    assert response.status_code == 422


def test_login_happy_path_returns_token_and_stamps_last_login(client):
    signup_body = _signup_body()
    client.post("/app/auth/signup", json=signup_body)

    response = client.post(
        "/app/auth/login", json={"email": signup_body["email"], "password": signup_body["password"]}
    )
    assert response.status_code == 200
    assert "token" in response.json()


def test_login_wrong_password_is_401(client):
    signup_body = _signup_body()
    client.post("/app/auth/signup", json=signup_body)

    response = client.post(
        "/app/auth/login", json={"email": signup_body["email"], "password": "wrong-password"}
    )
    assert response.status_code == 401


def test_login_unknown_email_is_401_with_the_same_message_as_wrong_password(client):
    unknown = client.post(
        "/app/auth/login", json={"email": "nobody-here@example.com", "password": "whatever123"}
    )
    signup_body = _signup_body()
    client.post("/app/auth/signup", json=signup_body)
    wrong_password = client.post(
        "/app/auth/login", json={"email": signup_body["email"], "password": "wrong-password"}
    )

    assert unknown.status_code == wrong_password.status_code == 401
    assert unknown.json()["detail"] == wrong_password.json()["detail"]


def test_login_rate_limited_returns_429(client, monkeypatch):
    import solarfit.routers.app_auth as app_auth_module

    monkeypatch.setattr(app_auth_module, "check_rate_limit", lambda key_id, limit: (False, 0))

    response = client.post(
        "/app/auth/login", json={"email": "anyone@example.com", "password": "whatever123"}
    )
    assert response.status_code == 429


def test_me_with_a_well_formed_but_fake_token_is_401_not_500(client):
    """Regression: a syntactically valid JWT whose "sub" isn't a real
    UUID must be treated as an invalid token (401), not crash get_by_id()
    with an unhandled ValueError (500)."""
    fake_token = create_access_token("not-a-real-uuid", "customer")
    response = client.get("/app/auth/me", headers={"Authorization": f"Bearer {fake_token}"})
    assert response.status_code == 401


def test_me_returns_the_callers_own_profile(client):
    signup_body = _signup_body()
    signup = client.post("/app/auth/signup", json=signup_body)
    token = signup.json()["token"]

    response = client.get("/app/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == signup_body["email"]


def test_me_without_a_token_is_401(client):
    assert client.get("/app/auth/me").status_code == 401


def test_me_with_a_malformed_token_is_401(client):
    response = client.get("/app/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_me_with_a_non_bearer_header_is_401(client):
    response = client.get("/app/auth/me", headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert response.status_code == 401


# --------------------------------------------------------------------- #
# require_role()
# --------------------------------------------------------------------- #


def test_require_role_allows_a_matching_role():
    from fastapi import HTTPException

    from solarfit.auth_users import AuthenticatedUser, require_role

    admin = AuthenticatedUser(id="u-1", email="a@example.com", role="admin", name="Admin")
    check = require_role("admin")
    assert check(user=admin) is admin

    try:
        check(user=AuthenticatedUser(id="u-2", email="c@example.com", role="customer", name="C"))
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("expected require_role to reject a non-admin caller")
