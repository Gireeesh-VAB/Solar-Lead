"""Owner: keerthana (Vendor domain, customer-account admin, jurisdictions).

Backs the admin Configuration page's "API keys" list and the existing
/app/admin/api-keys/rotate endpoint (app_admin_platform.py). There is
still no real secret-rotation infrastructure — the four outbound
providers' actual credentials live in .env, not a live-rotatable
secret store — so rotate_key() below regenerates only the visible
masked suffix and timestamps the request. What changed from before:
that masked value and timestamp are now a real, persisted row instead
of a hardcoded frontend array, so a rotation is visible on reload and
to every admin, not just simulated client-side.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, String, func, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, Session, mapped_column

from solarfit.db import Base

__all__ = ["ServiceApiKeyRow", "list_keys", "rotate_key"]


class ServiceApiKeyRow(Base):
    __tablename__ = "service_api_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    service: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    masked_value: Mapped[str] = mapped_column(String(64), nullable=False)
    last_rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def list_keys(session: Session) -> list[ServiceApiKeyRow]:
    return list(session.scalars(select(ServiceApiKeyRow).order_by(ServiceApiKeyRow.service)))


def _get(session: Session, service: str) -> ServiceApiKeyRow | None:
    return session.scalars(select(ServiceApiKeyRow).where(ServiceApiKeyRow.service == service)).one_or_none()


def rotate_key(session: Session, service: str) -> ServiceApiKeyRow | None:
    """Regenerates the masked value's visible suffix and stamps
    last_rotated_at — see module docstring for why this isn't a real
    secret rotation. Returns None for a service with no seeded row
    (the four seeded services are the only ones the admin UI sends)."""
    row = _get(session, service)
    if row is None:
        return None
    prefix = row.masked_value.split("•")[0]
    row.masked_value = f"{prefix}{'•' * 12}{secrets.token_hex(2)}"
    row.last_rotated_at = datetime.now(UTC)
    session.flush()
    return row
