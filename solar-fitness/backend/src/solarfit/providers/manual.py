"""Owner: Person 1 (Site & Geometry).

Implements GEO-02 (MANUAL_POLYGON) of
Solar_Fitness_Engine_Development_Document_v1.1: operator draws boundary
+ exclusions on satellite imagery, edits vertices after closure, emits
GeoJSON.

The drawing happens in the client; this provider is the server side of
it — it takes the emitted GeoJSON, validates it against GEO-07/08 and
normalises it into the internal Boundary shape. Deliberately the first
provider built: it needs no API key and no network, so the whole
create -> store -> compute_usable_area_m2 path is testable before
Google is involved at all.

Depends on: solarfit.providers.base (this person's own protocol),
solarfit.providers.validation (same track).
"""

from __future__ import annotations

from typing import ClassVar

from shapely.geometry import mapping, shape

from solarfit.domain.site import Site
from solarfit.providers import base, validation

__all__ = ["ManualPolygonProvider", "normalise_exclusions", "resolve_manual"]


class ManualPolygonProvider:
    """GEO-02. Boundary supplied directly by an operator as GeoJSON."""

    id = "manual_polygon"
    applies_to: ClassVar[list[str]] = []  # every rooftop type

    def resolve(self, site: Site, params: dict) -> dict:
        return resolve_manual(site, params)


def resolve_manual(site: Site, params: dict) -> dict:
    """GEO-02. Validate and normalise an operator-drawn boundary.

    `params["boundary"]` is the drawn polygon as GeoJSON. Returns the
    normalised Polygon; raises GeometryRejected (GEO-07) when the drawing
    is not a usable polygon — a self-intersecting trace, too few
    vertices, or one implausibly far from the site's centroid.
    """
    boundary = params.get("boundary")
    if not boundary:
        raise ValueError("manual_polygon provider requires params['boundary']")

    geom = validation.validate_boundary(boundary, centroid=site.centroid)
    return mapping(geom)


def normalise_exclusions(exclusions: object, boundary: dict) -> dict | None:
    """GEO-08. Accept a MultiPolygon, a single Polygon, or a list of
    either, and return one MultiPolygon contained within `boundary`.

    The client emits whatever the operator drew; the internal shape is
    always a MultiPolygon so engine/area.py never has to branch on it.
    """
    if not exclusions:
        return None

    parts: list[dict]
    if isinstance(exclusions, list):
        parts = list(exclusions)
    elif isinstance(exclusions, dict) and exclusions.get("type") == "MultiPolygon":
        parts = [
            {"type": "Polygon", "coordinates": coords}
            for coords in exclusions.get("coordinates", [])
        ]
    else:
        parts = [exclusions]  # type: ignore[list-item]

    if not parts:
        return None

    boundary_geom = shape(boundary)
    polygons = [validation.validate_exclusion(p, boundary_geom) for p in parts]
    return {
        "type": "MultiPolygon",
        "coordinates": [mapping(p)["coordinates"] for p in polygons],
    }


base.register(ManualPolygonProvider())
