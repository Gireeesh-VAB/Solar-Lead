"""Owner: karthik (App Platform & Foundation).

In-app notifications — one row per notification, written synchronously at
the call site (approve_assessment(), sweep_vendor_job_sla(), submit_job(),
...), same shape as repositories/audit.py::write_audit_log(). No queued
task: this is a DB write, not an external send, so there is nothing slow
enough to defer.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, String, Text, func, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, Session, mapped_column

from solarfit.db import Base

__all__ = ["NotificationRow", "create_notification", "list_for_user", "mark_read"]


class NotificationRow(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


def create_notification(
    session: Session, *, user_id: str | uuid.UUID, kind: str, title: str, body: str | None = None
) -> NotificationRow:
    row = NotificationRow(user_id=uuid.UUID(str(user_id)), kind=kind, title=title, body=body)
    session.add(row)
    session.flush()
    return row


def list_for_user(session: Session, user_id: str | uuid.UUID, *, limit: int = 50) -> list[NotificationRow]:
    """Unread first, newest first within each group — the two orderings
    a bell/list UI actually needs, in one query rather than the caller
    re-sorting client-side."""
    stmt = (
        select(NotificationRow)
        .where(NotificationRow.user_id == uuid.UUID(str(user_id)))
        .order_by(NotificationRow.read_at.is_not(None), NotificationRow.created_at.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt))


def mark_read(session: Session, notification_id: str | uuid.UUID, user_id: str | uuid.UUID) -> NotificationRow | None:
    """Scoped to user_id — same not-found-not-forbidden discipline
    app_vendor.py's _job_or_404() already established, so a caller can't
    probe someone else's notification ids."""
    row = session.get(NotificationRow, uuid.UUID(str(notification_id)))
    if row is None or row.user_id != uuid.UUID(str(user_id)):
        return None
    if row.read_at is None:
        row.read_at = datetime.now(UTC)
        session.flush()
    return row
