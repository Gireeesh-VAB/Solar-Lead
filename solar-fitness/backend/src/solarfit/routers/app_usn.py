"""Owner: omkar (Scoring, USN & Assessment API).

Roadmap workstream "USN HTTP routes" — 4 endpoints giving
providers/usn_ocr.py's already-built OCR pipeline an HTTP surface for
the first time. Every route 422s immediately on a non-billing-linked
site type (USN-05), before ever calling into providers/usn_ocr.py.

current_user() only, no role restriction — the roadmap doesn't specify
one, and USN capture is naturally something the site's own
customer/vendor performs, not an admin-only action (flagged assumption).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from sqlalchemy.orm import Session

from solarfit.auth_users import AuthenticatedUser, current_user
from solarfit.db import get_session
from solarfit.domain.site import BILLING_LINKED_SITE_TYPES
from solarfit.providers import usn_ocr
from solarfit.repositories import sites as sites_repo

router = APIRouter(prefix="/app/sites/{site_id}/usn", tags=["app-usn"])


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ManualUsnRequest(_CamelModel):
    usn: str = Field(min_length=1, max_length=64)


class UsnCaptureResponse(_CamelModel):
    usn: str | None
    usn_source: str | None


class UsnExtractionPreviewResponse(_CamelModel):
    upload_id: str
    usn: str | None
    usn_source: str
    extraction_status: str


class ConfirmUsnRequest(_CamelModel):
    upload_id: str
    confirmed_usn: str = Field(min_length=1, max_length=64)


def _get_billing_linked_site(session: Session, site_id: str):
    site = sites_repo.get(session, site_id)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Site {site_id} not found")
    if site.site_type not in BILLING_LINKED_SITE_TYPES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Site type {site.site_type} is not billing-linked — USN capture doesn't apply.",
        )
    return site


@router.post("/manual", response_model=UsnCaptureResponse)
def capture_manual_usn(
    site_id: str,
    payload: ManualUsnRequest,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> UsnCaptureResponse:
    """USN-01. Manual entry persists immediately — no confirm step,
    unlike the OCR paths, since there's no extraction to double-check."""
    del user
    _get_billing_linked_site(session, site_id)

    try:
        capture = usn_ocr.capture_manual(payload.usn)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    site = sites_repo.update_usn(session, site_id, usn=capture.usn, usn_source=capture.usn_source)
    return UsnCaptureResponse(usn=site.usn.usn, usn_source=site.usn.usn_source)


@router.post("/bill", response_model=UsnExtractionPreviewResponse)
def capture_bill_usn(
    site_id: str,
    file: Annotated[UploadFile, File(description="A photo/scan of an electricity bill")],
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> UsnExtractionPreviewResponse:
    """USN-02. Returns a preview — never auto-persisted onto the Site.
    The evidence row + object-storage upload DO happen immediately
    (USN-06), regardless of whether extraction succeeds."""
    del user
    _get_billing_linked_site(session, site_id)

    image = file.file.read()
    preview = usn_ocr.extract_from_bill(image, site_id)
    return UsnExtractionPreviewResponse(**preview.model_dump())


@router.post("/payment-proof", response_model=UsnExtractionPreviewResponse)
def capture_payment_proof_usn(
    site_id: str,
    file: Annotated[UploadFile, File(description="A photo/scan of a payment proof/transaction screenshot")],
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> UsnExtractionPreviewResponse:
    """USN-03. Same discipline as capture_bill_usn()."""
    del user
    _get_billing_linked_site(session, site_id)

    image = file.file.read()
    preview = usn_ocr.extract_from_payment_proof(image, site_id)
    return UsnExtractionPreviewResponse(**preview.model_dump())


@router.post("/confirm", response_model=UsnCaptureResponse)
def confirm_usn(
    site_id: str,
    payload: ConfirmUsnRequest,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> UsnCaptureResponse:
    """USN-02/03/04. Validates the (possibly operator-corrected) value,
    marks the evidence row confirmed, and — the step that was missing
    until repositories/sites.py::update_usn() existed — actually writes
    it onto the Site."""
    _get_billing_linked_site(session, site_id)

    try:
        capture = usn_ocr.confirm_and_finalize(
            payload.upload_id, payload.confirmed_usn, confirmed_by=user.id
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    site = sites_repo.update_usn(session, site_id, usn=capture.usn, usn_source=capture.usn_source)
    return UsnCaptureResponse(usn=site.usn.usn, usn_source=site.usn.usn_source)
