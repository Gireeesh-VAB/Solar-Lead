"""Owner: Person 4 (Scoring, USN & Assessment API).

Implements §9.15 USN Capture (USN-01..06) of
Solar_Fitness_Engine_Development_Document_v1.2. Scoped to
ROOFTOP_RESIDENTIAL / ROOFTOP_CI only (BILLING_LINKED_SITE_TYPES in
solarfit.domain.site).

  USN-01  Manual text entry — baseline path.
  USN-02  OCR from an uploaded electricity bill; confirm-before-store.
  USN-03  OCR from a payment-proof/transaction screenshot; same
          confirm-before-store discipline.
  USN-04  Converge all three paths into one usn + usn_source
          (see solarfit.domain.site.UsnCapture).
  USN-05  Coordinate with Person 1: SITE-02's JSON Schema must omit this
          field group entirely for non-billing-linked site types.
  USN-06  Bill/payment-proof images used purely for OCR: encrypted at
          rest, retention window, hard-excluded from ML/vision training.
          See repositories/usn_uploads.py for the evidence-retention
          table and workers/tasks_usn.py for the purge job.

Design notes (flagged, not silent):
  - "Confirm-before-store" means the extracted usn is never written onto
    a Site until confirm_and_finalize() runs. It does NOT mean the
    uploaded image/evidence sits unmanaged until then — USN-06 requires
    the image to already be under encrypted, retention-tracked storage
    the moment it's uploaded, regardless of whether extraction succeeds.
    So extract_from_bill()/extract_from_payment_proof() DO have a
    persistence side effect (the evidence row + object-storage upload);
    only the confirmed *value* waits for a separate step.
  - Persisting the confirmed usn onto Site.usn is the caller's job —
    routers/app_usn.py's /confirm route calls confirm_and_finalize()
    then repositories.sites.update_usn(), rather than this module
    reaching into Person 1's file itself.
  - No jurisdiction-specific USN format spec exists anywhere in the
    source material — _validate_usn_format() is a placeholder length/
    charset check, not a real format rule. Override once one is known.

Depends on: solarfit.domain.site.UsnCapture (frozen, Day 0),
solarfit.repositories.usn_uploads (this person's own, task 3).
"""

import re
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel

from solarfit.config import get_settings
from solarfit.db import session_scope
from solarfit.domain.site import UsnCapture, UsnSource
from solarfit.repositories import usn_uploads as usn_uploads_repo

_USN_FORMAT = re.compile(r"^[A-Z0-9\-]{6,20}$")

_USN_PATTERNS = [
    re.compile(r"USN[:\s]*([A-Z0-9\-]{6,20})", re.IGNORECASE),
    re.compile(r"Service\s*Number[:\s]*([A-Z0-9\-]{6,20})", re.IGNORECASE),
    re.compile(r"Consumer\s*(?:No\.?|Number)[:\s]*([A-Z0-9\-]{6,20})", re.IGNORECASE),
]


class UsnExtractionPreview(BaseModel):
    """Returned by extract_from_bill()/extract_from_payment_proof() —
    never auto-persisted onto a Site. upload_id threads through to
    confirm_and_finalize()."""

    upload_id: str
    usn: str | None
    usn_source: UsnSource
    extraction_status: Literal["extracted", "not_found", "failed"]


def _validate_usn_format(value: str) -> str:
    """Placeholder validation — no real jurisdiction format spec exists
    yet. Raises ValueError on an obviously malformed value."""
    normalized = value.strip().upper()
    if not _USN_FORMAT.match(normalized):
        raise ValueError(
            f"USN '{value}' doesn't match the expected format "
            "(6-20 uppercase alphanumeric/hyphen characters)."
        )
    return normalized


def capture_manual(usn: str) -> UsnCapture:
    """USN-01."""
    return UsnCapture(usn=_validate_usn_format(usn), usn_source="manual")


def _run_text_detection(image: bytes) -> str:
    """Wraps the Google Cloud Vision TEXT_DETECTION call. The client is
    constructed lazily inside the function (not at import time) so
    tests can monkeypatch this one function without needing real GCP
    credentials or a network call."""
    from google.cloud import vision

    client = vision.ImageAnnotatorClient()
    response = client.text_detection(image=vision.Image(content=image))
    if response.error.message:
        raise RuntimeError(f"Vision API error: {response.error.message}")
    annotations = response.text_annotations
    return annotations[0].description if annotations else ""


