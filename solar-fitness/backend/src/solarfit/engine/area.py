"""Owner: Person 1 (Site & Geometry).

Implements §9.3 Usable Area (AREA-01..06) of
Solar_Fitness_Engine_Development_Document_v1.1:

  AREA-01  Boundary area via geography cast or projected CRS.
           NEVER planar area on EPSG:4326 (see §14 PostGIS Rules, §17).
  AREA-02  Total exclusion area — overlapping exclusions unioned, not summed.
  AREA-03  Configurable edge setback as a negative buffer in a projected CRS.
           Read edge_setback_m from solarfit.packs.config_pack.get_edge_setback_m().
  AREA-04  usable_area = boundary - setback - exclusions - type deductions.
  AREA-05  Utilisation factor by class where per-site precision is
           unavailable. Read via
           solarfit.packs.config_pack.get_utilisation_factor(site_type).
  AREA-06  Return zero, never negative, when setback consumes the boundary.

Pure functions — no database, no network. Everything operates on the
GeoJSON already carried by the Site contract, so this is unit-testable in
isolation and cheap to call again after an exclusions change (Person 3's
OBS-04 re-runs compute_usable_area_m2() once an obstacle auto-applies).

Ordering note (AREA-04): the setback is applied to the boundary FIRST,
then exclusions are subtracted from the result. Reversing that double-
counts any exclusion touching the roof edge — once as exclusion, once as
setback.

Depends on: solarfit.domain.site.Site (frozen, Day 0),
solarfit.packs.config_pack (frozen loader, Day 0),
solarfit.engine.projection (same track).
"""

from dataclasses import dataclass

from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shapely_transform
from shapely.ops import unary_union

from solarfit.domain.site import Site
from solarfit.engine.projection import WGS84_EPSG, to_metric
from solarfit.packs import config_pack

__all__ = [
    "UsableRoof",
    "boundary_area_m2",
    "compute_usable_area_m2",
    "compute_usable_roof",
    "exclusion_area_m2",
]


@dataclass(frozen=True)
class UsableRoof:
    """AREA-01..06's full result: the number AND the shape behind it.

    `polygon` is GeoJSON in EPSG:4326, matching how every other geometry
    crosses this codebase's boundaries (Site.boundary, Site.exclusions),
    so it serialises straight to the API and onto a map.

    `polygon_metric` is the same shape still in its projected CRS, kept
    because anything that MEASURES or PACKS must work in metres — §17 is
    explicit that planar work never happens on EPSG:4326. Re-projecting
    it back and forth would be both wasteful and a chance to reintroduce
    exactly that bug.

    Both are None when the setback or the exclusions consumed the roof
    entirely (AREA-06). That is a real, usable answer — zero usable area
    — and deliberately distinct from a site with no boundary at all,
    which raises.
    """

    area_m2: float
    polygon: dict | None
    polygon_metric: BaseGeometry | None
    epsg: int | None


def _to_wgs84_geojson(geom: BaseGeometry, epsg: int) -> dict:
    """Projected geometry -> GeoJSON in EPSG:4326, for the API and the map."""
    to_wgs84 = Transformer.from_crs(f"EPSG:{epsg}", f"EPSG:{WGS84_EPSG}", always_xy=True).transform
    return mapping(shapely_transform(to_wgs84, geom))


def _metric_geometries(site: Site) -> tuple[BaseGeometry, BaseGeometry | None, int]:
    """The site's boundary and unioned exclusions, both projected into the
    same metric CRS.

    The zone is chosen once from the boundary and reused for the
    exclusions — measuring the two in different projections would make
    the subtraction meaningless.

    Raises ValueError when the site has no boundary: a site whose geometry
    provider has not resolved one is INSUFFICIENT_DATA to the caller,
    which is a different thing from a usable area of zero (AREA-06).
    Never conflate the two.
    """
    if not site.boundary:
        raise ValueError(f"site {site.id} has no boundary — cannot compute usable area")

    boundary_4326 = shape(site.boundary)
    if boundary_4326.is_empty:
        raise ValueError(f"site {site.id} has an empty boundary geometry")

    boundary, epsg = to_metric(boundary_4326)

    if not site.exclusions:
        return boundary, None, epsg

    exclusions_4326 = shape(site.exclusions)
    if exclusions_4326.is_empty:
        return boundary, None, epsg

    # AREA-02 — unioned, never summed. Two obstacles that overlap on the
    # roof must not deduct their shared area twice.
    exclusions, _ = to_metric(exclusions_4326, epsg=epsg)
    return boundary, unary_union(exclusions), epsg


