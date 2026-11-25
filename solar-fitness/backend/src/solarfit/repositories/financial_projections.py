"""FIN-02 — persisted snapshots of engine/financial_projection.py's output.

Pure storage, same providers/(compute) vs repositories/(persist) split as
every other repository in this codebase (see repositories/assessments.py's
own docstring). One row per computed projection, never overwritten — a
customer or admin can recompute (a new POST), which inserts a fresh row
and leaves the old one exactly as it was, reproducible against the
assumptions_version it stamped at the time.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Integer, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from solarfit.db import Base

__all__ = ["FinancialProjectionRow", "save_projection", "get_latest_by_assessment"]


class FinancialProjectionRow(Base):
    __tablename__ = "financial_projections"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    assessment_id: Mapped[str] = mapped_column(String, index=True)
    assumptions_version: Mapped[int] = mapped_column(Integer)
    financing_input: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def save_projection(
    session: Session,
    *,
    assessment_id: str,
    assumptions_version: int,
    financing_input: dict | None,
    result: dict,
) -> FinancialProjectionRow:
    row = FinancialProjectionRow(
        assessment_id=assessment_id,
        assumptions_version=assumptions_version,
        financing_input=financing_input,
        result=result,
        created_at=datetime.now(UTC),
    )
    session.add(row)
    session.flush()
    return row


def get_latest_by_assessment(session: Session, assessment_id: str) -> FinancialProjectionRow | None:
    stmt = (
        select(FinancialProjectionRow)
        .where(FinancialProjectionRow.assessment_id == assessment_id)
        .order_by(FinancialProjectionRow.created_at.desc())
        .limit(1)
    )
    return session.scalars(stmt).first()
