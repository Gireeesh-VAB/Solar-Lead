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

from sqlalchemy import JSON, Boolean, DateTime, Float, String, select
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
    limitations: Mapped[str] = mapped_column(String)

    capacity: Mapped[dict] = mapped_column(JSON)
    boundary: Mapped[dict] = mapped_column(JSON)
    usable_area_m2: Mapped[float | None] = mapped_column(Float, nullable=True)

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


def save_assessment(session: Session, *, owner_org: str, **fields) -> AssessmentRow:
    """Persists one orchestrate_assessment() result verbatim. `fields`
    matches AssessmentResponse's field names 1:1 (site_id, site_type,
    verdict, score, ...) — the router passes `response.model_dump()`
    plus owner_org, which the response itself doesn't carry.

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
        review_status="pending" if verdict in REVIEW_ELIGIBLE_VERDICTS else "not_applicable",
        **fields,
    )
    session.add(row)
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
        "binding_constraint": binding_constraint_dict(row),
        "reasons": row.reasons,
        "ceiling_ledger": ceiling_ledger_list(row),
        # Stored all along and never surfaced. The three together are what
        # let a customer see WHY a number was chosen: what the roof could
        # take, what they were recommended, and the gap between them.
        "usable_area_m2": row.usable_area_m2,
        "max_technical_kwp": (row.capacity or {}).get("max_technical_kwp"),
        "headroom_kwp": (row.capacity or {}).get("headroom_kwp"),
        "panorama_url": row.panorama_url,
        "ml_suitability_score": row.ml_suitability_score,
        "cache": {"cache_hit": row.cache_hit},
        "assessed_at": row.created_at.isoformat(),
        "model_version": row.engine_version,
    }
