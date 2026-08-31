"""Owner: Person 3 (AI Pipeline & Cache).

Implements the auto-apply/reversal half of §9.16 Obstacle Detection
(OBS-04..06) of Solar_Fitness_Engine_Development_Document_v1.2 — the
one stage in the whole pipeline that changes a customer-visible number
(usable_area_m2) without a human approval step, so it's held to a
stricter audit standard than VIS/VIZ/ML's purely-advisory pattern.

Day 3 status: real. OBS-03's validation (providers.vision.validate_obstacle_polygon)
runs first, so only geometrically-plausible obstacles ever reach the
threshold split below — an invalid obstacle is dropped with a logged
reason, never silently kept as advisory (correcting this file's
original stub docstring, which claimed the input list came back
unchanged).

Day 4 wiring status: get_or_create_analysis() now calls apply_or_flag()
for real. Its auto-apply branch still depends on Person 1's
repositories.sites, which is a NotImplementedError stub today — rather
than let that crash the whole cache-miss pipeline, apply_or_flag()
catches NotImplementedError from that dependency and falls back to
advisory-only for the obstacles that would have auto-applied (logged,
not silent). Once Person 1 implements repositories/sites.py for real,
this fallback stops triggering and OBS-04 starts auto-applying for
real — no code change needed here.

  OBS-04  Valid obstacles >= get_auto_apply_confidence_threshold() (read
          via solarfit.packs.config_pack, frozen Day 0) are unioned into
          the site's exclusions and trigger ONE new boundary version for
          the whole batch via Person 1's
          repositories.sites.new_boundary_version(), with
          source="obstacle_detection" recorded on that version — never
          a silent/untracked change. Then call Person 1/2's
          engine.area.compute_usable_area_m2() again against the
          updated exclusions.
  OBS-05  Valid obstacles below the threshold are stored as
          advisory-only annotations (Obstacle.applied stays False) —
          same discipline as VIS-03. Never auto-applied.
  OBS-06  Auto-applied obstacles must be independently reversible: an
          admin rejecting one supersedes that exclusion (SITE-05
          history is retained, never deleted) and triggers AREA-04
          recomputation back toward the prior value.

Depends on: solarfit.domain.assessment.Obstacle (frozen, Day 0/3),
solarfit.packs.config_pack.get_auto_apply_confidence_threshold (frozen
loader, Day 0), solarfit.providers.vision.validate_obstacle_polygon
(OBS-03, Day 3), Person 1's repositories.sites (SITE-05 versioning,
still NotImplementedError — called for real via lazy import, mocked in
tests, same discipline as repositories/analysis_cache.py's stub
dependencies), Person 1/2's engine.area (AREA-04 recompute — same
lazy-import/mock treatment).
"""

import logging

from shapely.geometry import mapping, shape
from shapely.geometry.multipolygon import MultiPolygon
from shapely.ops import unary_union

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
    .applied set correctly."""
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

    if to_apply:
        geoms = [shape(o.bounding_polygon) for o in to_apply]
        if site.exclusions:
            geoms.append(shape(site.exclusions))
        union_geom = unary_union(geoms)
        if union_geom.geom_type == "Polygon":
            union_geom = MultiPolygon([union_geom])
        new_exclusions = mapping(union_geom)

        try:
            updated_site = sites_repo.new_boundary_version(
                site_id=site.id,
                boundary=site.boundary,
                actor="system:obstacle_detection",
                source="obstacle_detection",
                exclusions=new_exclusions,
                applied_obstacle_ids=[o.id for o in to_apply],
            )
            compute_usable_area_m2(updated_site)

            # VIZ-04: a real boundary-version change invalidates any
            # previously-cached panorama/vision-refinement for this
            # location so the next lookup regenerates instead of serving
            # a now-stale result. force_refresh() is a no-op if nothing
            # is cached yet — safe to call unconditionally.
            from solarfit.repositories.analysis_cache import force_refresh

            site_lng, site_lat = site.centroid["coordinates"]
            force_refresh(site_lat, site_lng)
        except NotImplementedError:
            # OBS-04's persistence layer (Person 1's repositories.sites)
            # isn't built yet — degrade to advisory-only rather than
            # crash the pipeline, same VIS-04/VIZ-03 discipline. Once
            # that lands, this branch stops triggering.
            logger.warning(
                "Auto-apply for site %s skipped: repositories.sites not yet implemented "
                "(%d obstacle(s) left advisory-only)",
                site.id,
                len(to_apply),
            )
            to_flag.extend(to_apply)
            to_apply = []

        for obstacle in to_apply:
            obstacle.applied = True

    for obstacle in to_flag:
        obstacle.applied = False

    return valid


def reject_applied_obstacle(site_id: str, obstacle_id: str, actor: str) -> Site:
    """OBS-06. Loads the site, finds the SITE-05 version that auto-applied
    this obstacle, subtracts that obstacle's polygon from the site's
    current exclusions, versions again with source="obstacle_rejection"
    (history retained, never deleted), and recomputes usable area.

    Unlike apply_or_flag(), this has no safe advisory-only fallback when
    repositories.sites isn't implemented yet — there's nothing to
    reverse when nothing was ever actually persisted. That's a
    deliberate asymmetry, not an oversight: the NotImplementedError is
    re-raised with a clearer message instead of being swallowed."""
    from solarfit.engine.area import compute_usable_area_m2
    from solarfit.repositories import sites as sites_repo

    try:
        site = sites_repo.get(site_id)
    except NotImplementedError as exc:
        raise NotImplementedError(
            "reject_applied_obstacle requires repositories.sites to be implemented "
            "(Person 1) — there is no safe advisory fallback for reversing a change "
            "that was never actually persisted."
        ) from exc

    if site is None:
        raise ValueError(f"Unknown site_id: {site_id}")

    version = sites_repo.find_version_applying_obstacle(site_id, obstacle_id)
    if version is None:
        raise ValueError(f"Obstacle {obstacle_id} was never auto-applied for site {site_id}")

    rejected_polygon = shape(version.applied_obstacle_polygon)
    current_exclusions = shape(site.exclusions) if site.exclusions else None
    new_exclusions = mapping(current_exclusions.difference(rejected_polygon)) if current_exclusions else None

    updated_site = sites_repo.new_boundary_version(
        site_id=site_id,
        boundary=site.boundary,
        actor=actor,
        source="obstacle_rejection",
        exclusions=new_exclusions,
    )
    compute_usable_area_m2(updated_site)
    return updated_site
