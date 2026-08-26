"""STUB — Owner: Person 3 (AI Pipeline & Cache).

Implements the auto-apply/reversal half of §9.16 Obstacle Detection
(OBS-04..06) of Solar_Fitness_Engine_Development_Document_v1.2 — the
one stage in the whole pipeline that changes a customer-visible number
(usable_area_m2) without a human approval step, so it's held to a
stricter audit standard than VIS/VIZ/ML's purely-advisory pattern.

  OBS-04  Obstacles >= get_auto_apply_confidence_threshold() (read via
          solarfit.packs.config_pack, frozen Day 0) are unioned into the
          site's exclusions and trigger a NEW boundary version via
          Person 1's repositories.sites.new_boundary_version(), with
          source="obstacle_detection" recorded on that version — never
          a silent/untracked change. Then call Person 2's
          engine.area.compute_usable_area_m2() again against the
          updated exclusions.
  OBS-05  Obstacles below the threshold are stored as advisory-only
          annotations (Obstacle.applied stays False) — same discipline
          as VIS-03. Never auto-applied.
  OBS-06  Auto-applied obstacles must be independently reversible: an
          admin rejecting one supersedes that exclusion (SITE-05
          history is retained, never deleted) and triggers AREA-04
          recomputation back toward the prior value.

Depends on: solarfit.domain.assessment.Obstacle (frozen, Day 0),
solarfit.packs.config_pack.get_auto_apply_confidence_threshold (frozen
loader, Day 0), Person 1's repositories.sites (SITE-05 versioning —
reused, not reinvented), Person 2's engine.area (AREA-04 recompute —
already a pure function, no new interface needed).
"""

from solarfit.domain.assessment import Obstacle
from solarfit.domain.site import Site


def apply_or_flag(site: Site, obstacles: list[Obstacle]) -> list[Obstacle]:
    """OBS-04/05. Splits `obstacles` by get_auto_apply_confidence_threshold():
    at/above -> unions into exclusions, versions the site, recomputes
    usable area; below -> left advisory (Obstacle.applied stays False).
    Returns the same list with .applied set appropriately.
    Raises NotImplementedError until Person 3 implements it."""
    raise NotImplementedError


def reject_applied_obstacle(site_id: str, obstacle_id: str, actor: str) -> Site:
    """OBS-06. Supersedes a previously auto-applied obstacle's exclusion
    (SITE-05 history retained) and triggers AREA-04 recomputation.
    Raises NotImplementedError until Person 3 implements it."""
    raise NotImplementedError
