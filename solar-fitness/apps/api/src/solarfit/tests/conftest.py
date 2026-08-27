"""Shared test fixtures.

`db_session` runs each test inside a transaction that is rolled back
afterwards, so DB-backed tests never see each other's rows and the
Postgres+PostGIS service needs no reset between runs.

Person 3's site_analysis_cache fixtures can hang off the same pattern.
"""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from solarfit.config import Settings
from solarfit.db import get_engine
from solarfit.domain.site import Site


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
    """Factory fixture for a fixture Site — used across Person 2's tests
    so no test depends on Person 1's real repositories/providers."""

    def _make(**overrides) -> Site:
        defaults = {
            "id": "site-1",
            "site_type": "ROOFTOP_RESIDENTIAL",
            "name": "Test Site",
            "owner_org": "Test Org",
            "jurisdiction": "TS",
            "centroid": {"type": "Point", "coordinates": [78.4867, 17.3850]},
            "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        }
        defaults.update(overrides)
        return Site(**defaults)

    return _make
