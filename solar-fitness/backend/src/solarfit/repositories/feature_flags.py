"""Owner: keerthana (Vendor domain, customer-account admin, jurisdictions).

Backs the admin Configuration page's feature-flag toggles
(app_admin_platform.py). Previously a hardcoded array in the frontend
with a local useState — this table is the real, persisted source of
truth so a toggle survives a reload and is visible to every admin.

Rows are seeded by migration 7a4e2c8f9b15 with the exact flags/labels/
descriptions the frontend used to hardcode; nothing here adds or
removes flags at runtime — that's still a migration, same as adding a
new flag to the old hardcoded array would have been a code change.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, String, func, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, Session, mapped_column

from solarfit.db import Base

__all__ = ["FeatureFlagRow", "list_flags", "set_enabled"]


class FeatureFlagRow(Base):
    __tablename__ = "feature_flags"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(), nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


def list_flags(session: Session) -> list[FeatureFlagRow]:
    return list(session.scalars(select(FeatureFlagRow).order_by(FeatureFlagRow.key)))


def set_enabled(session: Session, key: str, enabled: bool) -> FeatureFlagRow | None:
    row = session.scalars(select(FeatureFlagRow).where(FeatureFlagRow.key == key)).one_or_none()
    if row is None:
        return None
    row.enabled = enabled
    row.updated_at = datetime.now(UTC)
    session.flush()
    return row
