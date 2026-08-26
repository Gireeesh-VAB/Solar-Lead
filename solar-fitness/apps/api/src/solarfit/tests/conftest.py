"""Shared test fixtures. DB-backed fixtures (a transactional session
against the Postgres+PostGIS service) get added here once Person 1's
`sites` table and Person 3's `site_analysis_cache` table exist — Day 0
only needs the settings fixture below, since test_geometry.py and
test_projection.py exercise Shapely/pyproj directly with no DB.
"""

import pytest

from solarfit.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None)
