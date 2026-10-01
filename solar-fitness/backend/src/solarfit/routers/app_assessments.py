"""Owner: omkar (Scoring, USN & Assessment API).

Roadmap workstream "Assessments, frontend-shaped & secured" — 2
endpoints. Wraps routers/assessments.py::orchestrate_assessment()
UNCHANGED (no new computation), adds auth + persistence + a
frontend-shaped response.

Real mapping gaps, flagged not guessed at (per the roadmap's own note):
  - confidence bucket: no threshold exists anywhere upstream — this
    file sets one explicitly (N/A when score is None, High >= 0.7,
    Medium >= 0.4, else Low).
  - bindingConstraint {name, reason, kind}: the backend only has a bare
    constraint-name string; matched against capacity.ceilings to pull
    reason/kind. Gate failures and "insufficient_data:..." sentinels
    aren't in the ceiling list — synthesized as {name, reason: <the
    detail text already on the AssessmentResponse>, kind: "physical"}
    rather than crashing on a lookup miss.
  - visionRefinement.deltaKwp: no such number exists in the backend at
    all — omitted, not sent as a fabricated value.
  - generation: engine/generation.py::estimate_generation_kwh() was
    already computed on every assessment (it feeds fitness.score_fitness())
    and silently discarded — now persisted and exposed for real
    (estimatedKwhPerYear/specificYieldKwhPerKwp/performanceRatio/method).
    p50/p90 remain None (GEN-06, still deferred in the engine itself).
  - cache.originalDate: AnalysisResult (the frozen contract) has no
    created_at field, and repositories/analysis_cache.py exposes no
    public lookup that would provide one without reaching into another
    person's private ORM row — omitted, not hacked around.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from solarfit.auth_users import AuthenticatedUser, current_user, require_permission, require_role
from solarfit.db import get_session, session_scope
from solarfit.domain.constraint import CapacityResult
from solarfit.repositories import assessments as assessments_repo
from solarfit.repositories import audit as audit_repo
from solarfit.repositories import notifications as notifications_repo
from solarfit.repositories import sites as sites_repo
from solarfit.repositories import vendors as vendors_repo
from solarfit.repositories.sites import SiteRow
from solarfit.routers.assessments import (
    AssessmentResponse,
    FinancialEstimateOut,
    GenerationEstimateOut,
    SiteNotFoundError,
    orchestrate_assessment,
)
from solarfit.routers.common import actor_audit_fields, request_audit_meta

router = APIRouter(tags=["app-assessments"])

ConfidenceLabel = Literal["High", "Medium", "Low", "N/A"]


def _to_camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(word.capitalize() for word in rest)


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)


class BindingConstraintOut(_CamelModel):
    name: str
    reason: str
    kind: str


class AppAssessmentResponse(_CamelModel):
    id: str
    site_id: str
    site_type: str

    verdict: str
    score: float | None
    confidence: ConfidenceLabel
    binding_constraint: BindingConstraintOut
    reasons: list[str]
    conditions: list[dict] = []
    limitations: str

    capacity: CapacityResult
    boundary: dict
    usable_area_m2: float | None

    vision_refinement: dict | None
    panorama_url: str | None
    ml_suitability_score: float | None
    ml_model_version: str | None
    cache_hit: bool

    engine_version: str
    constraint_pack_version: str
    created_at: str
    generation: GenerationEstimateOut | None = None
    financial_estimate: FinancialEstimateOut | None = None


class CeilingLedgerEntryOut(BaseModel):
    """Deliberately NOT a _CamelModel — keys are already camelCase from
    assessments_repo.ceiling_ledger_list() (see that function's
    docstring for why), and re-aliasing them here would double-apply
    camelCase-of-camelCase and break the field names."""

    model_config = ConfigDict(populate_by_name=True)

    label: str
    kwp: float | None
    kind: str
    note: str
    status: str
    isBinding: bool = Field(alias="isBinding")


ReviewStatus = Literal["not_submitted", "pending", "approved", "rejected", "not_applicable"]


class ReviewFieldsOut(_CamelModel):
    review_status: ReviewStatus
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    rejection_reason: str | None = None
    assigned_vendor_id: str | None = None
    vendor_job_id: str | None = None
    # Enquiry workflow — the customer's own action, distinct from the
    # admin's approve/reject/reassign action above.
    customer_selected_vendor_id: str | None = None
    enquiry_submitted_at: str | None = None
    # A district-matched vendor hint (repositories/vendors.py::
    # best_available_vendor_for_district()) — real matching logic, shown
    # only when no customer selection exists to prefill from instead.
    # None when nothing matches, never a guessed vendor.
    suggested_vendor_id: str | None = None


class SiteSummaryOut(_CamelModel):
    site_name: str
    address: str | None
    district: str
    state: str


class AssessmentListItem(AppAssessmentResponse, ReviewFieldsOut, SiteSummaryOut):
    owner_org: str


GridConnectionStatus = Literal[
    "not_started", "application_submitted", "under_review", "approved", "connected", "rejected"
]


class GridFeasibilityOut(_CamelModel):
    """Spec section 15 — admin-owned DISCOM policy/application tracking.
    Not computed: this is real-world grid-operator state an admin has
    to look up or negotiate, same reasoning as service_api_keys being
    display-only rather than fabricated."""

    discom: str | None = None
    distribution_area: str | None = None
    net_metering_available: bool | None = None
    gross_metering_available: bool | None = None
    application_required: bool | None = None
    grid_approval_required: bool | None = None
    transformer_capacity_kva: float | None = None
    max_permissible_capacity_kwp: float | None = None
    grid_connection_status: GridConnectionStatus = "not_started"
    application_reference: str | None = None
    notes: str | None = None


class FinancialFeasibilityOut(_CamelModel):
    """Spec section 16 — real quotes/negotiated commercial figures, same
    "admin enters it, engine doesn't fabricate it" reasoning as
    GridFeasibilityOut."""

    panel_cost_inr: float | None = None
    inverter_cost_inr: float | None = None
    mounting_structure_cost_inr: float | None = None
    dc_cable_cost_inr: float | None = None
    ac_cable_cost_inr: float | None = None
    protection_equipment_cost_inr: float | None = None
    installation_cost_inr: float | None = None
    civil_work_cost_inr: float | None = None
    transportation_cost_inr: float | None = None
    other_charges_inr: float | None = None
    total_project_cost_inr: float | None = None
    subsidy_applicable: bool | None = None
    subsidy_category: str | None = None
    subsidy_amount_inr: float | None = None
    customer_contribution_inr: float | None = None
    monthly_savings_inr: float | None = None
    annual_savings_inr: float | None = None
    payback_period_years: float | None = None
    ten_year_savings_inr: float | None = None
    twenty_year_savings_inr: float | None = None
    estimated_system_lifetime_years: float | None = None
    notes: str | None = None


class AssessmentDetailOut(AppAssessmentResponse, ReviewFieldsOut, SiteSummaryOut):
    owner_org: str
    checklist: list[CeilingLedgerEntryOut]
    grid_feasibility: GridFeasibilityOut | None = None
    financial_feasibility: FinancialFeasibilityOut | None = None


class ApproveAssessmentRequest(_CamelModel):
    vendor_id: str
    deadline_days: int = Field(default=3, ge=1, le=30)
    payout_inr: float | None = None


class RejectAssessmentRequest(_CamelModel):
    reason: str = Field(min_length=1)


class ReassignAssessmentRequest(_CamelModel):
    vendor_id: str
    deadline_days: int = Field(default=3, ge=1, le=30)
    reason: str | None = None


def _confidence_label(score: float | None, confidence: float) -> ConfidenceLabel:
    if score is None:
        return "N/A"
    if confidence >= 0.7:
        return "High"
    if confidence >= 0.4:
        return "Medium"
    return "Low"


def _binding_constraint_out(response: AssessmentResponse) -> BindingConstraintOut:
    name = response.binding_constraint
    for ceiling in response.capacity.ceilings:
        if ceiling.constraint == name:
            return BindingConstraintOut(name=name, reason=ceiling.reason, kind=ceiling.kind)
    # Gate failures ("gate:...") and "insufficient_data:..." sentinels
    # aren't in the ceiling list — synthesize from what we do have
    # rather than treating a lookup miss as an error.
    detail = next((r for r in response.reasons if name.split(":")[-1] in r), response.reasons[0])
    return BindingConstraintOut(name=name, reason=detail, kind="physical")


def _to_app_response(row_id: str, response: AssessmentResponse, created_at) -> AppAssessmentResponse:
    return AppAssessmentResponse(
        id=row_id,
        site_id=response.site_id,
        site_type=response.site_type,
        verdict=response.verdict,
        score=response.score,
        confidence=_confidence_label(response.score, response.confidence),
        binding_constraint=_binding_constraint_out(response),
        reasons=response.reasons,
        conditions=[c.model_dump() for c in response.conditions],
        limitations=response.limitations,
        capacity=response.capacity,
        boundary=response.boundary,
        usable_area_m2=response.usable_area_m2,
        vision_refinement=response.vision_refinement.model_dump() if response.vision_refinement else None,
        panorama_url=response.panorama_url,
        ml_suitability_score=response.ml_suitability_score,
        ml_model_version=response.ml_model_version,
        cache_hit=response.cache_hit,
        engine_version=response.engine_version,
        constraint_pack_version=response.constraint_pack_version,
        created_at=created_at.isoformat(),
        generation=response.generation,
        financial_estimate=response.financial_estimate,
    )


def _site_summary(session: Session, site_id: str) -> SiteSummaryOut:
    try:
        site_row = session.get(SiteRow, uuid.UUID(site_id))
    except ValueError:
        site_row = None
    if site_row is None:
        return SiteSummaryOut(site_name=site_id, address=None, district="", state="")
    return SiteSummaryOut(
        site_name=site_row.name,
        address=site_row.address,
        district=site_row.district or "",
        state=site_row.state or "",
    )


def _review_fields(row, session: Session | None = None) -> ReviewFieldsOut:
    suggested_vendor_id = None
    if (
        session is not None
        and row.review_status in ("pending", "not_submitted")
        and row.customer_selected_vendor_id is None
    ):
        site_summary = _site_summary(session, row.site_id)
        if site_summary.district:
            already_tried = {str(row.assigned_vendor_id)} if row.assigned_vendor_id else set()
            suggestion = vendors_repo.best_available_vendor_for_district(
                session, site_summary.district, exclude_ids=already_tried
            )
            suggested_vendor_id = str(suggestion.id) if suggestion else None
    return ReviewFieldsOut(
        review_status=row.review_status,
        reviewed_by=row.reviewed_by,
        reviewed_at=row.reviewed_at.isoformat() if row.reviewed_at else None,
        rejection_reason=row.rejection_reason,
        assigned_vendor_id=str(row.assigned_vendor_id) if row.assigned_vendor_id else None,
        vendor_job_id=str(row.vendor_job_id) if row.vendor_job_id else None,
        customer_selected_vendor_id=str(row.customer_selected_vendor_id)
        if row.customer_selected_vendor_id
        else None,
        enquiry_submitted_at=row.enquiry_submitted_at.isoformat() if row.enquiry_submitted_at else None,
        suggested_vendor_id=suggested_vendor_id,
    )


@router.post("/app/assessments/{site_id}", response_model=AppAssessmentResponse)
def post_app_assessment(
    site_id: str,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> AppAssessmentResponse:
    """Runs the real engine unchanged, then persists the result.
    A customer may only assess their own org's sites; an admin may
    assess any site — mirrors repositories/sites.py::list_sites()'s
    owner_org-scoping pattern already established for GET /app/sites."""
    with session_scope() as read_session:
        site = sites_repo.get(read_session, site_id)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Site {site_id} not found")
    if user.role != "admin" and site.owner_org != user.owner_org:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Site {site_id} not found")

    try:
        response = orchestrate_assessment(site_id)
    except SiteNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    with session_scope() as session:
        row = assessments_repo.save_assessment(
            session,
            owner_org=site.owner_org,
            **response.model_dump(),
        )
        session.commit()
        row_id, created_at = row.id, row.created_at

    return _to_app_response(row_id, response, created_at)


@router.get("/app/admin/assessments", response_model=list[AssessmentListItem])
def list_all_assessments(
    user: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
    limit: int = 50,
    offset: int = 0,
) -> list[AssessmentListItem]:
    """Cross-org, admin-only — reads the table post_app_assessment()
    writes above."""
    del user
    with session_scope() as session:
        rows = assessments_repo.list_assessments(session, owner_org=None, limit=limit, offset=offset)
        results = []
        for row in rows:
            response = AssessmentResponse(
                site_id=row.site_id,
                site_type=row.site_type,
                verdict=row.verdict,
                score=row.score,
                confidence=row.confidence,
                binding_constraint=row.binding_constraint,
                reasons=row.reasons,
                conditions=row.conditions or [],
                limitations=row.limitations,
                capacity=CapacityResult(**row.capacity),
                boundary=row.boundary,
                usable_area_m2=row.usable_area_m2,
                vision_refinement=row.vision_refinement,
                panorama_url=row.panorama_url,
                ml_suitability_score=row.ml_suitability_score,
                ml_model_version=row.ml_model_version,
                cache_hit=row.cache_hit,
                reused_from_analysis_id=row.reused_from_analysis_id,
                usn=row.usn,
                engine_version=row.engine_version,
                constraint_pack_version=row.constraint_pack_version,
                generation=row.generation,
                financial_estimate=row.financial_estimate,
            )
            item = _to_app_response(row.id, response, row.created_at)
            results.append(
                AssessmentListItem(
                    owner_org=row.owner_org,
                    **item.model_dump(by_alias=False),
                    **_review_fields(row, session).model_dump(by_alias=False),
                    **_site_summary(session, row.site_id).model_dump(by_alias=False),
                )
            )
        return results


@router.get("/app/admin/assessments/{assessment_id}", response_model=AssessmentDetailOut)
def get_admin_assessment(
    assessment_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> AssessmentDetailOut:
    """The admin review screen's data source: the real verdict, capacity,
    and the full per-constraint checklist the resolver actually
    evaluated (assessments_repo.ceiling_ledger_list()) — grounded in what
    the engine computed, not a separately hand-maintained checklist."""
    del user
    with session_scope() as session:
        row = assessments_repo.get_assessment(session, assessment_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "assessment not found")

        response = AssessmentResponse(
            site_id=row.site_id,
            site_type=row.site_type,
            verdict=row.verdict,
            score=row.score,
            confidence=row.confidence,
            binding_constraint=row.binding_constraint,
            reasons=row.reasons,
            conditions=row.conditions or [],
            limitations=row.limitations,
            capacity=CapacityResult(**row.capacity),
            boundary=row.boundary,
            usable_area_m2=row.usable_area_m2,
            vision_refinement=row.vision_refinement,
            panorama_url=row.panorama_url,
            ml_suitability_score=row.ml_suitability_score,
            ml_model_version=row.ml_model_version,
            cache_hit=row.cache_hit,
            reused_from_analysis_id=row.reused_from_analysis_id,
            usn=row.usn,
            engine_version=row.engine_version,
            constraint_pack_version=row.constraint_pack_version,
            generation=row.generation,
            financial_estimate=row.financial_estimate,
        )
        item = _to_app_response(row.id, response, row.created_at)
        checklist = [CeilingLedgerEntryOut(**c) for c in assessments_repo.ceiling_ledger_list(row)]
        return AssessmentDetailOut(
            owner_org=row.owner_org,
            checklist=checklist,
            grid_feasibility=GridFeasibilityOut(**row.grid_feasibility) if row.grid_feasibility else None,
            financial_feasibility=FinancialFeasibilityOut(**row.financial_feasibility) if row.financial_feasibility else None,
            **item.model_dump(by_alias=False),
            **_review_fields(row, session).model_dump(by_alias=False),
            **_site_summary(session, row.site_id).model_dump(by_alias=False),
        )


@router.post("/app/admin/assessments/{assessment_id}/approve", response_model=AssessmentDetailOut)
def approve_assessment(
    assessment_id: str,
    payload: ApproveAssessmentRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_permission("PROJECT_APPROVE"))],
) -> AssessmentDetailOut:
    """The one gate the whole review workflow exists for: Customer ->
    Feasibility Check -> Admin Review -> Admin Approval -> Vendor Access.
    Creates the vendor_jobs row (assigned to the chosen vendor, visible
    to them immediately) and links it back onto the assessment in one
    transaction, then writes an audit-log entry the same way every other
    admin-mutating endpoint in this codebase does."""
    row = assessments_repo.get_assessment(session, assessment_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assessment not found")
    if row.review_status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, f"assessment is already {row.review_status}, not pending review")

    vendor_row = vendors_repo.get_vendor(session, payload.vendor_id)
    if vendor_row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vendor not found")

    site_summary = _site_summary(session, row.site_id)
    payout_inr = payload.payout_inr
    if payout_inr is None:
        payout_inr = vendors_repo.default_survey_payout_inr(row.capacity.get("recommended_kwp"))

    job = vendors_repo.create_job(
        session,
        site_id=row.site_id,
        district=site_summary.district or "Unassigned",
        state=site_summary.state or "Unassigned",
        requirements=vendors_repo.default_survey_requirements(row.site_type),
        payout_inr=payout_inr,
        estimated_capacity_kwp=row.capacity.get("recommended_kwp"),
        deadline=datetime.now(UTC) + timedelta(days=payload.deadline_days),
        vendor_id=payload.vendor_id,
        status="queued",
    )

    assessments_repo.approve_assessment(
        session,
        assessment_id,
        admin_email=admin.email,
        vendor_id=payload.vendor_id,
        vendor_job_id=job.id,
    )
    audit_repo.write_audit_log(
        session,
        **actor_audit_fields(admin),
        action="assessment.approved",
        target=assessment_id,
        details=f"{admin.email} approved site {row.site_id} for vendor {vendor_row.name} (job {job.id})",
        entity_type="assessment",
        project_id=row.site_id,
        survey_id=assessment_id,
        customer_id=str(row.raised_by_user_id) if row.raised_by_user_id else row.owner_org,
        vendor_id=payload.vendor_id,
        previous_value={"reviewStatus": "pending"},
        new_value={"reviewStatus": "approved", "vendorId": payload.vendor_id, "vendorJobId": str(job.id)},
        **request_audit_meta(request),
    )
    vendors_repo.notify_vendor_users(
        session,
        payload.vendor_id,
        preference_key="new_job_assignment",
        kind="job_assigned",
        title="A new job has been assigned to you",
        body=f"Job in {site_summary.district or 'an unassigned district'}, {site_summary.state or ''}.",
    )
    if row.raised_by_user_id is not None:
        notifications_repo.create_notification(
            session,
            user_id=row.raised_by_user_id,
            kind="vendor_request_approved",
            title="Your vendor request was approved",
            body=f"{vendor_row.name} has been assigned to your site.",
        )
    session.commit()
    return get_admin_assessment(assessment_id, admin)


@router.post("/app/admin/assessments/{assessment_id}/reject", response_model=AssessmentDetailOut)
def reject_assessment(
    assessment_id: str,
    payload: RejectAssessmentRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_permission("PROJECT_REJECT"))],
) -> AssessmentDetailOut:
    row = assessments_repo.get_assessment(session, assessment_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assessment not found")
    if row.review_status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, f"assessment is already {row.review_status}, not pending review")

    assessments_repo.reject_assessment(session, assessment_id, admin_email=admin.email, reason=payload.reason)
    audit_repo.write_audit_log(
        session,
        **actor_audit_fields(admin),
        action="assessment.rejected",
        target=assessment_id,
        details=f"{admin.email} rejected site {row.site_id}: {payload.reason}",
        entity_type="assessment",
        project_id=row.site_id,
        survey_id=assessment_id,
        customer_id=str(row.raised_by_user_id) if row.raised_by_user_id else row.owner_org,
        previous_value={"reviewStatus": "pending"},
        new_value={"reviewStatus": "rejected"},
        reason=payload.reason,
        **request_audit_meta(request),
    )
    if row.raised_by_user_id is not None:
        notifications_repo.create_notification(
            session,
            user_id=row.raised_by_user_id,
            kind="vendor_request_rejected",
            title="Your vendor request was not approved",
            body=payload.reason,
        )
    session.commit()
    return get_admin_assessment(assessment_id, admin)


@router.post("/app/admin/assessments/{assessment_id}/reassign", response_model=AssessmentDetailOut)
def reassign_assessment(
    assessment_id: str,
    payload: ReassignAssessmentRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_permission("PROJECT_APPROVE"))],
) -> AssessmentDetailOut:
    """Changes an already-approved assessment's vendor — the gap the
    approve/reject panel alone can't close: once approved, there was no
    way to move the job to a different vendor short of rejecting the
    whole assessment and starting over (losing the approval history).

    Reuses the exact reassignment pattern the SLA sweep
    (repositories/vendors.py::sweep_vendor_job_sla) already established
    on the SAME vendor_jobs row, rather than creating a second one: the
    old vendor moves into previous_vendor_ids, the row's vendor_id
    changes, and status resets to "queued" with a fresh deadline so the
    new vendor sees it as a normal live job, not damaged goods. The
    site's surveyJobStatus link never breaks since it's still the same
    job id."""
    row = assessments_repo.get_assessment(session, assessment_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assessment not found")
    if row.review_status != "approved":
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"assessment is {row.review_status}, not approved — nothing to reassign"
        )
    if row.vendor_job_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "assessment has no vendor job to reassign")

    new_vendor_row = vendors_repo.get_vendor(session, payload.vendor_id)
    if new_vendor_row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vendor not found")
    if new_vendor_row.verification_status != "verified":
        raise HTTPException(status.HTTP_409_CONFLICT, "vendor is not verified")

    job = session.get(vendors_repo.VendorJobRow, row.vendor_job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vendor job not found")

    old_vendor_id = job.vendor_id
    if old_vendor_id is not None:
        job.previous_vendor_ids = [*job.previous_vendor_ids, str(old_vendor_id)]
    job.vendor_id = uuid.UUID(str(payload.vendor_id))
    job.status = "queued"
    job.deadline = datetime.now(UTC) + timedelta(days=payload.deadline_days)
    session.flush()

    assessments_repo.reassign_assessment_vendor(
        session, assessment_id, admin_email=admin.email, vendor_id=payload.vendor_id
    )
    audit_repo.write_audit_log(
        session,
        **actor_audit_fields(admin),
        action="assessment.reassigned",
        target=assessment_id,
        details=(
            f"{admin.email} reassigned site {row.site_id} from vendor "
            f"{old_vendor_id or 'none'} to {new_vendor_row.name} (job {job.id})"
            + (f" — {payload.reason}" if payload.reason else "")
        ),
        entity_type="assessment",
        project_id=row.site_id,
        survey_id=assessment_id,
        customer_id=str(row.raised_by_user_id) if row.raised_by_user_id else row.owner_org,
        vendor_id=payload.vendor_id,
        previous_value={"vendorId": str(old_vendor_id) if old_vendor_id else None},
        new_value={"vendorId": payload.vendor_id},
        reason=payload.reason,
        **request_audit_meta(request),
    )
    vendors_repo.notify_vendor_users(
        session,
        payload.vendor_id,
        preference_key="job_reassignment",
        kind="job_reassigned_to_you",
        title="A job has been reassigned to you",
        body=f"Job in {job.district}, {job.state}.",
    )
    if row.raised_by_user_id is not None:
        notifications_repo.create_notification(
            session,
            user_id=row.raised_by_user_id,
            kind="vendor_request_reassigned",
            title="Your assigned vendor has changed",
            body=f"{new_vendor_row.name} is now assigned to your site.",
        )
    session.commit()
    return get_admin_assessment(assessment_id, admin)


@router.patch("/app/admin/assessments/{assessment_id}/grid-feasibility", response_model=AssessmentDetailOut)
def save_grid_feasibility(
    assessment_id: str,
    payload: GridFeasibilityOut,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> AssessmentDetailOut:
    """Spec section 15. Not gated on review_status — DISCOM application
    tracking is a real-world process an admin updates over time (after
    approval, after connection), unlike approve/reject which are
    one-time decisions."""
    row = assessments_repo.get_assessment(session, assessment_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assessment not found")

    previous_grid_feasibility = row.grid_feasibility
    assessments_repo.set_grid_feasibility(session, assessment_id, feasibility=payload.model_dump(by_alias=False))
    audit_repo.write_audit_log(
        session,
        **actor_audit_fields(admin),
        action="assessment.grid_feasibility_updated",
        target=assessment_id,
        details=f"{admin.email} updated grid/DISCOM feasibility for site {row.site_id}",
        entity_type="assessment",
        project_id=row.site_id,
        survey_id=assessment_id,
        customer_id=str(row.raised_by_user_id) if row.raised_by_user_id else row.owner_org,
        vendor_id=str(row.assigned_vendor_id) if row.assigned_vendor_id else None,
        previous_value=previous_grid_feasibility,
        new_value=payload.model_dump(by_alias=False),
        **request_audit_meta(request),
    )
    session.commit()
    return get_admin_assessment(assessment_id, admin)


@router.patch("/app/admin/assessments/{assessment_id}/financial-feasibility", response_model=AssessmentDetailOut)
def save_financial_feasibility(
    assessment_id: str,
    payload: FinancialFeasibilityOut,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> AssessmentDetailOut:
    """Spec section 16 (final phase)."""
    row = assessments_repo.get_assessment(session, assessment_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "assessment not found")

    previous_financial_feasibility = row.financial_feasibility
    assessments_repo.set_financial_feasibility(session, assessment_id, feasibility=payload.model_dump(by_alias=False))
    audit_repo.write_audit_log(
        session,
        **actor_audit_fields(admin),
        action="assessment.financial_feasibility_updated",
        target=assessment_id,
        details=f"{admin.email} updated financial feasibility for site {row.site_id}",
        entity_type="assessment",
        project_id=row.site_id,
        survey_id=assessment_id,
        customer_id=str(row.raised_by_user_id) if row.raised_by_user_id else row.owner_org,
        vendor_id=str(row.assigned_vendor_id) if row.assigned_vendor_id else None,
        previous_value=previous_financial_feasibility,
        new_value=payload.model_dump(by_alias=False),
        **request_audit_meta(request),
    )
    session.commit()
    return get_admin_assessment(assessment_id, admin)
