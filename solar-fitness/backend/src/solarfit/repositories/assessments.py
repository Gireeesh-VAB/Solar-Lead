"""Owner: omkar (Scoring, USN & Assessment API).

Roadmap workstream "Assessments, frontend-shaped & secured" — persists
exactly what routers/assessments.py::orchestrate_assessment() already
computes. No new computation happens here; this is pure storage, same
providers/(compute) vs repositories/(persist) split as USN capture and
the ML pipeline.

No FK to sites — site_id is a plain indexed string, matching the
deferred-FK pattern already used elsewhere in this schema before a
target table existed (though sites does exist now; kept consistent
with calibration_records/ml_training_samples rather than mixing FK and
non-FK conventions across this person's own tables).
"""

import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, String, func, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, Session, mapped_column

from solarfit.db import Base

# Customer -> Feasibility Check -> Admin Review -> Admin Approval -> Vendor
# Access: only these two verdicts can ever lead to vendor field work, so
# only they enter the review queue. Everything else (CONDITIONAL,
# INSUFFICIENT_DATA, NOT_SUITABLE) is "not_applicable" — there is nothing
# for an admin to approve a vendor onto.
REVIEW_ELIGIBLE_VERDICTS = ("SUITABLE", "SUITABLE_SUBJECT_TO_SURVEY")


