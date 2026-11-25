"""Shared contract — built Day 0, frozen for the whole team.

Backs §9.1 Site Model (SITE-01..07), §9.15 USN Capture (USN-01..06), and
§9.17 Shading Analysis (SHADE-01..05) of
Solar_Fitness_Engine_Development_Document_v1.2.

Rooftop-only scope: FLOATING / GROUND_MOUNT / CANAL_TOP / CARPORT are
deliberately absent from RoofSiteType for now (floating/water-body work
is on hold) — add them back here first if that scope reopens.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

RoofSiteType = Literal["ROOFTOP_GOVT", "ROOFTOP_RESIDENTIAL", "ROOFTOP_CI"]

# Only ROOFTOP_RESIDENTIAL / ROOFTOP_CI are billing-linked (USN-05).
BILLING_LINKED_SITE_TYPES: tuple[RoofSiteType, ...] = (
    "ROOFTOP_RESIDENTIAL",
    "ROOFTOP_CI",
)

# "solar_api_mask" added alongside "solar_api": GEO-04's real-outline
# upgrade (providers/solar_api.py::extract_roof_polygon_from_mask) —
# a polygon vectorised from the Solar API's own building-mask raster,
# distinct from "solar_api"'s boundingBox rectangle. Additive only:
# every existing source is unchanged, and code that doesn't know about
# this one still treats it correctly via base.APPROXIMATE_SOURCES /
# base.PRECEDENCE (it deliberately is NOT in APPROXIMATE_SOURCES — it's
# a real traced-ish outline, not a rectangle).
GeometrySource = Literal[
    "manual_polygon", "solar_api", "solar_api_mask", "imported", "field_measured"
]
UsnSource = Literal["manual", "bill_ocr", "payment_proof_ocr"]
ShadingSource = Literal["solar_api", "unavailable"]


class UsnCapture(BaseModel):
    """USN-01..04. Three input paths converge on one usn + usn_source pair.

    Only ever populated for BILLING_LINKED_SITE_TYPES — SITE-02's JSON
    Schema must omit this field group entirely for every other site type.
    """

    usn: str | None = None
    usn_source: UsnSource | None = None


class ShadingEstimate(BaseModel):
    """SHADE-01/02. Populated by Person 1's providers/solar_api.py from
    fields the GEO-04 response already carries (per-segment sunshine
    hours / shading quantiles) — deliberately not a new external call or
    a custom shadow-casting model (see SHADE-05 for that future path).

    source == "unavailable" whenever geometry_source isn't "solar_api"
    (MANUAL_POLYGON/IMPORTED/FIELD_MEASURED carry no shading data) —
    SHADE-04 must read that as INSUFFICIENT_DATA for the shading
    sub-score, never assume zero or full shading.
    """

    sunshine_hours_per_year: float | None = None
    shading_score: float | None = None  # 0 (fully shaded) .. 1 (unobstructed), SHADE-02
    source: ShadingSource = "unavailable"


class Site(BaseModel):
    """SITE-01. GeoJSON is used for centroid/boundary/exclusions so the
    same shape serialises directly to/from the API and PostGIS via
    GeoAlchemy2's shape helpers.
    """

    id: str
    site_type: RoofSiteType
    name: str
    owner_org: str
    jurisdiction: str

    centroid: dict  # GeoJSON Point
    boundary: dict | None = None  # GeoJSON Polygon — None until a GEO provider resolves one
    exclusions: dict | None = None  # GeoJSON MultiPolygon

    geometry_source: GeometrySource | None = None
    imagery_date: datetime | None = None
    imagery_quality: str | None = None
    geometry_confidence: float | None = None  # GEO-09, 0..1
    # providers/solar_api.py::MaskVectorization.competing_regions, captured
    # once at site-creation time — how many OTHER candidate buildings the
    # mask found near the pin besides the one selected. None means no
    # mask lookup ran (not "found zero") — see repositories/sites.py's
    # own column comment for the full rationale.
    competing_buildings_nearby: int | None = None
    shading: ShadingEstimate | None = None  # SHADE-01/02

    usn: UsnCapture | None = None

    created_at: datetime
