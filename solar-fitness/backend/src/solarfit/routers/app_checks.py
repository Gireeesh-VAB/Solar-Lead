"""Owner: karthik (App Platform & Foundation).

The consumer self-service "checks" portal — closes a real gap found
during a frontend/backend sync audit: listChecks/getCheck/createCheck/
completeCheck/getCustomerProfile/updateCustomerProfile (6 functions)
had no backend at all.

Design decision, flagged not silently guessed at: lib/fixtures/
customer.ts's own comment already states "a 'check' is the same shape
as a Site with a latestAssessment... this simply exposes that model
through a simpler, homeowner-facing set of endpoints." So this reuses
routers/sites.py::create_site_core() and routers/assessments.py::
orchestrate_assessment() unchanged rather than a new domain model.

The one real wrinkle: app_sites.py's whole surface is owner_org-scoped,
and an individual signing up without a company name (the normal
consumer-check path) gets owner_org=None (see app_auth.py's signup
flow) — app_sites.py 403s/empties without one. Resolution: checks are
scoped by a synthetic owner_org derived from the user's own id
(f"individual:{user.id}"), passed to the *same* create_site_core/
list_sites/orchestrate_assessment functions everyone else uses — no
schema change, no new table, every existing validation/versioning/
assessment path runs unchanged. completeCheck calls the real engine via
orchestrate_assessment(), replacing the frontend mock's fabricated
random verdict with a genuine run.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import Field
from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.geometry.multipolygon import MultiPolygon
from shapely.ops import unary_union
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from solarfit.auth_users import AuthenticatedUser, current_user
from solarfit.config import get_settings
from solarfit.db import get_session
from solarfit.domain.assessment import Obstacle, ObstacleType
from solarfit.domain.site import RoofSiteType
from solarfit.engine.panorama import build_scene_geometry
from solarfit.engine.projection import WGS84_EPSG, utm_epsg_for
from solarfit.packs import config_pack
from solarfit.providers import manual, solar_api, usn_ocr
from solarfit.providers.validation import GeometryRejected, geometry_confidence
from solarfit.providers.vision import validate_obstacle_polygon
from solarfit.repositories import assessments as assessments_repo
from solarfit.repositories import audit as audit_repo
from solarfit.repositories import installations as installations_repo
from solarfit.repositories import notifications as notifications_repo
from solarfit.repositories import sites as repo
from solarfit.repositories import users as users_repo
from solarfit.repositories import vendor_reviews as vendor_reviews_repo
from solarfit.repositories import vendors as vendors_repo
from solarfit.routers.app_sites import SiteOut, _CamelModel, _site_out
from solarfit.routers.common import IndianMobile, actor_audit_fields, request_audit_meta
from solarfit.routers.installations_common import (
    CommissioningRecordOut,
    commissioning_out,
)
from solarfit.routers.sites import SiteCreate, create_site_core
from solarfit.workers.celery_app import celery_app
from solarfit.workers.tasks_assessments import run_check_assessment_task

router = APIRouter(prefix="/app", tags=["app-checks"])

_DEFAULT_JURISDICTION = "IN-TG"  # same rationale as app_sites.py's own constant — no jurisdiction field on this form either
_INDIVIDUAL_OWNER_ORG_PREFIX = "individual:"


def _individual_owner_org(user: AuthenticatedUser) -> str:
    return f"{_INDIVIDUAL_OWNER_ORG_PREFIX}{user.id}"


# --------------------------------------------------------------------- #
# schemas
# --------------------------------------------------------------------- #


RoofType = Literal[
    "RCC_CONCRETE", "METAL_SHEET", "GI_SHEET", "TILED", "ASBESTOS_SHEET", "GROUND_MOUNTED", "TERRACE", "OTHER"
]
RoofMaterial = Literal["RCC", "CONCRETE", "METAL", "TILE", "SHEET", "OTHER"]
RoofSlope = Literal["FLAT", "LOW", "MEDIUM", "HIGH"]
ConnectionType = Literal["SINGLE_PHASE", "THREE_PHASE"]


class MonthlyConsumptionEntry(_CamelModel):
    month: str = Field(min_length=1, max_length=16)  # "2026-01"
    units_kwh: float = Field(ge=0)


class PanelCornerOut(_CamelModel):
    lat: float
    lng: float


class MapMetadata(_CamelModel):
    zoom: int
    map_type_id: str = "satellite"
    clicked_lat: float
    clicked_lng: float
    # StartCheckWizard's Crop vs Freehand building-selection tool — purely
    # descriptive provenance for the confirmation panel/audit trail, not
    # read by anything downstream. Optional/additive: older clients that
    # don't send it just don't get the field.
    selection_method: Literal["crop", "freehand"] | None = None


class NewCheckInput(_CamelModel):
    # max_length matches SiteCreate.name below, which create_check() builds
    # from this field — an over-length address used to reach that internal
    # model unvalidated and raise an uncaught pydantic ValidationError deep
    # inside the handler (500), instead of a clean 422 at the API boundary.
    address: str = Field(min_length=1, max_length=255)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    site_type: RoofSiteType = "ROOFTOP_RESIDENTIAL"
    # CON-05 input. Optional: a check without a bill still runs, and the
    # consumption-offset ceiling reports insufficient_data exactly as it
    # does today — the system is then sized by roof area alone.
    monthly_bill_low_inr: float | None = Field(default=None, gt=0)
    monthly_bill_high_inr: float | None = Field(default=None, gt=0)
    # FIN-03 input — the PRIMARY consumption figures for seasonal
    # estimation/sizing when the customer knows their units (kWh), not
    # just their bill amount. Optional and independent of the ₹ pair
    # above: either or both may be given, and engine/seasonal_consumption.py
    # prefers these over converting the ₹ pair via a flat tariff.
    highest_consumption_kwh: float | None = Field(default=None, gt=0)
    lowest_consumption_kwh: float | None = Field(default=None, gt=0)

    # Roof Information (customer self-report at intake) — a rough
    # description is enough to shape the initial feasibility check; the
    # vendor's own in-person structural assessment is the source of
    # truth once a survey happens, not these. All optional: a customer
    # who doesn't know their roof material shouldn't be blocked from
    # running a check.
    roof_type: RoofType | None = None
    roof_material: RoofMaterial | None = None
    roof_slope: RoofSlope | None = None
    roof_construction_year: int | None = Field(default=None, ge=1900, le=2100)

    # Electrical Information + Electricity Consumption (customer
    # self-report, everything on this section is on the customer's own
    # bill) — the vendor's own in-person electrical inspection (meter/DB
    # photos, earthing, lightning protection) is a separate, later
    # capture on the vendor_jobs row, not here.
    electricity_board: str | None = None
    consumer_number: str | None = None
    # USN-01 (§9.15), captured at intake instead of only post-analysis on
    # the result page (see UsnCaptureFlow.tsx's own OCR-based path there
    # for anyone who'd rather scan a bill than type this). Validated with
    # the same providers/usn_ocr.py::capture_manual() the confirm-later
    # path uses, not a re-implementation of that rule — see create_check().
    usn: str | None = Field(default=None, min_length=1, max_length=64)
    connection_type: ConnectionType | None = None
    sanctioned_load_kw: float | None = Field(default=None, ge=0)
    contract_demand_kva: float | None = Field(default=None, ge=0)
    connected_load_kw: float | None = Field(default=None, ge=0)
    monthly_consumption_kwh: list[MonthlyConsumptionEntry] = Field(default_factory=list)

    # Battery Requirement (spec section 14) — customer's own interest/
    # need. The vendor's own physical assessment (room/location/
    # ventilation/fire safety) is a separate, later capture on the
    # vendor_jobs row, not here.
    battery_required: bool | None = None
    backup_required: bool | None = None
    required_backup_hours: float | None = Field(default=None, ge=0)
    critical_loads: str | None = None

    # Map-driven building selection/crop (StartCheckWizard) — optional,
    # additive. A customer who confirmed a rooftop polygon on the
    # full-screen map sends it here so the check is created with its
    # final geometry already in place, atomically, rather than the
    # rectangle-then-PUT-boundary two-call sequence save_check_boundary
    # exists for. See create_check()'s use of _apply_manual_boundary.
    confirmed_boundary: list[PanelCornerOut] | None = Field(default=None, min_length=3)
    map_metadata: MapMetadata | None = None


class CustomerProfileOut(_CamelModel):
    name: str
    email: str
    phone: str | None
    notify_on_complete: bool


class CustomerProfileUpdate(_CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    phone: IndianMobile = None
    notify_on_complete: bool | None = None


def _profile_out(row: users_repo.UserRow) -> CustomerProfileOut:
    return CustomerProfileOut(
        name=row.name, email=row.email, phone=row.phone, notify_on_complete=row.notify_on_complete
    )


def _owned_check_or_404(session: Session, check_id: str, owner_org: str):
    try:
        site = repo.get(session, check_id)
    except ValueError as exc:  # malformed UUID
        raise HTTPException(status.HTTP_404_NOT_FOUND, "check not found") from exc
    if site is None or site.owner_org != owner_org:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "check not found")
    row = session.get(repo.SiteRow, uuid.UUID(site.id))
    return site, row


def _readable_check_or_404(session: Session, check_id: str, user: AuthenticatedUser):
    """Like _owned_check_or_404, but also lets an admin read ANY check's
    read-only detail — the same "admin can read any site" precedent
    routers/app_sites.py::get_site() already established (its own
    docstring: "matches every other admin-scoped GET in this codebase"),
    which this router's own endpoints hadn't actually picked up yet.

    Exists so the admin assessment-review page's "Feasibility" button
    can open the exact same customer result page a customer sees —
    without this, GET /checks/{id} (and the solar-layout/scene/
    obstacles/financial-projection detail it pulls in) 404s for an
    admin even though GET /sites/{id} already worked, silently breaking
    most of that page for an admin viewer.

    Deliberately NOT used by any endpoint that MUTATES a customer's
    site (USN capture, boundary edits, profile, enquiry) — those stay
    customer-only; widening a read is a much smaller, safer step than
    widening a write, and nothing here asked for the latter.
    """
    try:
        site = repo.get(session, check_id)
    except ValueError as exc:  # malformed UUID
        raise HTTPException(status.HTTP_404_NOT_FOUND, "check not found") from exc
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "check not found")
    if user.role != "admin" and site.owner_org != _individual_owner_org(user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "check not found")
    row = session.get(repo.SiteRow, uuid.UUID(site.id))
    return site, row


# --------------------------------------------------------------------- #
# checks
# --------------------------------------------------------------------- #


@router.get("/checks", response_model=list[SiteOut])
def list_checks(
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> list[SiteOut]:
    owner_org = _individual_owner_org(user)
    sites = repo.list_sites(session, owner_org=owner_org)
    out = [_site_out(session, s, session.get(repo.SiteRow, uuid.UUID(s.id))) for s in sites]
    # Newest first — matches lib/api/client.ts's listChecks() own sort.
    out.sort(key=lambda o: o.created_at, reverse=True)
    return out


class RoofPitchOut(_CamelModel):
    """The real, measured plane of whichever roof segment the resolved
    point lands on — solarfit.providers.solar_api.roof_pitch_at_point(),
    never a fabricated/estimated figure. Physical roof slope, NOT the
    map camera's tilt/pitch, which this app never conflates with it."""

    segment_index: int
    pitch_deg: float
    azimuth_deg: float
    orientation: str
    plane_height_m: float | None
    area_m2: float | None
    ground_area_m2: float | None
    segment_count: int
    matched_by: Literal["contains", "tolerated_contains", "nearest"]
    confidence: Literal["high", "medium", "low"]


