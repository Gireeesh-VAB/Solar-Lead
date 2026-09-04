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
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import Field
from sqlalchemy.orm import Session

from solarfit.auth_users import AuthenticatedUser, current_user
from solarfit.config import get_settings
from solarfit.db import get_session, session_scope
from solarfit.domain.site import BILLING_LINKED_SITE_TYPES, RoofSiteType
from solarfit.engine.panel_layout import fetch_panel_layout
from solarfit.providers import manual, solar_api
from solarfit.providers.validation import GeometryRejected
from solarfit.repositories import assessments as assessments_repo
from solarfit.repositories import sites as repo
from solarfit.repositories import users as users_repo
from solarfit.repositories import vendors as vendors_repo
from solarfit.routers.app_sites import SiteOut, _CamelModel, _site_out
from solarfit.routers.assessments import SiteNotFoundError, orchestrate_assessment
from solarfit.routers.sites import SiteCreate, create_site_core

router = APIRouter(prefix="/app", tags=["app-checks"])

_DEFAULT_JURISDICTION = "IN-TG"  # same rationale as app_sites.py's own constant — no jurisdiction field on this form either
_INDIVIDUAL_OWNER_ORG_PREFIX = "individual:"

# A verdict of SUITABLE_SUBJECT_TO_SURVEY means the engine couldn't be
# confident from imagery alone — this is the one point where a completed
# check hands off to a vendor for an in-person survey. Requirements mirror
# the vendor portal's own field-capture steps (boundary/panorama/USN/
# shading); USN only applies to billing-linked site types, same condition
# app_usn.py's routes gate on.
_SURVEY_VERDICT = "SUITABLE_SUBJECT_TO_SURVEY"
_BOUNDARY_REQ = "Capture boundary polygon"
_USN_REQ = "Confirm USN via bill OCR"
_PANORAMA_REQ = "Upload panorama photo"
_SHADING_REQ = "Note shading obstructions"
_SURVEY_DEADLINE_DAYS = 3
_MIN_SURVEY_PAYOUT_INR = 800
_PAYOUT_PER_KWP_INR = 350


def _individual_owner_org(user: AuthenticatedUser) -> str:
    return f"{_INDIVIDUAL_OWNER_ORG_PREFIX}{user.id}"


def _survey_requirements(site_type: str) -> list[str]:
    requirements = [_BOUNDARY_REQ, _PANORAMA_REQ]
    if site_type in BILLING_LINKED_SITE_TYPES:
        requirements.append(_USN_REQ)
    requirements.append(_SHADING_REQ)
    return requirements


# --------------------------------------------------------------------- #
# schemas
# --------------------------------------------------------------------- #


class NewCheckInput(_CamelModel):
    address: str = Field(min_length=1)
    lat: float
    lng: float
    site_type: RoofSiteType = "ROOFTOP_RESIDENTIAL"
    # CON-05 input. Optional: a check without a bill still runs, and the
    # consumption-offset ceiling reports insufficient_data exactly as it
    # does today — the system is then sized by roof area alone.
    monthly_bill_low_inr: float | None = Field(default=None, gt=0)
    monthly_bill_high_inr: float | None = Field(default=None, gt=0)


class CustomerProfileOut(_CamelModel):
    name: str
    email: str
    phone: str | None
    notify_on_complete: bool


class CustomerProfileUpdate(_CamelModel):
    name: str | None = None
    phone: str | None = None
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


