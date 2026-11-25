"""Owner: karthik (App Platform & Foundation).

One shared audit trail for every admin/vendor/customer mutation across the
/app/* surface — the append-only record the User -> Vendor -> Super Admin
controlled workflow's "complete audit trail" requirement is built on.
Deliberately its own module rather than living inside a router — omkar's
app_admin_vendors.py and keerthana's app_admin_customers.py both call
write_audit_log() without needing to import each other's or karthik's
router files.

`actor`/`action`/`target`/`details` are the original four columns — kept
exactly as they were (the frontend's AuditLogEntry.details: string
contract still matches `details`) so every pre-existing call site keeps
working unchanged. Everything below is additive: structured actor
identity/role, an entity reference, cross-references to the
project/survey/customer/vendor a row is about, a before/after value pair,
and the request's ip/user-agent. Callers pass whichever of these they
have — there is no requirement to fill every field, since not every
action (e.g. a platform feature-flag toggle) has a customer or vendor to
reference.

No update()/delete() function exists here by design — audit rows are
append-only, and that must stay true even for a caller with a raw DB
session and good intentions.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, Text, func, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
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

    # Structured actor identity — actor above stays the human-readable
    # email/name shown in the table; these let the activity screen filter
    # by a stable id and by role without parsing the free-text actor.
    actor_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    actor_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # entity_id defaults to `target` at write time (see write_audit_log)
    # so every row is filterable by entity even for older callers that
    # only ever passed target.
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Cross-references. "project" and "survey" are the same underlying
    # AssessmentRow.id in this codebase (see repositories/assessments.py —
    # there is no separate Project entity), so both are set together for
    # any assessment-scoped action; kept as two columns rather than one to
    # match the spec's own field list and avoid a caller having to guess
    # which name a filter expects.
    project_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    survey_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    vendor_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    previous_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)


def write_audit_log(
    session: Session,
    *,
    actor: str,
    action: str,
    target: str,
    details: str | None = None,
    actor_id: str | None = None,
    actor_type: str | None = None,
    actor_role: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    project_id: str | None = None,
    survey_id: str | None = None,
    customer_id: str | None = None,
    vendor_id: str | None = None,
    previous_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
    reason: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLogRow:
    """Called from every admin/vendor/customer-mutating endpoint — never
    in place of the mutation itself, always alongside it, in the same
    request/transaction.

    `entity_id` falls back to `target` (and vice versa isn't done — target
    stays required, matching every existing call site) so a row written by
    an older call site is still findable via an entity-scoped filter.
    """
    row = AuditLogRow(
        actor=actor,
        action=action,
        target=target,
        details=details,
        actor_id=actor_id,
        actor_type=actor_type,
        actor_role=actor_role,
        entity_type=entity_type,
        entity_id=entity_id or target,
        project_id=project_id,
        survey_id=survey_id,
        customer_id=customer_id,
        vendor_id=vendor_id,
        previous_value=previous_value,
        new_value=new_value,
        reason=reason,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    session.add(row)
    session.flush()
    return row


def count_since(session: Session, since: datetime, *, action: str | None = None) -> int:
    """A COUNT(*), not list_audit_log()+len() — see
    repositories/sites.py::count_created_since for why: the admin
    platform-health incident count only needs the number."""
    stmt = select(func.count()).select_from(AuditLogRow).where(AuditLogRow.created_at >= since)
    if action is not None:
        stmt = stmt.where(AuditLogRow.action == action)
    return session.scalar(stmt) or 0


def list_audit_log(
    session: Session,
    *,
    actor: str | None = None,
    action: str | None = None,
    q: str | None = None,
    actor_role: str | None = None,
    entity_type: str | None = None,
    project_id: str | None = None,
    survey_id: str | None = None,
    customer_id: str | None = None,
    vendor_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 200,
) -> list[AuditLogRow]:
    """Newest first. `q` is a simple substring match against `target`/
    `details` — this is an ops/debugging screen, not a search product,
    so a LIKE query is proportionate rather than reaching for full-text
    search infrastructure nothing else in this codebase uses yet.

    Every other kwarg is an exact-match filter for the Super Admin
    activity screen (spec section 8): vendor/customer/project/survey/
    actor-role/entity-type/date-range, composable with `actor`/`action`/
    `q` above.
    """
    stmt = select(AuditLogRow).order_by(AuditLogRow.created_at.desc()).limit(limit)
    if actor is not None:
        stmt = stmt.where(AuditLogRow.actor == actor)
    if action is not None:
        stmt = stmt.where(AuditLogRow.action == action)
    if actor_role is not None:
        stmt = stmt.where(AuditLogRow.actor_role == actor_role)
    if entity_type is not None:
        stmt = stmt.where(AuditLogRow.entity_type == entity_type)
    if project_id is not None:
        stmt = stmt.where(AuditLogRow.project_id == project_id)
    if survey_id is not None:
        stmt = stmt.where(AuditLogRow.survey_id == survey_id)
    if customer_id is not None:
        stmt = stmt.where(AuditLogRow.customer_id == customer_id)
    if vendor_id is not None:
        stmt = stmt.where(AuditLogRow.vendor_id == vendor_id)
    if since is not None:
        stmt = stmt.where(AuditLogRow.created_at >= since)
    if until is not None:
        stmt = stmt.where(AuditLogRow.created_at <= until)
    if q:
        like = f"%{q}%"
        stmt = stmt.where((AuditLogRow.target.ilike(like)) | (AuditLogRow.details.ilike(like)))
    return list(session.scalars(stmt))