def _object_storage_client():
    import boto3

    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.object_storage_endpoint_url or None,
        aws_access_key_id=settings.object_storage_access_key or None,
        aws_secret_access_key=settings.object_storage_secret_key or None,
    )


def _upload_to_object_storage(key: str, data: bytes) -> None:
    """Lazily-constructed S3-compatible client — matches the
    OBJECT_STORAGE_ENDPOINT_URL shape already in Settings. Monkeypatched
    in tests, same as _run_text_detection."""
    settings = get_settings()
    _object_storage_client().put_object(Bucket=settings.object_storage_bucket, Key=key, Body=data)


def delete_from_object_storage(key: str) -> None:
    """Counterpart to _upload_to_object_storage — public since
    workers/tasks_usn.py's purge job calls this across the module
    boundary, unlike the upload/detection helpers which stay internal
    to this file's own extraction flow."""
    settings = get_settings()
    _object_storage_client().delete_object(Bucket=settings.object_storage_bucket, Key=key)


def _extract_usn_from_text(raw_text: str) -> str | None:
    """USN-02/03's field-locator step. Returns None — never a guess —
    when no pattern matches."""
    for pattern in _USN_PATTERNS:
        match = pattern.search(raw_text)
        if match:
            return match.group(1).strip().upper()
    return None


def _capture_and_extract(
    image: bytes, site_id: str, *, document_type: str, usn_source: UsnSource
) -> UsnExtractionPreview:
    """Shared body of extract_from_bill/extract_from_payment_proof —
    USN-06's evidence retention applies identically to both paths."""
    object_key = f"usn-ocr/{site_id}/{document_type}/{uuid4()}"

    status: Literal["extracted", "not_found", "failed"]
    try:
        raw_text: str | None = _run_text_detection(image)
        usn = _extract_usn_from_text(raw_text)
        status = "extracted" if usn else "not_found"
    except Exception:  # noqa: BLE001 — deliberately broad: any OCR-call failure
        # (network, auth, malformed image, an unexpected Vision API error type)
        # degrades to a "failed" preview rather than blocking the upload/evidence
        # trail below, matching VIS-04's "never block the pipeline on this step."
        raw_text = None
        usn = None
        status = "failed"

    _upload_to_object_storage(object_key, image)

    with session_scope() as session:
        upload = usn_uploads_repo.save_upload(
            session,
            site_id=site_id,
            document_type=document_type,
            object_storage_key=object_key,
            extraction_status=status,
            ocr_raw_text=raw_text,
        )
        session.commit()
        upload_id = upload.id

    return UsnExtractionPreview(
        upload_id=upload_id, usn=usn, usn_source=usn_source, extraction_status=status
    )


def extract_from_bill(image: bytes, site_id: str) -> UsnExtractionPreview:
    """USN-02. Never auto-persists a usn value onto a Site — see
    confirm_and_finalize()."""
    return _capture_and_extract(image, site_id, document_type="bill", usn_source="bill_ocr")


def extract_from_payment_proof(image: bytes, site_id: str) -> UsnExtractionPreview:
    """USN-03. Same discipline as extract_from_bill()."""
    return _capture_and_extract(
        image, site_id, document_type="payment_proof", usn_source="payment_proof_ocr"
    )


def confirm_and_finalize(upload_id: str, confirmed_usn: str, confirmed_by: str) -> UsnCapture:
    """USN-02/03's confirm-before-store step. Validates the (possibly
    operator-corrected) value and marks the evidence row confirmed.
    Persisting the result onto Site.usn is the caller's job, via
    repositories.sites.update_usn() (now implemented — see
    routers/app_usn.py's /confirm route, the one caller). confirmed_by
    is accepted now for the audit trail even though nothing persists it
    beyond the evidence row's status change yet."""
    del confirmed_by  # accepted for the audit-trail API shape; not yet persisted anywhere

    validated = _validate_usn_format(confirmed_usn)

    with session_scope() as session:
        upload = usn_uploads_repo.get_upload(session, upload_id)
        if upload is None:
            raise ValueError(f"No usn_ocr_uploads row for id={upload_id}")
        usn_source: UsnSource = "bill_ocr" if upload.document_type == "bill" else "payment_proof_ocr"
        usn_uploads_repo.mark_confirmed(session, upload_id)
        session.commit()

    return UsnCapture(usn=validated, usn_source=usn_source)
