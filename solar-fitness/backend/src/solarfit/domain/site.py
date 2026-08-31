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

GeometrySource = Literal["manual_polygon", "solar_api", "imported", "field_measured"]
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
    shading: ShadingEstimate | None = None  # SHADE-01/02

    usn: UsnCapture | None = None

    created_at: datetime
