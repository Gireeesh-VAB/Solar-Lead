"""Lays real solar panels inside the usable roof polygon.

Owner note: capacity is Person 2's slice (CON-07), and this changes how
it can be derived — see the warning at the bottom of this docstring.
The geometry is built here because engine/area.py's usable polygon is
Person 1's, and splitting the two across modules would mean re-deriving
the projection on the other side.

Why this exists
---------------
Capacity has been ``usable_area_m2 * 0.2 kWp/m2`` — an area times a
density constant. That answers "how much roof is there" but never "where
would the panels go", so nothing could draw a layout, and a roof with an
awkward shape scored the same as a clean rectangle of equal area.

This packs actual modules into the actual shape: rows running across the
slope, spaced so one row does not shade the next, with walkways every few
rows, and every panel required to lie wholly inside the usable polygon.

How the rows are laid
---------------------
Panels are packed on an axis-aligned grid in a frame ROTATED so that
"up-slope" points along +y. Doing it the other way — rotating each panel
in place on a north-aligned grid — leaves ragged, unusable slivers along
every edge that is not north-south, and no roof faces due north.

    rotate polygon by -azimuth  ->  pack axis-aligned  ->  rotate panels back

Row pitch is derived, not guessed: a row's shadow at winter-solstice noon
is ``panel_rise / tan(solar_altitude)``, with the altitude from the
site's own latitude. A flat array needs almost no gap; a steeply tilted
one at high latitude needs a lot. A configured floor keeps some airflow
either way.

WARNING for whoever wires this into capacity
--------------------------------------------
The polygon this receives is ALREADY post-setback and post-exclusion, and
is deliberately PRE-utilisation. AREA-05's utilisation factor is a
statistical stand-in for exactly the walkways and row spacing placed
explicitly here. Multiplying a packed count by it again deducts the same
allowance twice — assert_not_double_derated() below exists to make that
mistake loud rather than quiet.

Expect a packed count to come out BELOW ``usable_area_m2 * 0.2``: the
density constant assumes tidy wall-to-wall coverage, and a real layout
loses area to walkways, row gaps and edges that do not divide evenly.
That is a truer number, not a broken one.
"""

import logging
import math
from dataclasses import dataclass

from shapely.affinity import rotate
from shapely.geometry import Polygon, box
from shapely.geometry.base import BaseGeometry

from solarfit.packs import config_pack

logger = logging.getLogger(__name__)

# Earth's axial tilt. The sun is lowest at winter solstice noon, which is
# the worst case a row-spacing rule has to survive.
_AXIAL_TILT_DEG = 23.45

# Below this the sun never clears the horizon usefully and the shadow
# formula diverges; the configured floor takes over instead.
_MIN_SOLAR_ALTITUDE_DEG = 5.0


@dataclass(frozen=True)
class PackedPanel:
    """One module, in the same projected CRS as the polygon it was packed into."""

    footprint: Polygon
    watts: float
    row: int


@dataclass(frozen=True)
class PackedLayout:
    panels: list[PackedPanel]
    panel_watts: float
    tilt_deg: float
    azimuth_deg: float
    row_gap_m: float

    @property
    def count(self) -> int:
        return len(self.panels)

    @property
    def kwp(self) -> float:
        return self.count * self.panel_watts / 1000.0


def solar_noon_altitude_deg(latitude_deg: float) -> float:
    """Sun elevation at winter-solstice noon, the worst case for shading.

    Northern hemisphere: 90 - latitude - axial tilt. Mirrored for the
    south. Floored, because near the poles the formula goes negative and
    a negative altitude would produce an infinite row gap.
    """
    altitude = 90.0 - abs(latitude_deg) - _AXIAL_TILT_DEG
    return max(altitude, _MIN_SOLAR_ALTITUDE_DEG)


def row_gap_m(panel_length_m: float, tilt_deg: float, latitude_deg: float, floor_m: float) -> float:
    """Clear ground a row needs behind it so it does not shade the next.

    The rear edge of a tilted panel stands ``length * sin(tilt)`` above
    the roof, and that height casts ``rise / tan(altitude)`` of shadow at
    the worst moment of the year. A flat panel casts none, which is why
    the configured floor matters — rows still need airflow and access.
    """
    rise = panel_length_m * math.sin(math.radians(tilt_deg))
    shadow = rise / math.tan(math.radians(solar_noon_altitude_deg(latitude_deg)))
    return max(shadow, floor_m)


def assert_not_double_derated(packed_kwp: float, utilisation_factor: float) -> None:
    """Guard the one mistake that silently halves a customer's system.

    A packed layout has already paid for its walkways and row gaps in
    geometry. Applying AREA-05's utilisation factor on top charges for
    them twice. This raises rather than warns: a quietly undersized
    system looks perfectly plausible on a result page.
    """
    if not 0 < utilisation_factor <= 1:
        raise ValueError(f"utilisation_factor out of range: {utilisation_factor}")
    if utilisation_factor < 1:
        raise ValueError(
            "packed capacity must not be multiplied by the utilisation factor — "
            "the packer already placed the walkways and row spacing that factor "
            f"stands in for (would have turned {packed_kwp:.2f} kWp into "
            f"{packed_kwp * utilisation_factor:.2f} kWp)"
        )


