"""Detected-but-not-yet-confirmed rooftop obstacles.

A model detection must not shrink the customer's usable roof until the
customer has looked at it. So a detection is stored here as a `pending`
candidate; nothing about it touches site.exclusions. The customer then
Confirms it (applied to the exclusions through the normal SITE-05
versioned path, under the same id), Edits it (type/outline corrected, then
confirmed), or Ignores it (kept as `ignored`, so a later re-scan does not
offer the same object again).

`ordinal` is a stable per-site number (#1, #2, ...) shown on the map and
in the list. It survives confirmation, so "#2" keeps meaning the same
thing after the customer confirms #1.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, Session, mapped_column

from solarfit.db import Base

__all__ = [
    "STATUS_CONFIRMED",
    "STATUS_IGNORED",
    "STATUS_PENDING",
    "ObstacleCandidateRow",
    "add_candidates",
    "all_polygons",
    "get",
    "list_for_site",
    "mark",
    "ordinals_by_id",
    "update_shape",
]

STATUS_PENDING = "pending"
STATUS_CONFIRMED = "confirmed"
STATUS_IGNORED = "ignored"


class ObstacleCandidateRow(Base):
    __tablename__ = "obstacle_candidates"
    __table_args__ = (
        UniqueConstraint("site_id", "ordinal", name="uq_obstacle_candidates_site_ordinal"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    polygon: Mapped[dict] = mapped_column(JSONB, nullable=False)  # GeoJSON Polygon
    type: Mapped[str] = mapped_column(String(32), nullable=False, default="other")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="cv_detector")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=STATUS_PENDING)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


def _site_key(site_id: str | uuid.UUID) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(site_id))
    except (ValueError, AttributeError, TypeError):
        return None


def list_for_site(
    session: Session, site_id: str | uuid.UUID, *, status: str | None = None
) -> list[ObstacleCandidateRow]:
    """This site's candidates in their stable #1, #2... order."""
    key = _site_key(site_id)
    if key is None:
        return []
    stmt = select(ObstacleCandidateRow).where(ObstacleCandidateRow.site_id == key)
    if status is not None:
        stmt = stmt.where(ObstacleCandidateRow.status == status)
    return list(session.scalars(stmt.order_by(ObstacleCandidateRow.ordinal)))


def get(
    session: Session, site_id: str | uuid.UUID, candidate_id: str | uuid.UUID
) -> ObstacleCandidateRow | None:
    """One candidate, scoped to its site - another site's id is a miss."""
    key = _site_key(site_id)
    cid = _site_key(candidate_id)
    if key is None or cid is None:
        return None
    row = session.get(ObstacleCandidateRow, cid)
    return row if row is not None and row.site_id == key else None


def add_candidates(
    session: Session, site_id: str | uuid.UUID, obstacles: list
) -> list[ObstacleCandidateRow]:
    """Store detections as `pending`, keeping each one's own id so the id
    the customer sees is the id it keeps when confirmed. Numbers continue
    from the site's highest ordinal. The caller has already de-duplicated
    against what the site knows."""
    key = _site_key(site_id)
    if key is None or not obstacles:
        return []
    highest = session.scalar(
        select(func.max(ObstacleCandidateRow.ordinal)).where(ObstacleCandidateRow.site_id == key)
    )
    ordinal = int(highest or 0)
    rows: list[ObstacleCandidateRow] = []
    for obstacle in obstacles:
        ordinal += 1
        row = ObstacleCandidateRow(
            id=uuid.UUID(str(obstacle.id)),
            site_id=key,
            ordinal=ordinal,
            polygon=obstacle.bounding_polygon,
            type=obstacle.type,
            confidence=obstacle.confidence,
            source=obstacle.source,
            status=STATUS_PENDING,
        )
        session.add(row)
        rows.append(row)
    session.flush()
    return rows


def all_polygons(session: Session, site_id: str | uuid.UUID) -> list[dict]:
    """Every candidate's polygon whatever its status - pending, confirmed
    or ignored - so a re-scan never offers the same object twice and never
    resurrects one the customer ignored."""
    return [row.polygon for row in list_for_site(session, site_id)]


def ordinals_by_id(session: Session, site_id: str | uuid.UUID) -> dict[str, int]:
    """candidate id -> its #number, for labelling already-confirmed ones."""
    return {str(row.id): row.ordinal for row in list_for_site(session, site_id)}


def mark(session: Session, row: ObstacleCandidateRow, status: str) -> ObstacleCandidateRow:
    row.status = status
    row.updated_at = datetime.now(UTC)
    session.flush()
    return row


def update_shape(
    session: Session, row: ObstacleCandidateRow, *, polygon: dict | None = None, type_: str | None = None
) -> ObstacleCandidateRow:
    """The customer's correction to a detection (outline and/or type)."""
    if polygon is not None:
        row.polygon = polygon
    if type_ is not None:
        row.type = type_
    row.updated_at = datetime.now(UTC)
    session.flush()
    return row
