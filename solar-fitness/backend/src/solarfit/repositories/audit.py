"""Owner: karthik (App Platform & Foundation).

One shared audit trail for every admin mutation across the /app/*
surface. Deliberately its own module rather than living inside a router
— omkar's app_admin_vendors.py and keerthana's app_admin_customers.py
both call write_audit_log() without needing to import each other's or
karthik's router files.

`details` is a plain human-readable string, matching the frontend's
AuditLogEntry.details: string exactly — not a JSON blob.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, Session, mapped_column

from solarfit.db import Base

__all__ = ["AuditLogRow", "list_audit_log", "write_audit_log"]


class AuditLogRow(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    actor: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    target: Mapped[str] = mapped_column(String(255), nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


def write_audit_log(
    session: Session, *, actor: str, action: str, target: str, details: str | None = None
) -> AuditLogRow:
    """Called from every admin-mutating endpoint (suspend/reinstate/
    approve/reject/tier-change/key-rotation) — never in place of the
    mutation itself, always alongside it, in the same request."""
    row = AuditLogRow(actor=actor, action=action, target=target, details=details)
    session.add(row)
    session.flush()
    return row


def list_audit_log(
    session: Session,
    *,
    actor: str | None = None,
    action: str | None = None,
    q: str | None = None,
    limit: int = 200,
) -> list[AuditLogRow]:
    """Newest first. `q` is a simple substring match against `target`/
    `details` — this is an ops/debugging screen, not a search product,
    so a LIKE query is proportionate rather than reaching for full-text
    search infrastructure nothing else in this codebase uses yet."""
    stmt = select(AuditLogRow).order_by(AuditLogRow.created_at.desc()).limit(limit)
    if actor is not None:
        stmt = stmt.where(AuditLogRow.actor == actor)
    if action is not None:
        stmt = stmt.where(AuditLogRow.action == action)
    if q:
        like = f"%{q}%"
        stmt = stmt.where((AuditLogRow.target.ilike(like)) | (AuditLogRow.details.ilike(like)))
    return list(session.scalars(stmt))
