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

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from solarfit.db import Base


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


def save_assessment(session: Session, *, owner_org: str, **fields) -> AssessmentRow:
    """Persists one orchestrate_assessment() result verbatim. `fields`
    matches AssessmentResponse's field names 1:1 (site_id, site_type,
    verdict, score, ...) — the router passes `response.model_dump()`
    plus owner_org, which the response itself doesn't carry."""
    row = AssessmentRow(
        id=str(uuid4()),
        owner_org=owner_org,
        created_at=datetime.now(UTC),
        **fields,
    )
    session.add(row)
    session.flush()
    return row


def list_assessments(
    session: Session, *, owner_org: str | None = None, limit: int = 50, offset: int = 0
) -> list[AssessmentRow]:
    """owner_org=None is a genuine cross-org read — callers must have
    already established the right to one (GET /app/admin/assessments'
    require_role("admin") gate), same discipline as
    repositories/sites.py::list_sites()."""
    stmt = select(AssessmentRow).order_by(AssessmentRow.created_at.desc()).limit(limit).offset(offset)
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
            return {"name": name, "reason": ceiling.get("reason", ""), "kind": ceiling.get("kind", "physical")}
    detail = next((r for r in row.reasons if name.split(":")[-1] in r), row.reasons[0] if row.reasons else "")
    return {"name": name, "reason": detail, "kind": "physical"}


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
        "ceiling_ledger": [],
        "panorama_url": row.panorama_url,
        "ml_suitability_score": row.ml_suitability_score,
        "cache": {"cache_hit": row.cache_hit},
        "assessed_at": row.created_at.isoformat(),
        "model_version": row.engine_version,
    }