def pack_panels(
    usable_polygon_metric: BaseGeometry,
    *,
    latitude_deg: float,
    tilt_deg: float | None = None,
    azimuth_deg: float | None = None,
    panel_length_m: float | None = None,
    panel_width_m: float | None = None,
    panel_watts: float | None = None,
    params: dict | None = None,
) -> PackedLayout:
    """Fill `usable_polygon_metric` with panels.

    The polygon must be in a PROJECTED CRS — metres, not degrees (§17).
    engine/area.py's ``UsableRoof.polygon_metric`` is exactly that, and is
    the intended input.

    `tilt_deg`/`azimuth_deg` come from the roof segment when known; the
    config-pack defaults are used only when the roof does not say.
    Everything else falls back to the pack, but the Solar API's own panel
    dimensions and wattage are preferred when the caller has them.
    """
    settings = {**config_pack.get_panel_packing_params(), **(params or {})}

    length = float(panel_length_m or settings["panel_length_m"])
    width = float(panel_width_m or settings["panel_width_m"])
    watts = float(panel_watts or settings["panel_watts"])
    tilt = float(settings["default_tilt_deg"] if tilt_deg is None else tilt_deg)
    azimuth = float(settings["default_azimuth_deg"] if azimuth_deg is None else azimuth_deg)

    if usable_polygon_metric is None or usable_polygon_metric.is_empty:
        return PackedLayout([], watts, tilt, azimuth, 0.0)

    # PORTRAIT runs the long side up the slope, which is the direction
    # rows advance in. LANDSCAPE turns each module a quarter turn.
    portrait = str(settings["orientation"]).lower() != "landscape"
    along = length if portrait else width  # up-slope, the shaded direction
    across = width if portrait else length  # along the row

    gap = row_gap_m(along, tilt, latitude_deg, float(settings["min_row_gap_m"]))
    # A tilted panel occupies less ground than its length — the row pitch
    # is the FOOTPRINT plus the shadow gap, not the panel plus the gap.
    row_pitch = along * math.cos(math.radians(tilt)) + gap
    col_pitch = across + float(settings["panel_gap_m"])
    path_width = float(settings["maintenance_path_m"])
    rows_between_paths = int(settings["rows_between_paths"])

    # Pack in a frame where up-slope is +y, then rotate the result back.
    origin = usable_polygon_metric.centroid
    working = rotate(usable_polygon_metric, -azimuth, origin=origin, use_radians=False)
    min_x, min_y, max_x, max_y = working.bounds

    panels: list[PackedPanel] = []
    y = min_y
    row_index = 0
    while y + along * math.cos(math.radians(tilt)) <= max_y:
        row_height = along * math.cos(math.radians(tilt))
        x = min_x
        placed_in_row = 0
        while x + across <= max_x:
            candidate = box(x, y, x + across, y + row_height)
            # contains(), not intersects(): a panel hanging over the roof
            # edge or into an exclusion cannot be installed there.
            if working.contains(candidate):
                panels.append(
                    PackedPanel(
                        footprint=rotate(candidate, azimuth, origin=origin, use_radians=False),
                        watts=watts,
                        row=row_index,
                    )
                )
                placed_in_row += 1
            x += col_pitch

        if placed_in_row:
            row_index += 1
        # A maintenance path every few rows, wide enough to carry a panel.
        extra = (
            path_width
            if rows_between_paths > 0 and row_index > 0 and row_index % rows_between_paths == 0
            else 0.0
        )
        y += row_pitch + extra

    logger.info(
        "Packed %d panels (%.2f kWp) into %.1f m2 at tilt %.1f / azimuth %.1f, row gap %.2f m",
        len(panels),
        len(panels) * watts / 1000.0,
        usable_polygon_metric.area,
        tilt,
        azimuth,
        gap,
    )
    return PackedLayout(panels, watts, tilt, azimuth, gap)


def to_wgs84_rings(layout: PackedLayout, epsg: int) -> list[list[tuple[float, float]]]:
    """Packed panels -> (lng, lat) rings, ready to draw on a map.

    Mirrors engine/panel_layout.py's output shape so the same overlay can
    render a packed layout and Google's, without the frontend caring
    which produced it.
    """
    from pyproj import Transformer
    from shapely.ops import transform as shapely_transform

    to_wgs84 = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True).transform
    return [
        list(shapely_transform(to_wgs84, panel.footprint).exterior.coords)[:4]
        for panel in layout.panels
    ]


__all__ = [
    "PackedLayout",
    "PackedPanel",
    "assert_not_double_derated",
    "pack_panels",
    "row_gap_m",
    "solar_noon_altitude_deg",
    "to_wgs84_rings",
]
