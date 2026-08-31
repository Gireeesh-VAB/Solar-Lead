"""Owner: Person 4 (Scoring, USN & Assessment API).

Persistence for the USN-06 half of §9.15 USN Capture — the evidence
trail for a bill/payment-proof image uploaded purely to extract a USN.
This table stores only a pointer to the encrypted-at-rest object in
external storage plus the raw OCR text, both cleared by the purge job
(workers/tasks_usn.py) after get_usn_ocr_retention_days()
(packs/config_pack.py) has elapsed.

The confirmed `usn` value itself is NOT stored here and is not subject
to this retention window — once repositories/sites.py::update_usn()
exists, it lives with the Site indefinitely (CON-05's subsidy-tier
lookup needs it for the life of the site). This table is the OCR
*evidence* trail; providers/usn_ocr.py's UsnCapture is the *value*.

Never queried by engine/ml_score.py or any vision-training path
(USN-06's "hard-excluded from ML/vision training" clause) — enforced by
code-review discipline, not something Python's type system can check.

No FK to a `sites` table yet — it doesn't exist (Person 1's repositories/
sites.py is still a stub). `site_id` is stored as a plain indexed string
for now; add the FK constraint in a later migration once that table
exists.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import DateTime, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from solarfit.db import Base
from solarfit.packs.config_pack import get_usn_ocr_retention_days


class UsnOcrUpload(Base):
    __tablename__ = "usn_ocr_uploads"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    site_id: Mapped[str] = mapped_column(String, index=True)
    document_type: Mapped[str] = mapped_column(String)  # "bill" | "payment_proof"
    object_storage_key: Mapped[str | None] = mapped_column(String, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    purge_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    extraction_status: Mapped[str] = mapped_column(String)  # extracted|not_found|failed|confirmed
    ocr_raw_text: Mapped[str | None] = mapped_column(String, nullable=True)
    never_use_for_training: Mapped[bool] = mapped_column(default=True)


def save_upload(
    session: Session,
    *,
    site_id: str,
    document_type: str,
    object_storage_key: str,
    extraction_status: str,
    ocr_raw_text: str | None,
) -> UsnOcrUpload:
    """USN-06. Records upload evidence with its retention deadline
    computed from the config pack. Does not persist any usn value."""
    now = datetime.now(UTC)
    upload = UsnOcrUpload(
        id=str(uuid4()),
        site_id=site_id,
        document_type=document_type,
        object_storage_key=object_storage_key,
        uploaded_at=now,
        purge_after=now + timedelta(days=get_usn_ocr_retention_days()),
        extraction_status=extraction_status,
        ocr_raw_text=ocr_raw_text,
        never_use_for_training=True,
    )
    session.add(upload)
    session.flush()
    return upload


def get_upload(session: Session, upload_id: str) -> UsnOcrUpload | None:
    return session.get(UsnOcrUpload, upload_id)


def mark_confirmed(session: Session, upload_id: str) -> UsnOcrUpload:
    upload = session.get(UsnOcrUpload, upload_id)
    if upload is None:
        raise ValueError(f"No usn_ocr_uploads row for id={upload_id}")
    upload.extraction_status = "confirmed"
    session.flush()
    return upload


def find_expired(session: Session) -> list[UsnOcrUpload]:
    """USN-06. Rows past their retention deadline that still hold
    evidence to purge. Returns the rows themselves (not just IDs) since
    the caller needs object_storage_key to delete the actual blob before
    calling finalize_purge()."""
    now = datetime.now(UTC)
    stmt = select(UsnOcrUpload).where(
        UsnOcrUpload.purge_after <= now,
        UsnOcrUpload.ocr_raw_text.is_not(None),
    )
    return list(session.scalars(stmt).all())


def finalize_purge(session: Session, upload_id: str) -> None:
    """USN-06. Called only after the caller has confirmed the
    object-storage blob is deleted — nulls the remaining evidence."""
    upload = session.get(UsnOcrUpload, upload_id)
    if upload is None:
        return
    upload.ocr_raw_text = None
    upload.object_storage_key = None
    session.flush()
