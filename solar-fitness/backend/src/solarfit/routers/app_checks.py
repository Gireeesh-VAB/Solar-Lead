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
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import Field
from sqlalchemy.orm import Session

from solarfit.auth_users import AuthenticatedUser, current_user
from solarfit.db import get_session, session_scope
from solarfit.domain.site import RoofSiteType
from solarfit.providers import solar_api
from solarfit.repositories import assessments as assessments_repo
from solarfit.repositories import sites as repo
from solarfit.repositories import users as users_repo
from solarfit.routers.app_sites import SiteOut, _CamelModel, _site_out
from solarfit.routers.assessments import SiteNotFoundError, orchestrate_assessment
from solarfit.routers.sites import SiteCreate, create_site_core

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


class NewCheckInput(_CamelModel):
    address: str = Field(min_length=1)
    lat: float
    lng: float
    site_type: RoofSiteType = "ROOFTOP_RESIDENTIAL"

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

    Deliberately does NOT touch vendor_jobs. Customer -> Feasibility Check
    -> Admin Review -> Admin Approval -> Vendor Access: a
    SUITABLE_SUBJECT_TO_SURVEY (or SUITABLE) verdict lands the assessment
    in the admin review queue (assessments_repo.save_assessment() sets
    review_status="pending" for those verdicts) — a vendor job only ever
    gets created once an admin explicitly approves and picks a vendor, via
    routers/app_assessments.py::approve_assessment(). Previously this
    endpoint created an unassigned vendor_jobs row itself with no admin
    involved at all, and that row was permanently invisible to every
    vendor anyway (see repositories/vendors.py::create_job()'s docstring)."""
    owner_org = _individual_owner_org(user)
    site, _row = _owned_check_or_404(session, check_id, owner_org)

    try:
        response = orchestrate_assessment(check_id)
    except SiteNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    with session_scope() as assessment_session:
        assessments_repo.save_assessment(assessment_session, owner_org=owner_org, **response.model_dump())
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
