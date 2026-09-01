"""Owner: Person 3 (AI Pipeline & Cache).

Implements the auto-apply/reversal half of §9.16 Obstacle Detection
(OBS-04..06) of Solar_Fitness_Engine_Development_Document_v1.2 — the
one stage in the whole pipeline that changes a customer-visible number
(usable_area_m2) without a human approval step, so it's held to a
stricter audit standard than VIS/VIZ/ML's purely-advisory pattern.

Day 3 status: real. OBS-03's validation (providers.vision.validate_obstacle_polygon)
runs first, so only geometrically-plausible obstacles ever reach the
threshold split below — an invalid obstacle is dropped with a logged
reason, never silently kept as advisory.

Day 8 status (karthik + sameeksha merge): repositories.sites is real
now — Person 1's implementation, not a stub. Both functions below call
it for real via solarfit.db.session_scope(), matching her session-
passing convention (she owns the session, this module opens/closes it).
Her SiteVersionRow gained two new nullable JSONB columns for this merge
— applied_obstacle_ids / applied_obstacle_polygons — so OBS-06 can
identify and reverse exactly ONE obstacle out of a version that may
have auto-applied several at once; see repositories/sites.py's own
merge note for the schema-change details.

  OBS-04  Valid obstacles >= get_auto_apply_confidence_threshold() (read
          via solarfit.packs.config_pack, frozen Day 0) are unioned into
          the site's exclusions and trigger ONE new version for the
          whole batch via Person 1's
          repositories.sites.new_geometry_version(), with
          source="obstacle_detection" recorded on that version — never
          a silent/untracked change. Then call Person 1's
          engine.area.compute_usable_area_m2() again against the
          updated exclusions.
  OBS-05  Valid obstacles below the threshold are stored as
          advisory-only annotations (Obstacle.applied stays False) —
          same discipline as VIS-03. Never auto-applied.
  OBS-06  Auto-applied obstacles must be independently reversible: an
          admin rejecting one supersedes exactly that obstacle's
          contribution (SITE-05 history is retained, never deleted) and
          triggers AREA-04 recomputation back toward the prior value.

Depends on: solarfit.domain.assessment.Obstacle (frozen, Day 0/3),
solarfit.packs.config_pack.get_auto_apply_confidence_threshold (frozen
loader, Day 0), solarfit.providers.vision.validate_obstacle_polygon
(OBS-03, Day 3), Person 1's repositories.sites (SITE-05 versioning,
real), Person 1's engine.area (AREA-04 recompute, real).
"""

import logging

from shapely.geometry import mapping, shape
from shapely.geometry.multipolygon import MultiPolygon
from shapely.ops import unary_union

from solarfit.db import session_scope
from solarfit.domain.assessment import Obstacle
from solarfit.domain.site import Site

logger = logging.getLogger(__name__)