def boundary_area_m2(site: Site) -> float:
    """AREA-01. Boundary area in square metres, before any deduction.

    Measured in a projected CRS — never as planar area on EPSG:4326,
    where the coordinates are degrees and an 'area' is meaningless (§17).
    """
    boundary, _, _ = _metric_geometries(site)
    return float(boundary.area)


def exclusion_area_m2(site: Site) -> float:
    """AREA-02. Total excluded area in square metres, overlaps counted once."""
    boundary, exclusions, _ = _metric_geometries(site)
    if exclusions is None:
        return 0.0
    # Clipped to the boundary: an exclusion extending past the roof edge
    # cannot deduct area the roof never had. GEO-08 rejects such geometry
    # at ingest; this keeps the arithmetic honest regardless.
    return float(exclusions.intersection(boundary).area)


def compute_usable_roof(site: Site, params: dict | None = None) -> UsableRoof:
    """AREA-01..06, keeping the POLYGON as well as the number.

    Identical arithmetic to compute_usable_area_m2() below — this is the
    one implementation, and that function now delegates here. The only
    thing that changed is that `net`, the polygon the whole chain builds,
    is no longer dropped on the last line.

    That polygon is what a panel-layout algorithm has to be given. Handed
    only a float it can do nothing but assume a rectangle, which is how
    panels end up beside a building rather than on it.

    IMPORTANT for whoever packs panels into it: `polygon` is the roof
    AFTER setback and exclusions but BEFORE the utilisation factor.
    Utilisation (AREA-05) is a statistical stand-in for the walkways,
    row spacing and access gaps a real layout would place explicitly —
    so a packer must lay panels inside `polygon` and NOT also multiply by
    utilisation, or the same allowance is deducted twice.

        boundary -> project to a metric CRS
                 -> negative buffer by the edge setback   (AREA-03)
                 -> subtract unioned exclusions           (AREA-02, AREA-04)
                 -> measure                               (AREA-01)
                 -> multiply by the utilisation factor    (AREA-05)
                 -> clamp at zero                         (AREA-06)

    `params` overrides config-pack values for a single call — used by the
    tests, and by any future per-site precision superseding the by-class
    utilisation factor (AREA-05). Recognised keys: ``edge_setback_m``,
    ``utilisation_factor``.

    Raises ValueError when the site has no boundary (see _metric_geometries).
    """
    params = params or {}

    setback_m = params.get("edge_setback_m")
    if setback_m is None:
        setback_m = config_pack.get_edge_setback_m()
    setback_m = float(setback_m)
    if setback_m < 0:
        raise ValueError(f"edge_setback_m must not be negative, got {setback_m}")

    utilisation = params.get("utilisation_factor")
    if utilisation is None:
        # Deliberately unguarded: config_pack raises KeyError for an
        # unknown site_type rather than substituting a made-up number.
        utilisation = config_pack.get_utilisation_factor(site.site_type)
    utilisation = float(utilisation)

    boundary, exclusions, epsg = _metric_geometries(site)

    # AREA-03 — setback as a negative buffer, in metres, in a projected
    # CRS. Buffering coordinates still in degrees would be off by ~10^5.
    net = boundary.buffer(-setback_m) if setback_m else boundary

    # AREA-06 — a setback wider than the roof consumes it entirely.
    # Shapely returns an empty geometry rather than a negative area.
    if net.is_empty:
        return UsableRoof(area_m2=0.0, polygon=None, polygon_metric=None, epsg=epsg)

    # AREA-02 / AREA-04 — exclusions come off after the setback.
    if exclusions is not None:
        net = net.difference(exclusions)
        if net.is_empty:
            return UsableRoof(area_m2=0.0, polygon=None, polygon_metric=None, epsg=epsg)

    # AREA-01 / AREA-05
    usable = net.area * utilisation

    # AREA-06 — never negative, whatever the arithmetic did.
    return UsableRoof(
        area_m2=float(max(0.0, usable)),
        polygon=_to_wgs84_geojson(net, epsg),
        polygon_metric=net,
        epsg=epsg,
    )


def compute_usable_area_m2(site: Site, params: dict | None = None) -> float:
    """AREA-01..06. Usable roof area in square metres.

    Unchanged contract, unchanged number — every existing caller and test
    is unaffected. Kept as the narrow entry point because most callers
    genuinely only want the figure; compute_usable_roof() above is for the
    ones that need the shape too.
    """
    return compute_usable_roof(site, params).area_m2