class ResolveBuildingOut(_CamelModel):
    """Click-to-locate (StartCheckWizard step 2). Re-runs the same GEO-04
    resolution routers/sites.py::create_site_core does at site-creation
    time, but standalone and pre-creation — no check/Site exists yet at
    click time.

    Building Insights has no stable building/place id, so a resolved
    building is identified by (centroid, source) rather than an
    invented id that would imply a stability Google doesn't provide.

    Registered before the `/checks/{check_id}` route below: FastAPI
    matches routes in registration order and {check_id} is a plain
    string path param, so "resolve-building" would otherwise be
    swallowed by get_check() as if it were a check id.
    """

    status: Literal["ok", "no_coverage", "error"]
    boundary: list[PanelCornerOut] | None = None
    centroid: PanelCornerOut | None = None
    area_m2: float | None = None
    source: Literal["solar_api_mask", "solar_api"] | None = None
    imagery_quality: str | None = None
    # Surfaced so the "Adjust boundary" step can warn the customer when
    # detection ran on old/lower-tier imagery — the auto-detected shape
    # is never pixel-perfect (it's traced from a DIFFERENT Google
    # imagery capture than the satellite tile the customer taps
    # against, see solar_api.py module docstring), and this is the one
    # concrete signal already available for how much to trust it.
    imagery_date: str | None = None
    competing_buildings_nearby: int | None = None
    detail: str | None = None
    # None whenever no roof segment has both a pitch and an azimuth to
    # report (sparse data, no coverage) — the frontend must show "pitch
    # unavailable", never invent a number to fill the gap.
    roof_pitch: RoofPitchOut | None = None