class AssessmentRow(Base):
    __tablename__ = "assessments"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    site_id: Mapped[str] = mapped_column(String, index=True)
    owner_org: Mapped[str] = mapped_column(String, index=True)
    site_type: Mapped[str] = mapped_column(String)

    verdict: Mapped[str] = mapped_column(String)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float] = mapped_column(Float)
    binding_constraint: Mapped[str] = mapped_column(String)
    reasons: Mapped[list] = mapped_column(JSON)
    # Phase 6 — domain/assessment.py::Condition dicts (code/message/detail).
    # Additive: an older row predating this has conditions=None, read back
    # as an empty list by to_frontend_assessment_dict() below.
    conditions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    limitations: Mapped[str] = mapped_column(String)

    capacity: Mapped[dict] = mapped_column(JSON)
    boundary: Mapped[dict] = mapped_column(JSON)
    usable_area_m2: Mapped[float | None] = mapped_column(Float, nullable=True)
    # AREA-01, pre-setback/pre-exclusion — engine/area.py::boundary_area_m2().
    # Distinct from usable_area_m2 above: total minus usable is real,
    # displayable "non-usable" area (setback + exclusions), not a guess.
    total_area_m2: Mapped[float | None] = mapped_column(Float, nullable=True)
    # engine/fitness.py::score_fitness()'s own FitnessResult.components —
    # the per-factor breakdown (capacity_adequacy, constraint_headroom,
    # geometry_quality, shading, generation_yield) behind the single
    # blended `score` above. Was computed on every assessment and
    # discarded until now, same "real number, just never persisted"
    # story as `generation` below.
    score_components: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # FIT-04 explainability — engine/fitness.py::FitnessResult's own
    # confidence_components (per-factor values blended into `confidence`
    # above) and confidence_explanation (deterministic, template-generated
    # sentences derived from them). Same "real number, just never
    # persisted" story as score_components above.
    confidence_components: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence_explanation: Mapped[list | None] = mapped_column(JSON, nullable=True)

    vision_refinement: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    panorama_url: Mapped[str | None] = mapped_column(String, nullable=True)
    ml_suitability_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ml_model_version: Mapped[str | None] = mapped_column(String, nullable=True)
    cache_hit: Mapped[bool] = mapped_column(Boolean)
    reused_from_analysis_id: Mapped[str | None] = mapped_column(String, nullable=True)
    usn: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    engine_version: Mapped[str] = mapped_column(String)
    constraint_pack_version: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # engine/generation.py::estimate_generation_kwh()'s real output —
    # was computed on every assessment and discarded until now (see
    # routers/assessments.py::GenerationEstimateOut's docstring).
    generation: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # engine/financials.py::estimate_financials()'s real output — an
    # engine ESTIMATE (config-pack cost/kWp, subsidy scheme, tariff),
    # distinct from financial_feasibility below (an admin-entered real
    # quote). Same relationship as generation sits beside the admin-owned
    # fields.
    financial_estimate: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Admin review workflow (Customer -> Feasibility Check -> Admin Review ->
    # Admin Approval -> Vendor Access). "pending" | "approved" | "rejected" |
    # "not_applicable" (verdict never eligible for vendor work).
    review_status: Mapped[str] = mapped_column(String(16), nullable=False, default="not_applicable")
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    assigned_vendor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    vendor_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Spec section 15 "Grid / DISCOM Feasibility" — admin-owned workflow
    # state (net/gross metering availability, transformer capacity,
    # application/approval status), evolves alongside review_status as
    # the project moves through DISCOM approval. Not something a
    # customer or field vendor can determine.
    grid_feasibility: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Spec section 16 "Financial Feasibility" (final phase) — system
    # cost breakdown, subsidy, and ROI figures. Admin-owned real quotes/
    # negotiated commercial data, same reasoning as grid_feasibility:
    # not something the engine computes or fabricates.
    financial_feasibility: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # engine/panel_packing.py's real, obstacle/boundary-aware layout —
    # see routers/assessments.py::_pack_panel_layout()'s docstring. Was
    # previously not persisted at all: the frontend called Google's raw
    # solarPanels[] layout live on every page view instead, with no
    # relationship to this app's own resolved boundary or exclusions.
    panel_layout: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Building Insights' per-plane roof data (pitch/azimuth/area/sunshine
    # per roofSegmentStats entry) — see routers/assessments.py::
    # _pack_panel_layout()'s docstring. Persisted so the per-segment
    # figures a packed layout was built against survive the request
    # instead of being refetched live on every result-page view.
    roof_segments: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # routers/assessments.py::_building_match_warning()'s coarse "does the
    # returned building match the pin" sanity check result, if any.
    boundary_warning: Mapped[str | None] = mapped_column(String, nullable=True)

    # Enquiry workflow. The vendor the CUSTOMER picked when raising the
    # enquiry (raise_enquiry() below) — distinct from assigned_vendor_id
    # above, which is the admin's own final decision (approve_assessment()
    # still requires an explicit vendor_id even when this is set, so an
    # admin can confirm the customer's pick or override it). None when
    # the customer submitted without picking one.
    customer_selected_vendor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # When the customer actually raised the enquiry (raise_enquiry()) —
    # distinct from created_at (when the assessment itself was computed)
    # and reviewed_at (when an admin acted on it). None until raised.
    enquiry_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The specific customer login that raised the enquiry — owner_org
    # above is a shared account name (see users.py), not enough to notify
    # one person or to stamp a customerId on an audit-log row. Set once,
    # in raise_enquiry(), never overwritten.
    raised_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


def save_assessment(session: Session, *, owner_org: str, **fields) -> AssessmentRow:
    """Persists one orchestrate_assessment() result verbatim. `fields`
    matches AssessmentResponse's field names 1:1 (site_id, site_type,
    verdict, score, ...) — the router passes `response.model_dump()`
    plus owner_org, which the response itself doesn't carry.

    review_status starts at "not_submitted" for an eligible verdict, NOT
    "pending" — the feasibility check and the vendor enquiry are
    deliberately separate stages (a customer can view a SUITABLE result
    without ever creating an enquiry). It only becomes "pending" (i.e.
    enters the admin's review queue) when the customer explicitly raises
    an enquiry via raise_enquiry() below. An ineligible verdict still
    goes straight to "not_applicable" — there is never anything to raise
    an enquiry on for those.

    Deliberately does NOT create a vendor_jobs row itself (that used to
    happen inline in routers/app_checks.py::complete_check(), with no
    admin involved at all) — it only sets review_status so the
    assessment shows up in the admin review queue when eligible.
    Vendor job creation now only ever happens through approve_assessment()
    below, which is the one place a specific vendor gets chosen."""
    verdict = fields.get("verdict")
    row = AssessmentRow(
        id=str(uuid4()),
        owner_org=owner_org,
        created_at=datetime.now(UTC),
        review_status="not_submitted" if verdict in REVIEW_ELIGIBLE_VERDICTS else "not_applicable",
        **fields,
    )
    session.add(row)
    session.flush()
    return row


def raise_enquiry(
    session: Session,
    assessment_id: str,
    *,
    vendor_id: str | uuid.UUID | None,
    user_id: str | uuid.UUID | None = None,
) -> AssessmentRow | None:
    """The one place review_status moves from "not_submitted" to
    "pending" — the customer's own explicit act of turning a viewed
    result into something an admin needs to look at.

    Idempotent by design: once an assessment has left "not_submitted"
    (whether via this function or, for an older row predating this
    field, whatever state it's already in), calling this again is a
    silent no-op that returns the row UNCHANGED — never a second
    "enquiry", never a second vendor_jobs row, never an error. A
    double-submit (impatient click, retried request) must not create
    competing state; "first call wins" is the whole rule.

    Never creates a vendor_jobs row itself — that still only happens in
    approve_assessment() below, so there is exactly one place a vendor
    is ever actually assigned to real work, whether or not the customer
    expressed a preference here.
    """
    row = get_assessment(session, assessment_id)
    if row is None:
        return None
    if row.review_status != "not_submitted":
        return row
    row.review_status = "pending"
    row.customer_selected_vendor_id = uuid.UUID(str(vendor_id)) if vendor_id else None
    row.enquiry_submitted_at = datetime.now(UTC)
    row.raised_by_user_id = uuid.UUID(str(user_id)) if user_id else None
    session.flush()
    return row


def get_assessment(session: Session, assessment_id: str) -> AssessmentRow | None:
    return session.get(AssessmentRow, assessment_id)


def approve_assessment(
    session: Session,
    assessment_id: str,
    *,
    admin_email: str,
    vendor_id: str | uuid.UUID,
    vendor_job_id: str | uuid.UUID,
) -> AssessmentRow | None:
    """The one place review_status flips to "approved" — always paired
    with a real vendor_jobs row (created by the caller via
    repositories/vendors.py::create_job(), then linked back here) so an
    "approved" assessment always has somewhere a vendor can actually see
    it, closing the old create-an-orphaned-unassigned-job gap."""
    row = get_assessment(session, assessment_id)
    if row is None:
        return None
    row.review_status = "approved"
    row.reviewed_by = admin_email
    row.reviewed_at = datetime.now(UTC)
    row.assigned_vendor_id = uuid.UUID(str(vendor_id))
    row.vendor_job_id = uuid.UUID(str(vendor_job_id))
    session.flush()
    return row


def reassign_assessment_vendor(
    session: Session, assessment_id: str, *, admin_email: str, vendor_id: str | uuid.UUID
) -> AssessmentRow | None:
    """Changes WHO an already-approved assessment is assigned to.
    Re-stamps reviewed_by/reviewed_at to the reassigning admin/now, so
    "who assigned it and when" always reflects the CURRENT assignment,
    never a stale name from the original approval. The caller
    (routers/app_assessments.py) is responsible for moving the linked
    vendor_jobs row itself (repositories/vendors.py's own reassignment
    pattern, reused rather than duplicated) — this only updates the
    assessment's own pointer."""
    row = get_assessment(session, assessment_id)
    if row is None:
        return None
    row.assigned_vendor_id = uuid.UUID(str(vendor_id))
    row.reviewed_by = admin_email
    row.reviewed_at = datetime.now(UTC)
    session.flush()
    return row


def reject_assessment(
    session: Session, assessment_id: str, *, admin_email: str, reason: str
) -> AssessmentRow | None:
    row = get_assessment(session, assessment_id)
    if row is None:
        return None
    row.review_status = "rejected"
    row.reviewed_by = admin_email
    row.reviewed_at = datetime.now(UTC)
    row.rejection_reason = reason
    session.flush()
    return row


def set_grid_feasibility(session: Session, assessment_id: str, *, feasibility: dict) -> AssessmentRow | None:
    row = get_assessment(session, assessment_id)
    if row is None:
        return None
    row.grid_feasibility = feasibility
    session.flush()
    return row


def set_financial_feasibility(session: Session, assessment_id: str, *, feasibility: dict) -> AssessmentRow | None:
    row = get_assessment(session, assessment_id)
    if row is None:
        return None
    row.financial_feasibility = feasibility
    session.flush()
    return row


def count_created_since(session: Session, since: datetime) -> int:
    """A COUNT(*), not list_assessments()+len() — see
    repositories/sites.py::count_created_since for why: the admin
    platform-health quota display only needs the number."""
    stmt = select(func.count()).select_from(AssessmentRow).where(AssessmentRow.created_at >= since)
    return session.scalar(stmt) or 0


def list_assessments(
    session: Session, *, owner_org: str | None = None, limit: int = 50, offset: int = 0
) -> list[AssessmentRow]:
    """owner_org=None is a genuine cross-org read — callers must have
    already established the right to one (GET /app/admin/assessments'
    require_role("admin") gate), same discipline as
    repositories/sites.py::list_sites()."""
    stmt = (
        select(AssessmentRow).order_by(AssessmentRow.created_at.desc()).limit(limit).offset(offset)
    )
    if owner_org is not None:
        stmt = stmt.where(AssessmentRow.owner_org == owner_org)
    return list(session.scalars(stmt))


def get_latest_by_site(session: Session, site_id: str) -> AssessmentRow | None:
    """Closes a real gap found during a frontend/backend sync audit:
    Site.latestAssessment, PortfolioSummary.totalCapacityKwp/
    verdictBreakdown, and CompositeSite.aggregateCapacityKwp were all
    stubbed to None/0 with a "once the assessments table lands" TODO —
    it landed with omkar's merge, this is the lookup that unblocks all
    four."""
    stmt = (
        select(AssessmentRow)
        .where(AssessmentRow.site_id == site_id)
        .order_by(AssessmentRow.created_at.desc())
        .limit(1)
    )
    return session.scalars(stmt).first()


def confidence_label(score: float | None, confidence: float) -> str:
    """Same bucketing routers/app_assessments.py's own _confidence_label
    already established (N/A when there's no score, High >= 0.7,
    Medium >= 0.4, else Low) — shared here so every /app/* surface that
    renders a persisted assessment (site detail, portfolio, composites,
    checks) applies the identical rule rather than three near-copies
    drifting apart."""
    if score is None:
        return "N/A"
    if confidence >= 0.7:
        return "High"
    if confidence >= 0.4:
        return "Medium"
    return "Low"


def binding_constraint_dict(row: AssessmentRow) -> dict:
    """Same synthesis routers/app_assessments.py's own
    _binding_constraint_out already established: look the binding
    constraint's name up in the stored ceiling list for its real
    reason/kind; gate failures and "insufficient_data:..." sentinels
    aren't in that list, so fall back to the first matching reason
    string rather than crashing on a lookup miss."""
    name = row.binding_constraint
    for ceiling in (row.capacity or {}).get("ceilings", []):
        if ceiling.get("constraint") == name:
            return {
                "name": name,
                "reason": ceiling.get("reason", ""),
                "kind": ceiling.get("kind", "physical"),
            }
    detail = next(
        (r for r in row.reasons if name.split(":")[-1] in r), row.reasons[0] if row.reasons else ""
    )
    return {"name": name, "reason": detail, "kind": "physical"}


def ceiling_ledger(row: AssessmentRow) -> list[dict]:
    """CON-04. Every ceiling the resolver weighed, as the frontend needs it.

    These were always computed and stored in `capacity` — the ledger was
    just dropped on the way out ("ceiling_ledger": [] was hardcoded), so
    the customer saw a number and a constraint NAME with nothing behind
    it. Nothing new is calculated here; this only stops discarding what
    the resolver already decided.

    A ceiling that could not be evaluated keeps `kwp: None` and its
    "insufficient_data" status rather than being dropped or defaulted to
    zero: "we could not check this" and "this limits you to 0 kWp" are
    opposite claims, and a zero here would read as the second.

    Snake_case keys — safe for callers (like routers/app_sites.py's
    CeilingLedgerOut(**entry)) that validate through a _CamelModel with
    populate_by_name=True, which accepts either the field name or its
    camelCase alias. NOT safe for a caller that ships this list as a raw,
    untyped dict straight to the frontend — use ceiling_ledger_list()
    below for that.
    """
    binding = row.binding_constraint
    return [
        {
            "label": ceiling.get("constraint", ""),
            "kwp": ceiling.get("ceiling_kwp"),
            "kind": ceiling.get("kind", "physical"),
            "status": ceiling.get("status", "ok"),
            "note": ceiling.get("reason", ""),
            "is_binding": ceiling.get("constraint") == binding,
        }
        for ceiling in (row.capacity or {}).get("ceilings", [])
    ]


def ceiling_ledger_list(row: AssessmentRow) -> list[dict[str, Any]]:
    """The real per-constraint checklist an admin reviews before
    approving — every ceiling the resolver actually evaluated (physical/
    regulatory/commercial), not a separate hand-maintained checklist, so
    it can never drift from what the engine actually checked.

    Keys are already camelCase (label/kwp/kind/note/isBinding/status):
    this feeds AssessmentOut.ceiling_ledger, which is typed `list[dict]`
    (a raw dict, not a nested CamelModel) — FastAPI/pydantic only
    camelCases *declared* model fields, not keys inside an untyped dict,
    so this function has to hand back the exact shape
    lib/types.ts's CeilingLedgerEntry expects itself."""
    binding_name = row.binding_constraint
    return [
        {
            "label": c.get("constraint", ""),
            "kwp": c.get("ceiling_kwp"),
            "kind": c.get("kind", "physical"),
            "note": c.get("reason", ""),
            "status": c.get("status", "ok"),
            "isBinding": c.get("constraint") == binding_name,
        }
        for c in (row.capacity or {}).get("ceilings", [])
    ]


def to_frontend_assessment_dict(row: AssessmentRow) -> dict:
    """The nested Assessment shape lib/types.ts's Site.latestAssessment
    (and CompositeSite/PortfolioSummary's capacity aggregates) expect —
    distinct from AppAssessmentResponse in routers/app_assessments.py,
    which is the FLAT shape for POST /app/assessments/{id}'s own
    response. Same underlying row, two different frontend contracts."""
    return {
        "id": row.id,
        "site_id": row.site_id,
        "verdict": row.verdict,
        "capacity_kwp": (row.capacity or {}).get("recommended_kwp") or 0.0,
        "confidence": confidence_label(row.score, row.confidence),
        # Enquiry workflow — the customer-safe subset (no reviewer name,
        # no rejection reason, no vendor id) of what admin's own
        # ReviewFieldsOut carries. Lets the result page tell "not raised
        # yet" from "already in review" from "already assigned".
        "review_status": row.review_status,
        "enquiry_submitted_at": row.enquiry_submitted_at.isoformat() if row.enquiry_submitted_at else None,
        # Raw numeric alongside the existing bucketed label — FIT-03: a
        # None score (INSUFFICIENT_DATA) stays None, never a fabricated
        # 0. Both rescaled to 0-100 for a customer-facing "X/100" figure;
        # the 0..1 range is an internal engine convention, not something
        # a customer should have to interpret.
        "score": round(row.score * 100, 1) if row.score is not None else None,
        "confidence_score": round(row.confidence * 100, 1),
        "binding_constraint": binding_constraint_dict(row),
        "reasons": row.reasons,
        "conditions": row.conditions or [],
        # engine/fitness.py::STANDARD_LIMITATIONS — stored on every row
        # since Day 0 but never actually reached the customer-facing UI
        # (only shorter, separately-authored disclaimer sentences did).
        "limitations": row.limitations,
        "ceiling_ledger": ceiling_ledger_list(row),
        # Stored all along and never surfaced. The three together are what
        # let a customer see WHY a number was chosen: what the roof could
        # take, what they were recommended, and the gap between them.
        "usable_area_m2": row.usable_area_m2,
        "total_area_m2": row.total_area_m2,
        "score_components": row.score_components or {},
        "confidence_components": row.confidence_components or {},
        "confidence_explanation": row.confidence_explanation or [],
        "max_technical_kwp": (row.capacity or {}).get("max_technical_kwp"),
        "headroom_kwp": (row.capacity or {}).get("headroom_kwp"),
        "panel_layout": row.panel_layout,
        "roof_segments": row.roof_segments,
        "boundary_warning": row.boundary_warning,
        "panorama_url": row.panorama_url,
        "ml_suitability_score": row.ml_suitability_score,
        # engine/generation.py::estimate_generation_kwh()'s real output —
        # the row column has existed since a prior fix but was never read
        # into this customer-facing dict.
        "generation": row.generation,
        # engine/financials.py's real output — an estimate, not the
        # admin-entered financial_feasibility quote.
        "financial_estimate": row.financial_estimate,
        "cache": {"cache_hit": row.cache_hit},
        "assessed_at": row.created_at.isoformat(),
        "model_version": row.engine_version,
    }
