"""Independent re-check that a packed layout never escaped the roof.

engine/panel_packing.py::pack_panels() already guarantees full-footprint
containment via working.contains(candidate) at generation time — this
module does not change that guarantee, it audits it. Re-deriving the same
containment/intersection predicates against the packed footprints turns
"the packer is correct" from an assumption into a checked, reportable
number, and gives tests (and the API response) a real tripwire if the
packer's own logic ever regresses.
"""

from dataclasses import dataclass

from shapely.geometry.base import BaseGeometry

from solarfit.engine.panel_packing import PackedLayout


@dataclass(frozen=True)
class LayoutValidation:
    panel_count: int
    rejected_count: int
    panels_outside_roof: int
    panels_intersecting_obstacles: int

    @property
    def ok(self) -> bool:
        return self.panels_outside_roof == 0 and self.panels_intersecting_obstacles == 0


def validate_layout(
    layout: PackedLayout,
    usable_polygon_metric: BaseGeometry,
    exclusions_metric: BaseGeometry | None = None,
) -> LayoutValidation:
    """Re-checks every panel footprint in `layout` against the polygon it
    was supposedly packed into (and, optionally, a real exclusion
    geometry). Both counts should always come back zero for anything
    pack_panels() produced — that is the point of checking, not assuming.
    """
    panels_outside_roof = sum(
        1 for panel in layout.panels if not usable_polygon_metric.contains(panel.footprint)
    )
    panels_intersecting_obstacles = 0
    if exclusions_metric is not None and not exclusions_metric.is_empty:
        panels_intersecting_obstacles = sum(
            1 for panel in layout.panels if panel.footprint.intersects(exclusions_metric)
        )
    return LayoutValidation(
        panel_count=layout.count,
        rejected_count=layout.rejected_count,
        panels_outside_roof=panels_outside_roof,
        panels_intersecting_obstacles=panels_intersecting_obstacles,
    )


__all__ = ["LayoutValidation", "validate_layout"]
