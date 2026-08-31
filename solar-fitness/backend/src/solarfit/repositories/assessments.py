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
