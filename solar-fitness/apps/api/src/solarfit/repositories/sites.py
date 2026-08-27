"""STUB — Owner: Person 1 (Site & Geometry).

Implements SITE-05 (version boundary changes rather than overwriting;
retain full history with actor and timestamp) of
Solar_Fitness_Engine_Development_Document_v1.2, plus general
sites/site_versions CRUD.

First task: write the Alembic migration for the `sites` table
(id, site_type, name, owner_org, jurisdiction, centroid, boundary,
exclusions, geometry_source, imagery_date, imagery_quality,
geometry_confidence, created_at) and a `site_versions` history table —
see db/migrations/versions/0001_enable_postgis.py for the pattern
(0001 only enables the postgis/pgcrypto extensions; 0002 is Person 3's
site_analysis_cache — the sites/site_versions tables are yours to add
as 0003).

Day 3 addition (Person 3, obstacles.py): new_boundary_version() gained
`source`/`exclusions`/`applied_obstacle_ids` kwargs, and
find_version_applying_obstacle() was added, both still
NotImplementedError — engine/obstacles.py's OBS-04/06 calls these for
real via lazy import and mocks them in tests, same discipline as
repositories/analysis_cache.py's GEO/weather/VIZ/ML dependencies.
SiteVersionSource is deliberately separate from domain.site.py's frozen
GeometrySource: GeometrySource answers "how was this geometry first
obtained," SiteVersionSource answers "why did this version get
created" — different axes, so the frozen contract stays untouched.

Depends on: solarfit.domain.site.Site (frozen, Day 0).
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from solarfit.domain.site import Site

SiteVersionSource = Literal["manual_edit", "obstacle_detection", "obstacle_rejection"]


class SiteVersion(BaseModel):
    """SITE-05 history row. `applied_obstacle_ids` / `applied_obstacle_polygon`
    are only populated when source == "obstacle_detection" — OBS-06's
    reject_applied_obstacle() reads applied_obstacle_polygon back to
    subtract exactly this version's contribution from current exclusions."""

    id: str
    site_id: str
    boundary: dict
    exclusions: dict | None = None
    source: SiteVersionSource
    applied_obstacle_ids: list[str] = []
    applied_obstacle_polygon: dict | None = None
    actor: str
    created_at: datetime


def create(site: Site) -> Site:
    """Raises NotImplementedError until Person 1 implements it."""
    raise NotImplementedError


def get(site_id: str) -> Site | None:
    """Raises NotImplementedError until Person 1 implements it."""
    raise NotImplementedError


def new_boundary_version(
    site_id: str,
    boundary: dict,
    actor: str,
    source: SiteVersionSource = "manual_edit",
    exclusions: dict | None = None,
    applied_obstacle_ids: list[str] | None = None,
) -> Site:
    """SITE-05. Raises NotImplementedError until Person 1 implements it."""
    raise NotImplementedError


def find_version_applying_obstacle(site_id: str, obstacle_id: str) -> SiteVersion | None:
    """OBS-06 support: locate the site version that auto-applied a given
    obstacle, so reject_applied_obstacle() can subtract exactly its
    contribution from current exclusions. Raises NotImplementedError
    until Person 1 implements it."""
    raise NotImplementedError