def apply_or_flag(site: Site, obstacles: list[Obstacle]) -> list[Obstacle]:
    """OBS-03/04/05. Validates each obstacle (dropping invalid ones with
    a logged reason), splits the survivors by
    get_auto_apply_confidence_threshold(), unions everything at/above
    threshold into site.exclusions as ONE new site version, and
    recomputes usable area once for the whole batch. Returns only the
    valid obstacles (dropped ones are logged, not returned), each with
    .applied set correctly.

    A DB failure during the auto-apply write degrades the would-have-
    applied obstacles to advisory-only (logged, not silent) rather than
    crashing the whole cache-miss pipeline — the same VIS-04/VIZ-03
    discipline used elsewhere for a genuine external-system hiccup, not
    a "dependency doesn't exist yet" excuse (repositories.sites is real
    now)."""
    from solarfit.engine.area import compute_usable_area_m2
    from solarfit.packs.config_pack import get_auto_apply_confidence_threshold
    from solarfit.providers.vision import validate_obstacle_polygon
    from solarfit.repositories import sites as sites_repo

    if site.boundary is None:
        for obstacle in obstacles:
            obstacle.applied = False
        return obstacles  # nothing to validate containment against — advisory only

    valid: list[Obstacle] = []
    for obstacle in obstacles:
        if validate_obstacle_polygon(obstacle, site.boundary):
            valid.append(obstacle)
        else:
            logger.info(
                "Dropping obstacle %s (%s) for site %s: failed OBS-03/GEO-07-08 checks",
                obstacle.id,
                obstacle.type,
                site.id,
            )

    threshold = get_auto_apply_confidence_threshold()
    to_apply = [o for o in valid if o.confidence >= threshold]
    to_flag = [o for o in valid if o.confidence < threshold]

    # Idempotency: the same cached vision detection (site_analysis_cache)
    # can be handed to this function again — on a repeat assessment call
    # for this site, or a different site reusing the same cached location
    # (CACHE-01/03) — so anything already reflected in this site's own
    # exclusions must be skipped here, never unioned in a second time.
    # Already-applied ones still report .applied = True below; they're
    # just not re-persisted.
    already_applied: set[str] = set()
    if to_apply:
        from solarfit.repositories.sites import applied_obstacle_ids

        with session_scope() as session:
            already_applied = applied_obstacle_ids(session, site.id)
        to_apply = [o for o in to_apply if o.id not in already_applied]

    if to_apply:
        geoms = [shape(o.bounding_polygon) for o in to_apply]
        if site.exclusions:
            geoms.append(shape(site.exclusions))
        union_geom = unary_union(geoms)
        if union_geom.geom_type == "Polygon":
            union_geom = MultiPolygon([union_geom])
        new_exclusions = mapping(union_geom)
        applied_obstacle_polygons = {o.id: o.bounding_polygon for o in to_apply}

        try:
            with session_scope() as session:
                sites_repo.new_geometry_version(
                    session,
                    site.id,
                    exclusions=new_exclusions,
                    actor="system:obstacle_detection",
                    source="obstacle_detection",
                    applied_obstacle_ids=[o.id for o in to_apply],
                    applied_obstacle_polygons=applied_obstacle_polygons,
                )
                updated_site = sites_repo.get(session, site.id)
                compute_usable_area_m2(updated_site)

            # VIZ-04: a real version change invalidates any previously-
            # cached panorama/vision-refinement for this location so the
            # next lookup regenerates instead of serving a stale result.
            # force_refresh() is a no-op if nothing is cached yet — safe
            # to call unconditionally.
            from solarfit.repositories.analysis_cache import force_refresh

            site_lng, site_lat = site.centroid["coordinates"]
            force_refresh(site_lat, site_lng)
        except Exception:
            logger.exception(
                "Auto-apply failed for site %s — %d obstacle(s) left advisory-only",
                site.id,
                len(to_apply),
            )
            to_flag.extend(to_apply)
            to_apply = []

        for obstacle in to_apply:
            obstacle.applied = True

    for obstacle in to_flag:
        obstacle.applied = False

    # Already-applied ones (filtered out of to_apply above, never
    # re-persisted) are genuinely applied — reflect that in the result
    # even though this call didn't write anything new for them.
    for obstacle in valid:
        if obstacle.id in already_applied:
            obstacle.applied = True

    return valid


def reject_applied_obstacle(site_id: str, obstacle_id: str, actor: str) -> Site:
    """OBS-06. Loads the site, finds the version whose applied_obstacle_ids
    contains this obstacle, subtracts exactly that obstacle's own
    polygon (not the whole version's batch) from the site's current
    exclusions, versions again with source="obstacle_rejected" (history
    retained, never deleted), and recomputes usable area."""
    from solarfit.engine.area import compute_usable_area_m2
    from solarfit.repositories import sites as sites_repo

    with session_scope() as session:
        site = sites_repo.get(session, site_id)
        if site is None:
            raise ValueError(f"Unknown site_id: {site_id}")

        version = next(
            (
                v
                for v in sites_repo.versions(session, site_id)
                if v.applied_obstacle_ids and obstacle_id in v.applied_obstacle_ids
            ),
            None,
        )
        if version is None or not (version.applied_obstacle_polygons or {}).get(obstacle_id):
            raise ValueError(f"Obstacle {obstacle_id} was never auto-applied for site {site_id}")

        rejected_polygon = shape(version.applied_obstacle_polygons[obstacle_id])
        current_exclusions = shape(site.exclusions) if site.exclusions else None
        new_exclusions = (
            mapping(current_exclusions.difference(rejected_polygon)) if current_exclusions else None
        )

        sites_repo.new_geometry_version(
            session,
            site_id,
            exclusions=new_exclusions,
            actor=actor,
            source="obstacle_rejected",
        )
        updated_site = sites_repo.get(session, site_id)
        compute_usable_area_m2(updated_site)

    return updated_site
