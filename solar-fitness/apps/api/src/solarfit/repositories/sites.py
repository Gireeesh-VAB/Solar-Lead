"""STUB — Owner: Person 1 (Site & Geometry).

Implements SITE-05 (version boundary changes rather than overwriting;
retain full history with actor and timestamp) of
Solar_Fitness_Engine_Development_Document_v1.1, plus general
sites/site_versions CRUD.

First task: write the Alembic migration for the `sites` table
(id, site_type, name, owner_org, jurisdiction, centroid, boundary,
exclusions, geometry_source, imagery_date, imagery_quality,
geometry_confidence, created_at) and a `site_versions` history table —
see db/migrations/versions/0001_enable_postgis.py for the pattern
(0001 only enables the postgis/pgcrypto extensions; the sites table is
yours to add as 0002).

Depends on: solarfit.domain.site.Site (frozen, Day 0).
"""

from solarfit.domain.site import Site


def create(site: Site) -> Site:
    """Raises NotImplementedError until Person 1 implements it."""
    raise NotImplementedError


def get(site_id: str) -> Site | None:
    """Raises NotImplementedError until Person 1 implements it."""
    raise NotImplementedError


def new_boundary_version(site_id: str, boundary: dict, actor: str) -> Site:
    """SITE-05. Raises NotImplementedError until Person 1 implements it."""
    raise NotImplementedError
