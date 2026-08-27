"""Shared test fixtures. DB-backed fixtures (a transactional session
against the Postgres+PostGIS service) get added here once Person 1's
`sites` table and Person 3's `site_analysis_cache` table exist — Day 0
only needs the settings fixture below, since test_geometry.py and
test_projection.py exercise Shapely/pyproj directly with no DB.
"""

from datetime import datetime, timezone

import pytest

from solarfit.config import Settings
from solarfit.domain.site import Site


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None)


@pytest.fixture
def make_site():
    """Factory fixture for a fixture Site — used across Person 2's tests
    so no test depends on Person 1's real repositories/providers."""

    def _make(**overrides) -> Site:
        defaults = dict(
            id="site-1",
            site_type="ROOFTOP_RESIDENTIAL",
            name="Test Site",
            owner_org="Test Org",
            jurisdiction="TS",
            centroid={"type": "Point", "coordinates": [78.4867, 17.3850]},
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        defaults.update(overrides)
        return Site(**defaults)

    return _make