@router.get("/checks/resolve-building", response_model=ResolveBuildingOut)
def resolve_building_at_point(
    lat: float,
    lng: float,
    _user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> ResolveBuildingOut:
    """Click-to-locate: given a point the customer clicked on the
    satellite map, resolve the building at (or nearest) that point.

    No check/site exists yet at this point in the flow, so this is
    `current_user`-only auth (no `_owned_check_or_404`) — same pattern
    as this module's other non-check-scoped routes (`/customer/profile`).

    Prefers the vectorised building-mask polygon (a real traced outline)
    over the bounding-box rectangle when the mask extraction succeeds,
    mirroring routers/sites.py::create_site_core's own rectangle-then-
    mask-upgrade sequence — never raises for "no building here", only
    for a genuine failure to even ask (missing API key, malformed
    request).
    """
    try:
        result = solar_api.resolve_for_location(lat, lng)
    except solar_api.SolarApiError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    if not result.usable:
        return ResolveBuildingOut(
            status="no_coverage" if result.status == "no_coverage" else "error",
            detail=result.detail,
        )

    boundary = result.boundary
    source: Literal["solar_api_mask", "solar_api"] = "solar_api"
    mask_result = solar_api.extract_roof_polygon_from_mask(lat, lng)
    competing_buildings_nearby = mask_result.competing_regions
    if mask_result.polygon is not None:
        # In a dense block, _select_building_region() picks whichever
        # mask region is nearest the click — independent of, and not
        # cross-checked against, Building Insights' own building match.
        # Only trust the mask's pick when it's close enough to agree
        # with Building Insights' answer; otherwise a customer's
        # correctly-drawn crop can silently get a NEIGHBOUR's real-but-
        # wrong outline instead of their own building's coarser (but
        # correctly-located) rectangle. Reuses the same max_pin_distance_m
        # tolerance _select_building_region() itself already trusts.
        mask_centroid = solar_api.polygon_centroid(mask_result.polygon)
        disagreement_m = solar_api.centroid_disagreement_m(mask_centroid, result.centroid)
        max_disagreement_m = float(config_pack.get_roof_mask_params()["max_pin_distance_m"])
        if disagreement_m is None or disagreement_m <= max_disagreement_m:
            boundary = mask_result.polygon
            source = "solar_api_mask"

    ring = (boundary.get("coordinates") or [[]])[0]
    points = [PanelCornerOut(lat=point_lat, lng=point_lng) for point_lng, point_lat in ring]

    # Always derived from `boundary` above, never from `result.centroid`
    # directly — when the mask swap just above picked a DIFFERENT
    # structure than Building Insights resolved, `result.centroid` is
    # that other building's centre. Recomputing from the boundary that
    # is actually being returned keeps this response internally
    # consistent — see solar_api.polygon_centroid()'s docstring for why
    # this exact mismatch is what makes the next wizard step's map
    # recentre away from the polygon it just drew.
    centroid_geojson = solar_api.polygon_centroid(boundary) or result.centroid
    centroid_out = None
    centroid_coords = (centroid_geojson or {}).get("coordinates")
    if centroid_coords:
        centroid_out = PanelCornerOut(lat=centroid_coords[1], lng=centroid_coords[0])

    # Same raw Building Insights payload already fetched above for the
    # boundary — no second call. The pin's own (lat, lng), not the
    # centroid: a pin dropped on one wing of an L-shaped roof should
    # report THAT wing's plane, not whichever segment happens to be
    # nearest the building's overall centre.
    pitch = solar_api.roof_pitch_at_point(
        result.raw, lat, lng, imagery_quality=result.imagery_quality
    )
    roof_pitch_out = (
        RoofPitchOut(
            segment_index=pitch.segment_index,
            pitch_deg=pitch.pitch_deg,
            azimuth_deg=pitch.azimuth_deg,
            orientation=pitch.orientation,
            plane_height_m=pitch.plane_height_m,
            area_m2=pitch.area_m2,
            ground_area_m2=pitch.ground_area_m2,
            segment_count=pitch.segment_count,
            matched_by=pitch.matched_by,
            confidence=pitch.confidence,
        )
        if pitch is not None
        else None
    )

    return ResolveBuildingOut(
        status="ok",
        boundary=points,
        centroid=centroid_out,
        area_m2=result.roof_area_m2,
        source=source,
        imagery_quality=result.imagery_quality,
        imagery_date=result.imagery_date.isoformat() if result.imagery_date else None,
        competing_buildings_nearby=competing_buildings_nearby,
        detail=result.detail,
        roof_pitch=roof_pitch_out,
    )


@router.get("/checks/{check_id}", response_model=SiteOut)
def get_check(
    check_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> SiteOut:
    site, row = _readable_check_or_404(session, check_id, user)
    return _site_out(session, site, row)


class SolarPanelOut(_CamelModel):
    corners: list[PanelCornerOut]
    capacity_watts: float | None = None
    orientation: str
    segment_index: int | None = None
    azimuth_degrees: float | None = None
    pitch_degrees: float | None = None


class SolarLayoutValidationOut(_CamelModel):
    """engine/panel_validation.py's independent re-check of the layout
    above — always None for rows persisted before this field existed.
    panels_outside_roof/panels_intersecting_obstacles should always be 0;
    this makes that a checked, reported number rather than an assumption.
    """

    panel_count: int = 0
    rejected_count: int = 0
    panels_outside_roof: int = 0
    panels_intersecting_obstacles: int = 0


class SolarLayoutOut(_CamelModel):
    """This app's own panel layout for this rooftop (engine/panel_packing.py),
    for drawing over the satellite imagery.

    `panel_count`/`total_kwp` now describe the SAME system the result
    page's capacity figure names — the layout was packed specifically to
    reach `capacity.recommended_kwp` (see routers/assessments.py::
    _pack_panel_layout()), inside the resolved usable polygon, obstacle-
    and setback-aware. Small floating-point differences between the two
    numbers are possible (a packed layout can't hit an arbitrary kWp
    exactly — it stops at the nearest whole panel), but they should never
    disagree by more than one panel's worth.
    """

    status: str  # ok | no_layout | no_data
    reason: str | None = None
    source: str = "packed layout"
    panel_count: int = 0
    total_kwp: float = 0.0
    panels: list[SolarPanelOut] = Field(default_factory=list)
    validation: SolarLayoutValidationOut | None = None


@router.get("/checks/{check_id}/solar-layout", response_model=SolarLayoutOut)
def get_check_solar_layout(
    check_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> SolarLayoutOut:
    """The panel layout persisted alongside this check's latest assessment
    (engine/panel_packing.py, packed at assessment time — see
    routers/assessments.py::_pack_panel_layout()).

    Reads the stored layout rather than repacking live: packing was
    already done once, against the exact usable polygon and capacity this
    assessment resolved, and repeating it on every page view could drift
    from what the rest of the result page is describing (e.g. if the
    site's exclusions changed since). A failure or absence here must
    never take the result page's verdict or capacity down with it —
    non-ok statuses come back as 200 with an explicit reason.
    """
    _site, _row = _readable_check_or_404(session, check_id, user)
    assessment = assessments_repo.get_latest_by_site(session, check_id)

    if assessment is None:
        return SolarLayoutOut(status="no_data", reason="No assessment has run for this check yet")

    layout = assessment.panel_layout
    if not layout:
        return SolarLayoutOut(
            status="no_layout", reason="No panel layout is available for this rooftop"
        )

    raw_validation = layout.get("validation")
    validation = (
        SolarLayoutValidationOut(
            panel_count=raw_validation.get("panelCount", 0),
            rejected_count=raw_validation.get("rejectedCount", 0),
            panels_outside_roof=raw_validation.get("panelsOutsideRoof", 0),
            panels_intersecting_obstacles=raw_validation.get("panelsIntersectingObstacles", 0),
        )
        if raw_validation
        else None
    )

    return SolarLayoutOut(
        status=layout.get("status", "ok"),
        reason=layout.get("reason"),
        panel_count=layout.get("panelCount", 0),
        total_kwp=layout.get("totalKwp", 0.0),
        validation=validation,
        panels=[
            SolarPanelOut(
                corners=[PanelCornerOut(lat=lat, lng=lng) for lng, lat in panel["corners"]],
                capacity_watts=layout.get("panelWatts"),
                orientation=layout.get("orientation", "PORTRAIT"),
                segment_index=panel.get("segmentIndex"),
                azimuth_degrees=panel.get("azimuthDeg"),
                pitch_degrees=panel.get("tiltDeg"),
            )
            for panel in layout.get("panels", [])
        ],
    )


class SceneMeshOut(_CamelModel):
    """engine/panorama.py::SceneMesh, unchanged — vertices/faces in the
    local metre frame (x east, y north, z up, ground at z=0) a Three.js
    BufferGeometry can consume directly, plus the same mesh's per-vertex
    colors (roof sunshine tint / panel frame+glass) when it has any."""

    vertices: list[list[float]]
    faces: list[list[int]]
    colors: list[list[float]] | None = None


def _scene_mesh_out(mesh) -> SceneMeshOut | None:
    if mesh is None:
        return None
    return SceneMeshOut(vertices=mesh.vertices, faces=mesh.faces, colors=mesh.colors)


class SceneObstacleOut(_CamelModel):
    id: str
    type: str | None = None
    mesh: SceneMeshOut


class SceneOut(_CamelModel):
    """The 3D rooftop viewer's data source: engine/panorama.py::
    build_scene_geometry()'s roof + walls + this app's own packed panel
    array + mounting-rack visuals + OBS-04's applied obstacles, for this
    check's latest assessment, for the client-side Three.js scene on the
    result page. Unrelated to panorama_url/the .glb pipeline
    (SolarLayoutOut/PanoramaResult above, untouched)."""

    status: str  # ok | not_generated | no_data
    reason: str | None = None
    origin_lat: float | None = None
    origin_lng: float | None = None
    height_m: float | None = None
    ground_source: str | None = None
    roof: SceneMeshOut | None = None
    walls: SceneMeshOut | None = None
    panels: SceneMeshOut | None = None
    # Visual-only support-leg/rack geometry under flat-mounted panels
    # (engine/panorama.py::_mounting_leg_mesh()) — never affects panel
    # count, position or tilt, purely presentation.
    mounting: SceneMeshOut | None = None
    panel_count: int = 0
    obstacles: list[SceneObstacleOut] = Field(default_factory=list)
    version: str | None = None


@router.get("/checks/{check_id}/scene", response_model=SceneOut)
def get_check_scene(
    check_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> SceneOut:
    """Roof + walls + panel array + mounting racks + obstacles geometry
    for the client-side Three.js viewer on the result page
    (components/panorama/Scene3DViewer.tsx).

    Builds from this check's own stored boundary, its latest assessment's
    OWN packed panel_layout (NOT Google's solarPanels[] — see
    engine/panorama.py::_panel_mesh_from_layout()'s docstring), and
    OBS-04's applied obstacles (repositories/sites.py::
    applied_obstacles(), the same read get_check_obstacles() above uses)
    via engine/panorama.py::build_scene_geometry() — the same real DSM/
    segment-plane/shading source of truth generate_panorama()'s .glb
    export already uses, just serialized as JSON instead of baked into a
    binary scene. Computed on request rather than cached — see this
    function's own follow-up note if page-load latency becomes an issue.
    """
    _site, _row = _readable_check_or_404(session, check_id, user)
    assessment = assessments_repo.get_latest_by_site(session, check_id)

    if assessment is None or not assessment.boundary:
        return SceneOut(status="no_data", reason="No assessment has run for this check yet")

    obstacles = [
        {"id": obstacle_id, "type": obs_type, "bounding_polygon": polygon}
        for obstacle_id, polygon, obs_type, _confidence, _source in repo.applied_obstacles(
            session, check_id
        )
    ]

    result = build_scene_geometry(
        assessment.boundary, panel_layout=assessment.panel_layout, obstacles=obstacles
    )
    return SceneOut(
        status=result.status,
        reason=result.reason,
        origin_lat=result.origin_lat,
        origin_lng=result.origin_lng,
        height_m=result.height_m,
        ground_source=result.ground_source,
        roof=_scene_mesh_out(result.roof),
        walls=_scene_mesh_out(result.walls),
        panels=_scene_mesh_out(result.panels),
        mounting=_scene_mesh_out(result.mounting),
        panel_count=result.panel_count,
        obstacles=[
            SceneObstacleOut(id=o.id, type=o.type, mesh=_scene_mesh_out(o.mesh))
            for o in result.obstacles
        ],
        version=result.version,
    )


class RoofObstacleOut(_CamelModel):
    id: str
    polygon: list[PanelCornerOut]
    # domain/assessment.py::ObstacleType (water_tank/hvac_unit/chimney/
    # existing_solar_panel/vent/antenna/other) + its real detection
    # confidence. Both None for an obstacle applied before this field
    # existed — never guessed for an older row.
    type: str | None = None
    confidence: float | None = None
    # Provenance, not a visual distinction: "vision_llm"/"cv_detector"/
    # "obstacle_detection" for something the pipeline found, and
    # "customer_marked" for something the homeowner placed themselves.
    # The customer UI renders both identically — this only tells the
    # marking screen which items that customer is allowed to remove.
    source: str | None = None


class RoofObstaclesOut(_CamelModel):
    """OBS-04. Obstacles detected on this roof and unioned into the site's
    exclusions, so they can be drawn over the satellite imagery.

    `detected` distinguishes "this roof genuinely has none" from "nothing
    has looked yet" — the vision pipeline (OBS-01/02) needs an
    OPENAI_API_KEY, and without one it reports insufficient_data and
    finds nothing. Showing an empty roof as "no obstacles" in that case
    would be a lie of omission.
    """

    detected: bool
    reason: str | None = None
    obstacles: list[RoofObstacleOut] = Field(default_factory=list)


@router.get("/checks/{check_id}/obstacles", response_model=RoofObstaclesOut)
def get_check_obstacles(
    check_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> RoofObstaclesOut:
    """The real obstacles applied to this roof — never a guess.

    Nothing here infers an obstacle from elevation or imagery on the fly.
    It reports what OBS-04 actually applied; an empty list means nothing
    was detected, and `reason` says whether detection ever ran.
    """
    _site, _row = _readable_check_or_404(session, check_id, user)
    found = repo.applied_obstacles(session, check_id)

    if not found:
        vision_configured = bool(get_settings().openai_api_key)
        return RoofObstaclesOut(
            detected=vision_configured,
            reason=(
                None
                if vision_configured
                else "Rooftop obstacle detection is not configured on this deployment"
            ),
        )

    return RoofObstaclesOut(detected=True, obstacles=_obstacles_out(found))


def _obstacles_out(found: list[tuple[str, dict, str | None, float | None, str | None]]):
    obstacles: list[RoofObstacleOut] = []
    for obstacle_id, polygon, obs_type, confidence, source in found:
        ring = ((polygon or {}).get("coordinates") or [[]])[0]
        points = [PanelCornerOut(lat=lat, lng=lng) for lng, lat in ring]
        if len(points) >= 3:
            obstacles.append(
                RoofObstacleOut(
                    id=obstacle_id,
                    polygon=points,
                    type=obs_type,
                    confidence=confidence,
                    source=source,
                )
            )
    return obstacles


# The side length of the square footprint a customer's single map tap
# becomes. A tap is a point, not a traced outline, so the size is a
# deliberate, documented default rather than a measurement: 1.5 m is a
# typical rooftop water tank / split-AC condenser footprint in this
# market, comfortably above the pack's min_obstacle_area_m2 (0.25 m²)
# and far below max_obstacle_area_fraction_of_boundary. AREA-04 buffers
# it OUT by the pack's real obstacle_setback_m on top of this, so the
# area actually removed from the roof is larger than the square itself.
# PLACEHOLDER: replace with a customer-adjustable size if the marking
# UI ever grows a size control.
_CUSTOMER_OBSTACLE_SIDE_M = 1.5

_CUSTOMER_OBSTACLE_SOURCE = "customer_marked"


def _square_around(lat: float, lng: float, side_m: float) -> dict:
    """A `side_m` square centred on (lat, lng), as a GeoJSON Polygon.

    Built in a projected CRS and transformed back — §17: a "square" laid
    out by adding degrees to EPSG:4326 coordinates is not square and not
    the size it claims, and gets worse the further from the equator.
    """
    epsg = utm_epsg_for(lng, lat)
    to_metric_xy = Transformer.from_crs(f"EPSG:{WGS84_EPSG}", f"EPSG:{epsg}", always_xy=True).transform
    to_wgs84 = Transformer.from_crs(f"EPSG:{epsg}", f"EPSG:{WGS84_EPSG}", always_xy=True).transform

    x, y = to_metric_xy(lng, lat)
    half = side_m / 2.0
    corners_m = [
        (x - half, y - half),
        (x + half, y - half),
        (x + half, y + half),
        (x - half, y + half),
    ]
    ring = [to_wgs84(cx, cy) for cx, cy in corners_m]
    return {"type": "Polygon", "coordinates": [[[lng_, lat_] for lng_, lat_ in ring] + [list(ring[0])]]}


class MarkObstacleRequest(_CamelModel):
    type: ObstacleType
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


def _union_exclusions(site, polygon: dict) -> dict:
    """`polygon` unioned into the site's existing exclusions — the same
    single-MultiPolygon shape engine/obstacles.py::apply_or_flag()
    produces, so both writers leave the geometry in one form."""
    geoms = [shape(polygon)]
    if site.exclusions:
        geoms.append(shape(site.exclusions))
    union_geom = unary_union(geoms)
    if union_geom.geom_type == "Polygon":
        union_geom = MultiPolygon([union_geom])
    return mapping(union_geom)


@router.post(
    "/checks/{check_id}/obstacles",
    response_model=RoofObstacleOut,
    status_code=status.HTTP_201_CREATED,
)
def mark_check_obstacle(
    check_id: str,
    payload: MarkObstacleRequest,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> RoofObstacleOut:
    """The homeowner marking something that's really on their own roof.

    This is not a second obstacle system. The tap becomes a square
    polygon, is put through OBS-03's *existing* validation
    (providers.vision.validate_obstacle_polygon — self-intersection,
    containment in the boundary, plausible area), is unioned into
    site.exclusions, and is recorded on the new SITE-05 version through
    the same applied_obstacle_ids/applied_obstacle_polygons provenance
    the OBS-04 auto-apply already uses. GET .../obstacles then returns
    it alongside the detected ones with no special-casing.

    There is deliberately no confidence: a customer pointing at their own
    roof is a statement, not a probabilistic detection, and inventing a
    number for it would be a fabrication the UI would then display as
    "N% sure".

    Like a corrected boundary, this versions the geometry immediately but
    does NOT itself recompute the assessment — the caller re-runs it via
    POST /checks/{id}/complete, exactly as BoundaryEditorClient does.
    """
    site, _row = _owned_check_or_404(session, check_id, _individual_owner_org(user))
    if site.boundary is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This roof has no outline yet, so there is nothing to mark an obstacle on.",
        )

    polygon = _square_around(payload.lat, payload.lng, _CUSTOMER_OBSTACLE_SIDE_M)
    obstacle = Obstacle(
        type=payload.type,
        bounding_polygon=polygon,
        # Only used to satisfy the frozen domain contract while OBS-03
        # validates the geometry; the value persisted below is None.
        confidence=1.0,
        source=_CUSTOMER_OBSTACLE_SOURCE,
        applied=True,
    )
    if not validate_obstacle_polygon(obstacle, site.boundary):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "That spot isn't inside your roof outline. Tap somewhere on the roof itself.",
        )

    repo.new_geometry_version(
        session,
        check_id,
        exclusions=_union_exclusions(site, polygon),
        actor=user.email,
        source="customer_marked_obstacle",
        applied_obstacle_ids=[obstacle.id],
        applied_obstacle_polygons={
            obstacle.id: {
                "polygon": polygon,
                "type": obstacle.type,
                "confidence": None,
                "source": _CUSTOMER_OBSTACLE_SOURCE,
            }
        },
    )
    ring = polygon["coordinates"][0]
    return RoofObstacleOut(
        id=obstacle.id,
        polygon=[PanelCornerOut(lat=lat, lng=lng) for lng, lat in ring],
        type=obstacle.type,
        confidence=None,
        source=_CUSTOMER_OBSTACLE_SOURCE,
    )


@router.delete("/checks/{check_id}/obstacles/{obstacle_id}", status_code=status.HTTP_204_NO_CONTENT)
def unmark_check_obstacle(
    check_id: str,
    obstacle_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> None:
    """Remove an obstacle the customer placed themselves.

    Only a `customer_marked` one: an AI detection is the pipeline's
    audited output and is reversed through the admin OBS-06 path
    (engine/obstacles.py::reject_applied_obstacle), not by the customer.

    Mirrors OBS-06's mechanics — subtract exactly this obstacle's own
    polygon from the current exclusions and version again, so SITE-05
    history is retained rather than the applying version being edited.
    """
    site, _row = _owned_check_or_404(session, check_id, _individual_owner_org(user))

    entry = None
    for version in repo.versions(session, check_id):
        candidate = (version.applied_obstacle_polygons or {}).get(obstacle_id)
        if candidate:
            entry = candidate
    if not entry or entry.get("removed"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such obstacle on this roof")
    if entry.get("source") != _CUSTOMER_OBSTACLE_SOURCE:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only obstacles you marked yourself can be removed here.",
        )

    marked_polygon = shape(entry["polygon"])
    current = shape(site.exclusions) if site.exclusions else None
    new_exclusions = mapping(current.difference(marked_polygon)) if current else None

    repo.new_geometry_version(
        session,
        check_id,
        exclusions=new_exclusions or {"type": "MultiPolygon", "coordinates": []},
        actor=user.email,
        source="customer_unmarked_obstacle",
        applied_obstacle_ids=[obstacle_id],
        applied_obstacle_polygons={obstacle_id: {"removed": True}},
    )


class SaveCheckBoundaryRequest(_CamelModel):
    points: list[PanelCornerOut] = Field(min_length=3)


def _apply_manual_boundary(
    session: Session, site, check_id: str, points: list[PanelCornerOut], actor: str
):
    """GEO-02. Validate + version a customer-drawn/confirmed roof outline.

    Shared by save_check_boundary (post-creation correction) and
    create_check (StartCheckWizard's pre-creation confirmed_boundary) so
    the ring-closing + GEO-07/08 validation + SITE-05 versioning logic
    exists in exactly one place. `manual_polygon` (precedence 300)
    outranks GEO-04's `solar_api` rectangle (precedence 100), so from
    here on every assessment measures the confirmed/traced roof instead
    of the bounding box.

    GEO-09: recomputes geometry_confidence fresh for the new
    manual_polygon boundary rather than letting new_geometry_version()
    default it forward from whatever the PRIOR version's source was
    (e.g. a solar_api_mask confidence, which is a different scale/shape
    of trust than a customer-confirmed one). That default-forward
    behaviour is correct for an exclusions-only change (SITE-04 — the
    boundary itself didn't move, so its imagery context should carry
    over) but wrong here: the boundary itself just changed, so its
    confidence must be re-scored against the boundary that's actually
    being stored, not inherited from whatever came before it.
    """
    boundary_geojson = {
        "type": "Polygon",
        # A GeoJSON ring must close; the UI sends the open path it edits.
        "coordinates": [
            [[p.lng, p.lat] for p in points] + [[points[0].lng, points[0].lat]]
        ],
    }
    try:
        validated = manual.resolve_manual(site, {"boundary": boundary_geojson})
    except GeometryRejected as exc:
        # A self-intersecting or degenerate trace is the customer's input
        # to fix, not a server fault — and never silently repaired.
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    confidence = geometry_confidence(
        source="manual_polygon", imagery_date=site.imagery_date, boundary=validated
    )

    return repo.new_geometry_version(
        session,
        check_id,
        boundary=validated,
        actor=actor,
        source="manual_edit",
        geometry_source="manual_polygon",
        geometry_confidence=confidence,
    )


@router.put("/checks/{check_id}/boundary", response_model=SiteOut)
def save_check_boundary(
    check_id: str,
    payload: SaveCheckBoundaryRequest,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> SiteOut:
    """GEO-02. The customer's own traced roof outline.

    A check-scoped twin of PUT /app/sites/{id}/boundary, and not a
    duplicate for its own sake: that route authorises through
    `user.owner_org`, which an individual signup does not have. This is
    the same synthetic-owner_org reason every other route in this module
    exists — without it a customer literally cannot correct their own
    roof, which is what a 404 on save turned out to be.
    """
    site, _row = _owned_check_or_404(session, check_id, _individual_owner_org(user))
    updated_site = _apply_manual_boundary(session, site, check_id, payload.points, user.email)
    updated_row = session.get(repo.SiteRow, uuid.UUID(check_id))
    return _site_out(session, updated_site, updated_row)


@router.post("/checks", response_model=SiteOut, status_code=status.HTTP_201_CREATED)
def create_check(
    payload: NewCheckInput,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> SiteOut:
    owner_org = _individual_owner_org(user)

    # USN-01, reusing providers/usn_ocr.py::capture_manual() — the exact
    # same validation the post-analysis manual-entry path applies, not a
    # re-implementation of it. A malformed value is the customer's own
    # typo to fix, same discipline as a rejected boundary: loud, never
    # silently dropped or repaired.
    captured_usn = None
    if payload.usn:
        try:
            captured_usn = usn_ocr.capture_manual(payload.usn)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    core_payload = SiteCreate(
        site_type=payload.site_type,
        name=payload.address,
        jurisdiction=_DEFAULT_JURISDICTION,
        address=payload.address,
        centroid={"type": "Point", "coordinates": [payload.lng, payload.lat]},
        usn=captured_usn.usn if captured_usn else None,
        usn_source=captured_usn.usn_source if captured_usn else None,
    )
    try:
        site, _note = create_site_core(
            core_payload,
            session,
            owner_org,
            address=payload.address,
            monthly_bill_low_inr=payload.monthly_bill_low_inr,
            monthly_bill_high_inr=payload.monthly_bill_high_inr,
            highest_consumption_kwh=payload.highest_consumption_kwh,
            lowest_consumption_kwh=payload.lowest_consumption_kwh,
            roof_type=payload.roof_type,
            roof_material=payload.roof_material,
            roof_slope=payload.roof_slope,
            roof_construction_year=payload.roof_construction_year,
            electricity_board=payload.electricity_board,
            consumer_number=payload.consumer_number,
            connection_type=payload.connection_type,
            sanctioned_load_kw=payload.sanctioned_load_kw,
            contract_demand_kva=payload.contract_demand_kva,
            connected_load_kw=payload.connected_load_kw,
            monthly_consumption_kwh=[e.model_dump(by_alias=False) for e in payload.monthly_consumption_kwh],
            battery_required=payload.battery_required,
            backup_required=payload.backup_required,
            required_backup_hours=payload.required_backup_hours,
            critical_loads=payload.critical_loads,
        )
    except solar_api.SolarApiError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    # StartCheckWizard: the customer already confirmed a rooftop polygon
    # on the map before creating the check. Apply it now, atomically with
    # creation, via the same helper save_check_boundary uses — so
    # complete_check's background job never has a window where it would
    # run against create_site_core's un-cropped rectangle instead.
    if payload.confirmed_boundary:
        site = _apply_manual_boundary(
            session, site, site.id, payload.confirmed_boundary, user.email
        )

    if payload.map_metadata:
        # Stored camelCase (by_alias=True) since this JSONB blob is
        # echoed back verbatim as SiteOut.mapViewMetadata, unlike every
        # other field on this row which _site_out re-serialises through
        # a typed, camelCase-aliased model.
        repo.set_map_view_metadata(session, site.id, payload.map_metadata.model_dump(by_alias=True))

    row = session.get(repo.SiteRow, uuid.UUID(site.id))
    return _site_out(session, site, row)


class StartAssessmentOut(_CamelModel):
    job_id: str


class AssessmentJobStatusOut(_CamelModel):
    """Phase 4 — what the processing screen polls.

    `status`: "pending" | "progress" | "ok" | "not_found" |
    "geometry_rejected" | "error". `stage` is one of
    routers/assessments.py::ASSESSMENT_STAGES, present only while
    status == "progress" — the frontend owns the human-facing copy for
    each stage key, same split as every other symbolic-status field in
    this codebase."""

    job_id: str
    status: str
    stage: str | None = None
    error: str | None = None


@router.post(
    "/checks/{check_id}/complete", response_model=StartAssessmentOut, status_code=status.HTTP_202_ACCEPTED
)
def complete_check(
    check_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> StartAssessmentOut:
    """Starts the real engine (routers/assessments.py::orchestrate_assessment,
    unchanged) as a background job and returns a job id to poll — never a
    fabricated verdict, and never a request left blocking for however
    long the full pipeline takes.

    Previously this ran orchestrate_assessment synchronously in-request
    and returned the finished SiteOut directly; the processing screen
    covered that wait with a fixed ~3s client-side animation regardless
    of how long the real work actually took. Phase 4 replaces that with
    workers/tasks_assessments.py::run_check_assessment_task, polled via
    GET .../complete/{job_id} below, which reports the pipeline's real
    stage as it runs.

    Deliberately does NOT touch vendor_jobs — see
    run_check_assessment_task's own docstring for where persistence and
    the admin-review-queue handoff now happen (inside the task, not
    here)."""
    owner_org = _individual_owner_org(user)
    _owned_check_or_404(session, check_id, owner_org)

    task = run_check_assessment_task.delay(check_id, owner_org)
    return StartAssessmentOut(job_id=task.id)


@router.get("/checks/{check_id}/complete/{job_id}", response_model=AssessmentJobStatusOut)
def get_check_assessment_status(
    check_id: str,
    job_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> AssessmentJobStatusOut:
    """Ownership is checked against `check_id`, not `job_id` — Celery job
    ids are opaque UUIDs from `task.id`, not scoped to a tenant on their
    own, so a caller with no ownership of a check has no way to guess
    their way into reading a real job's status."""
    _owned_check_or_404(session, check_id, _individual_owner_org(user))

    async_result = celery_app.AsyncResult(job_id)
    if async_result.state == "PROGRESS":
        meta = async_result.info if isinstance(async_result.info, dict) else {}
        return AssessmentJobStatusOut(job_id=job_id, status="progress", stage=meta.get("stage"))
    if async_result.state == "SUCCESS":
        result = async_result.result if isinstance(async_result.result, dict) else {}
        job_status = result.get("status", "ok")
        return AssessmentJobStatusOut(job_id=job_id, status=job_status, error=result.get("error"))
    if async_result.state == "FAILURE":
        return AssessmentJobStatusOut(job_id=job_id, status="error", error=str(async_result.info))
    # PENDING (not yet picked up) or a Celery state we don't special-case.
    return AssessmentJobStatusOut(job_id=job_id, status="pending")


# --------------------------------------------------------------------- #
# enquiry — the customer's own act of turning a viewed result into
# something an admin needs to look at. Deliberately separate from
# completing the check itself (see repositories/assessments.py::
# save_assessment()'s "not_submitted" default): a customer can view a
# SUITABLE result without this ever being called.
# --------------------------------------------------------------------- #


class NearbyVendorOut(_CamelModel):
    """Customer-safe vendor card — name/service-area/verification/
    availability/certifications only. Deliberately excludes every
    contact/legal field admin's own AdminVendorSummary carries (phone,
    email, GST/PAN, address) — a customer doesn't get a vendor's direct
    contact details before the vendor has actually agreed to the job,
    same policy this codebase already applies to the survey-status
    banner (see SiteOut.survey_job_status's own comment).

    averageRating/reviewCount come from real customer reviews
    (repositories/vendor_reviews.py) — averageRating is null, not 0,
    when reviewCount is 0, so the UI can show "No reviews yet" instead
    of a fabricated score. activeJobs/jobsCompleted are the same
    live-computed figures vendors_repo.vendor_admin_stats() already
    gives the admin screen, now also shown to the customer choosing a
    vendor. accuracyScore is kept for backward compatibility but is a
    separate, currently-dormant metric (see VendorRow's own docstring)
    — not a customer rating, and the frontend no longer renders it as
    one."""

    id: str
    name: str
    match_category: Literal["same_district", "same_state", "other"]
    region: str
    verification_status: str
    availability: bool
    accuracy_score: float
    certifications: list[str] = Field(default_factory=list)
    average_rating: float | None = None
    review_count: int = 0
    active_jobs: int = 0
    jobs_completed: int = 0


@router.get("/checks/{check_id}/vendors", response_model=list[NearbyVendorOut])
def list_check_vendors(
    check_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> list[NearbyVendorOut]:
    """Nearby/available vendors for this check's own district/state —
    "nearby" means district/state matching (the same real signal
    repositories/vendors.py's own reassignment matching already uses),
    never a fabricated geographic distance (no vendor has a lat/lng in
    this schema). Only verified + available vendors are shown at all;
    a district/state match is preferred but a genuinely empty
    verified+available pool is the only case that returns []."""
    _site, row = _owned_check_or_404(session, check_id, _individual_owner_org(user))
    district = (row.district or "").strip()
    state = (row.state or "").strip()

    candidates = vendors_repo.list_vendors(session, verification_status="verified")
    candidates = [v for v in candidates if v.availability]

    def _match_category(vendor) -> str:
        districts = vendor.service_area.get("districts") or []
        if district and district in districts:
            return "same_district"
        if state and state.lower() == str(vendor.service_area.get("region") or "").lower():
            return "same_state"
        return "other"

    result = []
    for v in candidates:
        stats = vendors_repo.vendor_admin_stats(session, v.id)
        rating = vendor_reviews_repo.vendor_rating_summary(session, v.id)
        result.append(
            NearbyVendorOut(
                id=str(v.id),
                name=v.name,
                match_category=_match_category(v),
                region=v.service_area.get("region") or "",
                verification_status=v.verification_status,
                availability=v.availability,
                accuracy_score=v.accuracy_score,
                certifications=v.certifications or [],
                average_rating=rating["average_rating"],
                review_count=rating["review_count"],
                active_jobs=stats["active_jobs"],
                jobs_completed=stats["total_jobs_completed"],
            )
        )
    return result


class RaiseEnquiryRequest(_CamelModel):
    vendor_id: str | None = None


@router.post("/checks/{check_id}/enquiry", response_model=SiteOut)
def raise_check_enquiry(
    check_id: str,
    payload: RaiseEnquiryRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> SiteOut:
    """The one place review_status moves from "not_submitted" to
    "pending" for a customer-initiated enquiry. Idempotent — calling
    this again on the same check is a no-op (see repositories/
    assessments.py::raise_enquiry()'s own docstring); the frontend never
    needs special double-submit handling, though it should still disable
    the button while the request is in flight."""
    site, row = _owned_check_or_404(session, check_id, _individual_owner_org(user))
    assessment = assessments_repo.get_latest_by_site(session, check_id)
    if assessment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no assessment has run for this check yet")
    if assessment.review_status == "not_applicable":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "this assessment's verdict is not eligible for an enquiry"
        )

    if payload.vendor_id:
        vendor_row = vendors_repo.get_vendor(session, payload.vendor_id)
        if vendor_row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "vendor not found")
        if vendor_row.verification_status != "verified" or not vendor_row.availability:
            raise HTTPException(status.HTTP_409_CONFLICT, "vendor is not currently available")

    already_submitted = assessment.review_status != "not_submitted"
    assessments_repo.raise_enquiry(session, assessment.id, vendor_id=payload.vendor_id, user_id=user.id)
    if not already_submitted:
        audit_repo.write_audit_log(
            session,
            **actor_audit_fields(user),
            action="enquiry.raised",
            target=assessment.id,
            details=(
                f"{user.email} raised an enquiry for site {check_id}"
                + (f" requesting vendor {payload.vendor_id}" if payload.vendor_id else " with no vendor preference")
            ),
            entity_type="assessment",
            project_id=check_id,
            survey_id=assessment.id,
            customer_id=user.id,
            vendor_id=payload.vendor_id,
            new_value={"reviewStatus": "pending", "customerSelectedVendorId": payload.vendor_id},
            **request_audit_meta(request),
        )
        # Mirrors app_vendor.py::submit_job's "no per-admin preference,
        # every admin sees every X" notification — this is the Super
        # Admin review-queue trigger spec section 10 asks for ("New
        # vendor request submitted").
        for admin_user in users_repo.list_by_role(session, "admin"):
            notifications_repo.create_notification(
                session,
                user_id=admin_user.id,
                kind="vendor_request_submitted",
                title="A new vendor request needs review",
                body=f"{user.name} submitted a vendor request for site {check_id}.",
            )
    return _site_out(session, site, row)


# --------------------------------------------------------------------- #
# installation
#
# The pipeline used to stop dead at review_status == "approved" (admin
# approved, vendor assigned) with no further customer action possible.
# accept_quotation() below is the missing trigger: the customer's
# acceptance is what actually opens an installation project.
#
# Everything the customer can read back here is deliberately a subset —
# stage/capacity/equipment only, no vendor contact details and no
# reviewer identity, the same discipline app_assessments.py's
# ReviewFieldsOut applies.
# --------------------------------------------------------------------- #


class CustomerInstallationOut(_CamelModel):
    """The customer-safe view of an installation project. `stages` is the
    full ordered key list and `stageIndex` the position within it — the
    same "backend emits symbolic keys, frontend owns the copy" contract
    as routers/assessments.py::ASSESSMENT_STAGES, so a progress strip can
    render without hardcoding the pipeline."""

    id: str
    site_id: str
    status: str
    stage_index: int
    stages: list[str]
    approved_capacity_kwp: float
    panel_model: str | None = None
    inverter_model: str | None = None
    created_at: datetime
    updated_at: datetime
    # Sign-off state the customer genuinely acts on, lifted off the
    # commissioning record so the result page needs one request, not two.
    qc_approved: bool = False
    commissioning_submitted: bool = False
    customer_accepted: bool = False
    admin_approved: bool = False
    # Whether a vendor_reviews row already exists for this project — lets
    # the result page stop offering "rate your vendor" after the customer
    # already has, even across a page reload, without a second request.
    reviewed: bool = False


def _customer_installation_out(
    session: Session, project: installations_repo.InstallationProjectRow
) -> CustomerInstallationOut:
    checklist = installations_repo.get_checklist(session, project.id)
    commissioning = installations_repo.get_commissioning(session, project.id)
    return CustomerInstallationOut(
        id=project.id,
        site_id=str(project.site_id),
        status=project.status,
        stage_index=installations_repo.stage_index(project.status),
        stages=installations_repo.INSTALLATION_STAGES,
        approved_capacity_kwp=project.approved_capacity_kwp,
        panel_model=project.panel_model,
        inverter_model=project.inverter_model,
        created_at=project.created_at,
        updated_at=project.updated_at,
        qc_approved=checklist is not None and checklist.approved_at is not None,
        commissioning_submitted=commissioning is not None and commissioning.vendor_confirmed,
        customer_accepted=commissioning is not None and commissioning.customer_accepted,
        admin_approved=commissioning is not None and commissioning.admin_approved,
        reviewed=vendor_reviews_repo.get_review_for_project(session, project.id) is not None,
    )


@router.post(
    "/checks/{check_id}/accept-quotation",
    response_model=CustomerInstallationOut,
    status_code=status.HTTP_201_CREATED,
)
def accept_quotation(
    check_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> CustomerInstallationOut:
    """Customer -> Feasibility Check -> Admin Review -> Admin Approval ->
    Vendor Survey -> **Customer accepts the quotation** -> Installation.

    This is the one and only path that creates an installation_projects
    row (repositories/installations.py::create_project() is its
    create_job() equivalent). Guarded exactly like
    app_assessments.py::approve_assessment(): 404 if there's nothing to
    act on, 409 if the assessment is in the wrong state.

    Idempotent by 409 rather than by no-op — unlike raise_enquiry(),
    accepting twice would otherwise open a second physical install, so
    the second call is an explicit conflict that returns nothing new."""
    _owned_check_or_404(session, check_id, _individual_owner_org(user))
    assessment = assessments_repo.get_latest_by_site(session, check_id)
    if assessment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no assessment has run for this check yet")
    if assessment.review_status != "approved":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"assessment is {assessment.review_status}, not approved — there is no quotation to accept yet",
        )

    existing = installations_repo.get_project_for_site(session, check_id)
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "an installation project already exists for this check"
        )

    project = installations_repo.create_project(
        session,
        site_id=check_id,
        approved_capacity_kwp=float(assessment.capacity.get("recommended_kwp") or 0.0),
        vendor_job_id=assessment.vendor_job_id,
        assigned_vendor_id=assessment.assigned_vendor_id,
        status="created",
    )
    audit_repo.write_audit_log(
        session,
        actor=user.email,
        action="assessment.quotation_accepted",
        target=assessment.id,
        details=(
            f"{user.email} accepted the quotation for site {check_id} — "
            f"opened installation project {project.id} at "
            f"{project.approved_capacity_kwp} kWp"
        ),
    )
    return _customer_installation_out(session, project)


@router.get("/checks/{check_id}/installation", response_model=CustomerInstallationOut)
def get_check_installation(
    check_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> CustomerInstallationOut:
    """404 when no project exists yet — the result page treats that as
    "no install section to render", the same null-safe way it treats
    every other optional card."""
    _owned_check_or_404(session, check_id, _individual_owner_org(user))
    project = installations_repo.get_project_for_site(session, check_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no installation project for this check")
    return _customer_installation_out(session, project)


@router.post("/checks/{check_id}/installation/accept", response_model=CommissioningRecordOut)
def accept_installation(
    check_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> CommissioningRecordOut:
    """The customer's final handover sign-off. Requires the vendor to
    have submitted the commissioning record first — there is nothing to
    accept before that — and 409s on a second call rather than silently
    re-stamping an acceptance that is already on record."""
    _owned_check_or_404(session, check_id, _individual_owner_org(user))
    project = installations_repo.get_project_for_site(session, check_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no installation project for this check")

    record = installations_repo.get_commissioning(session, project.id)
    if record is None or not record.vendor_confirmed:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "the installer has not submitted commissioning details yet"
        )
    if record.customer_accepted:
        raise HTTPException(status.HTTP_409_CONFLICT, "you have already accepted this installation")

    record = installations_repo.set_commissioning(
        session, project.id, fields={"customer_accepted": True}
    )
    audit_repo.write_audit_log(
        session,
        **actor_audit_fields(user),
        action="installation.customer_accepted",
        target=project.id,
        details=f"{user.email} accepted the completed installation for site {check_id}",
        entity_type="installation_project",
        project_id=check_id,
        vendor_id=str(project.assigned_vendor_id) if project.assigned_vendor_id else None,
        customer_id=user.id,
        **request_audit_meta(request),
    )
    return commissioning_out(record)


# --------------------------------------------------------------------- #
# vendor reviews — only available once the customer has accepted the
# finished installation (accept_installation() above), so a review can
# never be left for work that was never actually confirmed done. One
# review per installation project, enforced by VendorReviewRow's own
# unique constraint, not just this endpoint's own pre-check — a
# double-submit race still ends in a 409, never two reviews.
# --------------------------------------------------------------------- #


class VendorReviewRequest(_CamelModel):
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


class VendorReviewOut(_CamelModel):
    id: str
    vendor_id: str
    rating: int
    comment: str | None
    created_at: datetime
    # First name only — same "customer-safe, not the full identity"
    # discipline NearbyVendorOut applies in the other direction.
    reviewer_name: str


def _review_out(row: vendor_reviews_repo.VendorReviewRow, reviewer_name: str) -> VendorReviewOut:
    return VendorReviewOut(
        id=str(row.id),
        vendor_id=str(row.vendor_id),
        rating=row.rating,
        comment=row.comment,
        created_at=row.created_at,
        reviewer_name=reviewer_name,
    )


@router.post("/checks/{check_id}/review", response_model=VendorReviewOut, status_code=status.HTTP_201_CREATED)
def submit_vendor_review(
    check_id: str,
    payload: VendorReviewRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> VendorReviewOut:
    """Gated on the customer having already accepted the finished
    installation (record.customer_accepted) — the same real "the work is
    actually done" signal accept_installation() itself requires the
    vendor to have confirmed first. Never gated on admin_approved: that's
    a separate, admin-owned sign-off timeline, and the customer's own
    acceptance is the honest trigger for "was I happy with this vendor,"
    not whether admin has gotten around to closing the paperwork."""
    _owned_check_or_404(session, check_id, _individual_owner_org(user))
    project = installations_repo.get_project_for_site(session, check_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no installation project for this check")
    if project.assigned_vendor_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "this installation has no assigned vendor to review")

    record = installations_repo.get_commissioning(session, project.id)
    if record is None or not record.customer_accepted:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "you can only review a vendor after accepting the completed installation",
        )

    if vendor_reviews_repo.get_review_for_project(session, project.id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "you have already reviewed this installation")

    try:
        row = vendor_reviews_repo.create_review(
            session,
            vendor_id=project.assigned_vendor_id,
            installation_project_id=project.id,
            customer_user_id=user.id,
            rating=payload.rating,
            comment=payload.comment,
        )
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "you have already reviewed this installation") from exc

    audit_repo.write_audit_log(
        session,
        **actor_audit_fields(user),
        action="vendor.reviewed",
        target=str(row.id),
        details=f"{user.email} left a {payload.rating}-star review for vendor {project.assigned_vendor_id}",
        entity_type="vendor_review",
        entity_id=str(row.id),
        project_id=check_id,
        customer_id=user.id,
        vendor_id=str(project.assigned_vendor_id),
        new_value={"rating": payload.rating},
        **request_audit_meta(request),
    )
    vendors_repo.notify_vendor_users(
        session,
        project.assigned_vendor_id,
        preference_key="installation_updates",
        kind="vendor_reviewed",
        title="A customer left you a review",
        body=f"{payload.rating}/5 stars" + (f" — {payload.comment}" if payload.comment else ""),
    )
    session.commit()
    return _review_out(row, reviewer_name=user.name.split(" ")[0] if user.name else "Customer")


@router.get("/checks/{check_id}/vendors/{vendor_id}/reviews", response_model=list[VendorReviewOut])
def list_vendor_reviews(
    check_id: str,
    vendor_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> list[VendorReviewOut]:
    """check_id is only used to prove the caller is an authenticated
    customer with a real check on file (same auth-scoping pattern as
    list_check_vendors above) — the reviews themselves are for the
    vendor, not scoped to this specific check, since a vendor's review
    history is what a DIFFERENT customer choosing them needs to see."""
    _owned_check_or_404(session, check_id, _individual_owner_org(user))
    rows = vendor_reviews_repo.list_reviews_for_vendor(session, vendor_id)
    reviewers = {row.customer_user_id: users_repo.get_by_id(session, row.customer_user_id) for row in rows}
    return [
        _review_out(
            row,
            reviewer_name=(
                reviewers[row.customer_user_id].name.split(" ")[0]
                if reviewers[row.customer_user_id] and reviewers[row.customer_user_id].name
                else "Customer"
            ),
        )
        for row in rows
    ]


# --------------------------------------------------------------------- #
# profile
# --------------------------------------------------------------------- #


@router.get("/customer/profile", response_model=CustomerProfileOut)
def get_customer_profile(
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> CustomerProfileOut:
    row = users_repo.get_by_id(session, user.id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")
    return _profile_out(row)


@router.patch("/customer/profile", response_model=CustomerProfileOut)
def update_customer_profile(
    payload: CustomerProfileUpdate,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> CustomerProfileOut:
    row = users_repo.update_profile(
        session,
        user.id,
        name=payload.name,
        phone=payload.phone,
        notify_on_complete=payload.notify_on_complete,
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")
    return _profile_out(row)
