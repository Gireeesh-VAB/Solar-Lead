"""Shared test fixtures. A transactional session against the real
Postgres+PostGIS service gets added here once Person 1's `sites` table
and Person 3's `site_analysis_cache` table exist for real —
test_geometry.py and test_projection.py exercise Shapely/pyproj
directly with no DB, and Person 4's fitness tests are pure-function
tests against the frozen domain contracts, also with no DB.

Person 4's own tables (usn_ocr_uploads, and calibration's tables once
built) don't need PostGIS and don't depend on anyone else's tables, so
their tests run against the sqlite_engine fixture below instead of
requiring a live Postgres — this docker-compose service isn't always
running locally, and these tables have no geometry columns that would
need PostGIS specifically.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from solarfit.config import Settings
from solarfit.domain.constraint import CapacityResult, Ceiling, Gate
from solarfit.domain.site import ShadingEstimate, Site


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
def make_site():
    """Factory fixture for a Site with sane, overridable defaults — used
    across Person 4's fitness/USN/assessment tests. All fields are the
    frozen domain/site.py contract, so no guesswork involved."""

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
            "shading": ShadingEstimate(
                sunshine_hours_per_year=2200.0,
                shading_score=0.85,
                source="solar_api",
            ),
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
def make_gate():
    """Factory fixture for a single Gate with sane, overridable
    defaults."""

    def _make(**overrides) -> Gate:
        defaults = {"gate": "structural_gate", "status": "PASS", "detail": "Structural review passed"}
        defaults.update(overrides)
        return Gate(**defaults)

    return _make
