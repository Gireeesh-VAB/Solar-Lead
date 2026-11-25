"""Owner: Person 1 (Site & Geometry).

Turns Google Solar API's per-panel layout into map-ready polygons: four
real lat/lng corners per panel, ready to draw straight onto satellite
imagery.

Why the geometry lives here and not in the browser: rotating a rectangle
about a point on the earth is a projection problem, not a drawing one. A
naive "degrees per metre" fudge in JavaScript stretches panels as
latitude changes and shears them as azimuth changes. §17 of the spec is
explicit that planar maths never happens on EPSG:4326, so each building
gets its own local metre-based frame (the same azimuthal-equidistant
projection engine/projection.py's UTM helper exists to avoid guessing at)
and the corners come back as degrees only at the very end.

Everything drawn is real:

  * panel centres are Google's own solarPanels[].center lat/lng
  * panel size is Google's panelHeight/WidthMeters
  * per-panel orientation is Google's PORTRAIT/LANDSCAPE
  * rotation is the panel's own roof segment azimuth
  * count is however many Google returned — never padded, never trimmed

Nothing here fabricates, redistributes or evens out a layout. Absence of
data is reported as absence (status "no_layout"/"no_coverage"), never
filled in with a plausible arrangement.

DELIBERATELY NOT a capacity source. Google's panel count and P2's
recommended kWp are different numbers from different methods and they
disagree substantially — P2 derives capacity from usable area times a
density constant and has no layout at all. Callers must label this
"Google Solar layout" and leave P2's figure alone.
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Literal

from pyproj import Transformer

logger = logging.getLogger(__name__)

# Status values, in the same "absence is data, not an exception" style
# providers/vision.py already uses.
LayoutStatus = Literal["ok", "no_coverage", "no_layout", "error"]


@dataclass(frozen=True)
class PanelPolygon:
    """One panel as it should be drawn on a map."""

    corners: list[tuple[float, float]]  # 4 x (lng, lat), clockwise
    capacity_watts: float | None
    orientation: str
    segment_index: int | None
    azimuth_degrees: float | None
    pitch_degrees: float | None


@dataclass(frozen=True)
class PanelLayout:
    status: LayoutStatus
    panels: list[PanelPolygon] = field(default_factory=list)
    reason: str | None = None
    panel_capacity_watts: float | None = None

    @property
    def total_kwp(self) -> float:
        return sum((p.capacity_watts or 0.0) for p in self.panels) / 1000.0


def _local_frame(lat: float, lng: float) -> tuple[Transformer, Transformer]:
    """A metre-based frame centred on this building: x east, y north.

    Azimuthal-equidistant rather than UTM so a building sitting on a zone
    boundary is not split across two projections, and so the centre of
    the frame is always the building itself — distortion over a rooftop's
    few tens of metres is far below the width of a panel.
    """
    proj = f"+proj=aeqd +lat_0={lat} +lon_0={lng} +datum=WGS84 +units=m +no_defs"
    return (
        Transformer.from_crs("EPSG:4326", proj, always_xy=True),
        Transformer.from_crs(proj, "EPSG:4326", always_xy=True),
    )


def _panel_corners(
    centre_xy: tuple[float, float],
    panel_h: float,
    panel_w: float,
    azimuth_deg: float,
    pitch_deg: float,
    landscape: bool,
) -> list[tuple[float, float]]:
    """Four corners of one panel in the local metric frame.

    The map is looking straight down, so a panel lying on a pitched roof
    is foreshortened along the slope by cos(pitch) — negligible on the
    7-degree roof segment measured at the test site, but a 46-degree
    segment on the same building shrinks to 69% and would otherwise be
    drawn a third too long.
    """
    azimuth = math.radians(azimuth_deg)
    # Down-slope direction and its perpendicular, in (east, north).
    along = (math.sin(azimuth), math.cos(azimuth))
    across = (math.cos(azimuth), -math.sin(azimuth))

    # PORTRAIT runs the long side down the slope; LANDSCAPE runs it across.
    half_along = (panel_w if landscape else panel_h) / 2.0
    half_across = (panel_h if landscape else panel_w) / 2.0
    half_along *= math.cos(math.radians(pitch_deg))  # plan-view foreshortening

    cx, cy = centre_xy
    return [
        (
            cx + sa * half_along * along[0] + sc * half_across * across[0],
            cy + sa * half_along * along[1] + sc * half_across * across[1],
        )
        for sa, sc in ((1, -1), (1, 1), (-1, 1), (-1, -1))
    ]


def panel_layout_from_insights(building_insights: dict, lat: float, lng: float) -> PanelLayout:
    """Converts a buildingInsights response into drawable panel polygons.

    `building_insights` is whatever providers.vision.fetch_building_insights
    returned. An empty dict means the Solar API had no coverage at this
    location — reported as "no_coverage" rather than quietly producing an
    empty layout that looks like a successful call.
    """
    if not building_insights:
        return PanelLayout(
            status="no_coverage",
            reason="Solar API has no building data at this location",
        )

    potential = building_insights.get("solarPotential") or {}
    panels = potential.get("solarPanels") or []
    panel_h = potential.get("panelHeightMeters")
    panel_w = potential.get("panelWidthMeters")

    if not panels:
        return PanelLayout(
            status="no_layout", reason="Solar API returned no panel layout for this building"
        )
    if not panel_h or not panel_w:
        # Guessing a module size to salvage a layout would put fabricated
        # dimensions on a customer's roof.
        return PanelLayout(
            status="no_layout", reason="Solar API omitted panel dimensions for this building"
        )

    segments = potential.get("roofSegmentStats") or []
    capacity_watts = potential.get("panelCapacityWatts")
    to_local, to_wgs84 = _local_frame(lat, lng)

    drawn: list[PanelPolygon] = []
    for panel in panels:
        centre = panel.get("center") or {}
        p_lat, p_lng = centre.get("latitude"), centre.get("longitude")
        if p_lat is None or p_lng is None:
            continue

        index = panel.get("segmentIndex")
        segment = segments[index] if isinstance(index, int) and 0 <= index < len(segments) else {}
        azimuth = float(segment.get("azimuthDegrees") or 0.0)
        pitch = float(segment.get("pitchDegrees") or 0.0)
        orientation = panel.get("orientation") or "PORTRAIT"

        corners_xy = _panel_corners(
            to_local.transform(p_lng, p_lat),
            panel_h,
            panel_w,
            azimuth,
            pitch,
            landscape=orientation == "LANDSCAPE",
        )
        drawn.append(
            PanelPolygon(
                corners=[to_wgs84.transform(x, y) for x, y in corners_xy],
                capacity_watts=capacity_watts,
                orientation=orientation,
                segment_index=index if isinstance(index, int) else None,
                azimuth_degrees=azimuth,
                pitch_degrees=pitch,
            )
        )

    if not drawn:
        return PanelLayout(
            status="no_layout", reason="Solar API panel entries carried no usable coordinates"
        )

    logger.info("Panel layout at (%s, %s): %d panels", lat, lng, len(drawn))
    return PanelLayout(status="ok", panels=drawn, panel_capacity_watts=capacity_watts)


def fetch_panel_layout(lat: float, lng: float) -> PanelLayout:
    """The full path: Solar API call plus conversion to polygons.

    Never raises. A transport or quota failure is reported as "error"
    with the real reason logged — VIS-04's "absence never blocks the
    page" discipline. The caller keeps rendering the map and the
    analysis; only the overlay goes missing.
    """
    from solarfit.providers.vision import fetch_building_insights

    try:
        insights = fetch_building_insights(lat, lng)
    except Exception:
        logger.exception("Building Insights request failed at (%s, %s)", lat, lng)
        return PanelLayout(status="error", reason="Could not reach the Solar API")

    return panel_layout_from_insights(insights, lat, lng)
