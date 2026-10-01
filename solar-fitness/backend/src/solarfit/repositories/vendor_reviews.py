"""Customer reviews of a vendor's completed work.

One review per installation project (the unique constraint on
installation_project_id on VendorReviewRow), left only after the customer
has accepted the finished installation — app_checks.py::accept_installation
sets commissioning.customer_accepted, and the review endpoint in that same
router gates on it before calling create_review().

vendor_rating_summary() is computed live from these rows at read time,
never stored on VendorRow — same "can't drift from the real data"
discipline repositories/vendors.py::vendor_admin_stats() already applies
to workload figures. VendorRow.accuracy_score is a separate, dormant field
(nothing computes it for a real vendor — see vendors.py's own module
docstring) and is intentionally not read or written anywhere in this file.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, Session, mapped_column

from solarfit.db import Base

__all__ = [
    "VendorReviewRow",
    "create_review",
    "get_review_for_project",
    "list_reviews_for_vendor",
    "vendor_rating_summary",
]


class VendorReviewRow(Base):
    __tablename__ = "vendor_reviews"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Unique: enforces "one review per completed job" at the DB level,
    # not just by the router checking get_review_for_project() first —
    # a double-submit race still 409s instead of creating two rows.
    installation_project_id: Mapped[str] = mapped_column(
        String, ForeignKey("installation_projects.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    # No FK — no FK to users.id exists anywhere in this schema yet (see
    # repositories/users.py's own module docstring), kept consistent.
    customer_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


def create_review(
    session: Session,
    *,
    vendor_id: str | uuid.UUID,
    installation_project_id: str,
    customer_user_id: str | uuid.UUID,
    rating: int,
    comment: str | None,
) -> VendorReviewRow:
    row = VendorReviewRow(
        vendor_id=uuid.UUID(str(vendor_id)),
        installation_project_id=installation_project_id,
        customer_user_id=uuid.UUID(str(customer_user_id)),
        rating=rating,
        comment=comment,
    )
    session.add(row)
    session.flush()
    return row


def get_review_for_project(session: Session, installation_project_id: str) -> VendorReviewRow | None:
    return session.scalars(
        select(VendorReviewRow).where(VendorReviewRow.installation_project_id == installation_project_id)
    ).one_or_none()


def list_reviews_for_vendor(
    session: Session, vendor_id: str | uuid.UUID, *, limit: int = 50
) -> list[VendorReviewRow]:
    """Newest first — a vendor card's "recent reviews" list, not a full
    paginated history (no admin/customer screen needs that yet)."""
    vid = uuid.UUID(str(vendor_id))
    stmt = (
        select(VendorReviewRow)
        .where(VendorReviewRow.vendor_id == vid)
        .order_by(VendorReviewRow.created_at.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt))


def vendor_rating_summary(session: Session, vendor_id: str | uuid.UUID) -> dict[str, float | int | None]:
    """{average_rating, review_count} — live-computed, same discipline as
    vendors.py::vendor_admin_stats(). average_rating is None (not 0.0)
    when there are no reviews yet, so the customer UI can show "No
    reviews yet" instead of a misleading 0-star rating."""
    vid = uuid.UUID(str(vendor_id))
    stmt = select(func.avg(VendorReviewRow.rating), func.count(VendorReviewRow.id)).where(
        VendorReviewRow.vendor_id == vid
    )
    average, count = session.execute(stmt).one()
    return {
        "average_rating": float(average) if average is not None else None,
        "review_count": int(count or 0),
    }
