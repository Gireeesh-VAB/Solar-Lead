"""Shared test fixtures.

`db_session` runs each test inside a transaction that is rolled back
afterwards, so DB-backed tests never see each other's rows and the
Postgres+PostGIS service needs no reset between runs.

Person 4's own tables (usn_ocr_uploads, and calibration's tables) don't
need PostGIS and don't depend on anyone else's tables, so their tests
run against the sqlite_engine fixture below instead of requiring a live
Postgres — these tables have no geometry columns that would need
PostGIS specifically.
"""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from solarfit.config import Settings
from solarfit.db import get_engine
from solarfit.domain.constraint import CapacityResult, Ceiling, Gate
from solarfit.domain.site import Site


@pytest.fixture
def sqlite_engine():
    """A fresh in-memory SQLite database per test, single connection
    shared via StaticPool so multiple session checkouts within the same
    test see the same data (plain :memory: SQLite ties data to a single
    connection otherwise)."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    yield engine
    engine.dispose()


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None)


@pytest.fixture
def db_session() -> Iterator[Session]:
    """Transactional session — every test rolls back on exit.

    The session is bound to an already-open transaction, so repository
    code calling flush() (or even commit()) stays inside it and the outer
    rollback still undoes everything.
    """
    engine = get_engine()
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture(autouse=True)
def _allow_header_tenant(monkeypatch):
    """API-06 ships real API-key auth; the existing suite authenticates
    with the X-Owner-Org escape hatch, which is off by default. Turn it
    on for tests only — test_auth.py covers the real key path."""
    from solarfit.config import get_settings

    monkeypatch.setenv("ALLOW_HEADER_TENANT", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def make_site():
    """Factory fixture for a Site with sane, overridable defaults — used
    across Person 2/4's tests. All fields are the frozen domain/site.py
    contract, so no guesswork involved."""

    def _make(**overrides) -> Site:
        defaults = {
            "id": "site-1",
            "site_type": "ROOFTOP_RESIDENTIAL",
            "name": "Test Site",
            "owner_org": "Test Org",
            "jurisdiction": "AP",
            "centroid": {"type": "Point", "coordinates": [78.4867, 17.3850]},
            "boundary": None,
            "exclusions": None,
            "geometry_source": "solar_api",
            "imagery_date": datetime.now(UTC),
            "imagery_quality": "HIGH",
            "geometry_confidence": 0.9,
            "shading": None,
            "usn": None,
            "created_at": datetime.now(UTC),
        }
        defaults.update(overrides)
        return Site(**defaults)

    return _make


@pytest.fixture
def make_capacity():
    """Factory fixture for a CapacityResult with sane, overridable
    defaults."""

    def _make(**overrides) -> CapacityResult:
        defaults = {
            "recommended_kwp": 4.0,
            "max_technical_kwp": 6.0,
            "binding_constraint": "net_metering_cap",
            "headroom_kwp": 2.0,
            "ceilings": [
                Ceiling(
                    constraint="net_metering_cap",
                    ceiling_kwp=4.0,
                    reason="Net metering cap for residential",
                    confidence_delta=0.0,
                    kind="regulatory",
                    status="ok",
                ),
                Ceiling(
                    constraint="usable_area_ceiling",
                    ceiling_kwp=6.0,
                    reason="Usable roof area ceiling",
                    confidence_delta=0.0,
                    kind="physical",
                    status="ok",
                ),
            ],
            "unit_basis": "DC",
            "status": "ok",
        }
        defaults.update(overrides)
        return CapacityResult(**defaults)

    return _make


@pytest.fixture
def make_auth_header(db_session):
    """Factory fixture: `make_auth_header(role="customer", **overrides)`
    returns a real `{"Authorization": "Bearer ..."}` header for a
    freshly-created user — every /app/* endpoint's current_user()/
    require_role() gate needs this to test against. Creates a real
    UserRow against the same transactional db_session every other
    Postgres-backed test uses, so it rolls back with everything else.
    """
    import uuid

    from solarfit.auth_users import create_access_token, hash_password
    from solarfit.repositories import users as users_repo

    def _make(role: str = "customer", **overrides) -> dict[str, str]:
        defaults = {
            "email": f"test-{role}-{uuid.uuid4().hex[:8]}@example.com",
            "password_hash": hash_password("Test1234!"),
            "name": f"Test {role.title()}",
            "role": role,
        }
        if role == "customer":
            defaults["owner_org"] = "Test Org"
        defaults.update(overrides)
        row = users_repo.create_user(db_session, **defaults)
        token = create_access_token(str(row.id), row.role)
        return {"Authorization": f"Bearer {token}"}

    return _make


@pytest.fixture
def make_gate():
    """Factory fixture for a single Gate with sane, overridable
    defaults."""

    def _make(**overrides) -> Gate:
        defaults = {"gate": "structural_gate", "status": "PASS", "detail": "Structural review passed"}
        defaults.update(overrides)
        return Gate(**defaults)

    return _make