@router.get("/checks/{check_id}", response_model=SiteOut)
def get_check(
    check_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> SiteOut:
    site, row = _owned_check_or_404(session, check_id, _individual_owner_org(user))
    return _site_out(session, site, row)


class PanelCornerOut(_CamelModel):
    lat: float
    lng: float


class SolarPanelOut(_CamelModel):
    corners: list[PanelCornerOut]
    capacity_watts: float | None = None
    orientation: str
    segment_index: int | None = None
    azimuth_degrees: float | None = None
    pitch_degrees: float | None = None


class SolarLayoutOut(_CamelModel):
    """Google's own panel layout for this rooftop, for drawing over the
    satellite imagery.

    Deliberately NOT a capacity result. `panel_count`/`total_kwp` describe
    Google's layout only; the assessment's recommended kWp is P2's figure
    from usable area, arrived at a different way, and the two disagree.
    The frontend labels this overlay as Google's so the two are never
    read as one number.
    """

    status: str  # ok | no_coverage | no_layout | error
    reason: str | None = None
    source: str = "Google Solar API"
    panel_count: int = 0
    total_kwp: float = 0.0
    panels: list[SolarPanelOut] = Field(default_factory=list)


@router.get("/checks/{check_id}/solar-layout", response_model=SolarLayoutOut)
def get_check_solar_layout(
    check_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> SolarLayoutOut:
    """The real per-panel layout at this check's location.

    Separate from GET /checks/{id} on purpose: it costs a Solar API call,
    it is presentation-only, and a failure here must never take the
    result page's verdict or capacity down with it. Non-ok statuses come
    back as 200 with an explicit reason — the overlay is absent, which is
    information, not a request error.
    """
    site, _row = _owned_check_or_404(session, check_id, _individual_owner_org(user))
    lng, lat = site.centroid["coordinates"]

    layout = fetch_panel_layout(lat, lng)
    return SolarLayoutOut(
        status=layout.status,
        reason=layout.reason,
        panel_count=len(layout.panels),
        total_kwp=round(layout.total_kwp, 2),
        panels=[
            SolarPanelOut(
                corners=[PanelCornerOut(lat=c_lat, lng=c_lng) for c_lng, c_lat in p.corners],
                capacity_watts=p.capacity_watts,
                orientation=p.orientation,
                segment_index=p.segment_index,
                azimuth_degrees=p.azimuth_degrees,
                pitch_degrees=p.pitch_degrees,
            )
            for p in layout.panels
        ],
    )


class RoofObstacleOut(_CamelModel):
    id: str
    polygon: list[PanelCornerOut]


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
    _site, _row = _owned_check_or_404(session, check_id, _individual_owner_org(user))
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

    obstacles: list[RoofObstacleOut] = []
    for obstacle_id, polygon in found:
        ring = ((polygon or {}).get("coordinates") or [[]])[0]
        points = [PanelCornerOut(lat=lat, lng=lng) for lng, lat in ring]
        if len(points) >= 3:
            obstacles.append(RoofObstacleOut(id=obstacle_id, polygon=points))

    return RoofObstaclesOut(detected=True, obstacles=obstacles)


class SaveCheckBoundaryRequest(_CamelModel):
    points: list[PanelCornerOut] = Field(min_length=3)


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

    Validation, versioning and provenance are identical: GEO-07/08 via
    manual.resolve_manual, then a new SITE-05 version recorded as
    `manual_polygon`. That outranks GEO-04's `solar_api` rectangle
    (precedence 300 vs 100), so from here on every assessment measures
    the traced roof instead of the bounding box.
    """
    _site, _row = _owned_check_or_404(session, check_id, _individual_owner_org(user))

    boundary_geojson = {
        "type": "Polygon",
        # A GeoJSON ring must close; the UI sends the open path it edits.
        "coordinates": [
            [[p.lng, p.lat] for p in payload.points]
            + [[payload.points[0].lng, payload.points[0].lat]]
        ],
    }
    try:
        validated = manual.resolve_manual(_site, {"boundary": boundary_geojson})
    except GeometryRejected as exc:
        # A self-intersecting or degenerate trace is the customer's input
        # to fix, not a server fault — and never silently repaired.
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    updated_site = repo.new_geometry_version(
        session,
        check_id,
        boundary=validated,
        actor=user.email,
        source="manual_edit",
        geometry_source="manual_polygon",
    )
    updated_row = session.get(repo.SiteRow, uuid.UUID(check_id))
    return _site_out(session, updated_site, updated_row)


@router.post("/checks", response_model=SiteOut, status_code=status.HTTP_201_CREATED)
def create_check(
    payload: NewCheckInput,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> SiteOut:
    owner_org = _individual_owner_org(user)
    core_payload = SiteCreate(
        site_type=payload.site_type,
        name=payload.address,
        jurisdiction=_DEFAULT_JURISDICTION,
        address=payload.address,
        centroid={"type": "Point", "coordinates": [payload.lng, payload.lat]},
    )
    try:
        site, _note = create_site_core(
            core_payload,
            session,
            owner_org,
            address=payload.address,
            monthly_bill_low_inr=payload.monthly_bill_low_inr,
            monthly_bill_high_inr=payload.monthly_bill_high_inr,
        )
    except solar_api.SolarApiError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    row = session.get(repo.SiteRow, uuid.UUID(site.id))
    return _site_out(session, site, row)


@router.post("/checks/{check_id}/complete", response_model=SiteOut)
def complete_check(
    check_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> SiteOut:
    """Runs the real engine (routers/assessments.py::orchestrate_assessment,
    unchanged) and persists the result — never a fabricated verdict.

    A SUITABLE_SUBJECT_TO_SURVEY verdict also queues an unassigned vendor
    job in the same transaction as the assessment save (repositories/
    vendors.py::create_job()) — this is the only path that populates
    vendor_jobs today, closing the "no frontend flow assigns a vendor to a
    site" gap that repository's own docstring used to flag."""
    owner_org = _individual_owner_org(user)
    site, row = _owned_check_or_404(session, check_id, owner_org)

    try:
        response = orchestrate_assessment(check_id)
    except SiteNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except GeometryRejected as exc:
        # GEO-04: no Solar API coverage at this location. Google covers
        # India building-by-building, so this is ordinary here, not an
        # error on our side — a 500 both misreports it and leaves the
        # customer's processing screen spinning with nothing to show.
        # The check row survives; it needs a boundary from a source that
        # outranks solar_api (a manual trace, GEO-02).
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "We couldn't find automatic roof data for this location. "
            "Draw the roof outline on the map to continue.",
        ) from exc

    with session_scope() as assessment_session:
        assessments_repo.save_assessment(
            assessment_session, owner_org=owner_org, **response.model_dump()
        )

        if response.verdict == _SURVEY_VERDICT:
            vendors_repo.create_job(
                assessment_session,
                site_id=check_id,
                district=row.district or "Unassigned",
                state=row.state or "Unassigned",
                requirements=_survey_requirements(site.site_type),
                payout_inr=max(
                    _MIN_SURVEY_PAYOUT_INR,
                    round((response.capacity.recommended_kwp or 3) * _PAYOUT_PER_KWP_INR),
                ),
                estimated_capacity_kwp=response.capacity.recommended_kwp,
                deadline=datetime.now(UTC) + timedelta(days=_SURVEY_DEADLINE_DAYS),
            )

        assessment_session.commit()

    updated_row = session.get(repo.SiteRow, uuid.UUID(check_id))
    return _site_out(session, site, updated_row)


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
