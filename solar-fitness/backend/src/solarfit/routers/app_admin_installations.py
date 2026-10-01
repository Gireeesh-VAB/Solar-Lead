"""Admin oversight of installation projects.

The back half of the pipeline the admin surface never had: everything
after the customer accepts a quotation. Mirrors app_assessments.py's
admin-endpoint shape exactly — require_role("admin"), Depends(get_session),
CamelModel request/response bodies, guard-then-mutate-then-audit-then-
commit for anything that is a review decision.

Stage advancement is deliberately NOT a state machine (see
repositories/installations.py's docstring): the router validates the
target against INSTALLATION_STAGES only to reject typos, and never
enforces ordering — an admin correcting a mis-clicked stage must be able
to move backwards, and repositories/vendors.py's status handling set
this convention first.

The two REVIEW gates here (QC approval, commissioning approval) are the
ones that get the full approve_assessment() treatment: 409 on the wrong
prior state, write_audit_log(), commit.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from solarfit.auth_users import AuthenticatedUser, require_role
from solarfit.db import get_session
from solarfit.repositories import audit as audit_repo
from solarfit.repositories import installations as repo
from solarfit.routers.common import actor_audit_fields
from solarfit.routers.installations_common import (
    AdvanceStatusRequest,
    CommissioningRecordOut,
    CommissioningUpdateRequest,
    InstallationPhotoOut,
    InstallationProjectOut,
    InstallationQcChecklistOut,
    QcChecklistRequest,
    commissioning_out,
    empty_qc_out,
    photo_out,
    project_out,
    qc_out,
)

router = APIRouter(prefix="/app/admin/installations", tags=["app-admin-installations"])


def _project_or_404(session: Session, project_id: str) -> repo.InstallationProjectRow:
    row = repo.get_project(session, project_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "installation project not found")
    return row


@router.get("", response_model=list[InstallationProjectOut])
def list_installation_projects(
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
    project_status: Annotated[str | None, Query(alias="status")] = None,
) -> list[InstallationProjectOut]:
    return [project_out(r) for r in repo.list_projects(session, status=project_status)]


@router.get("/{project_id}", response_model=InstallationProjectOut)
def get_installation_project(
    project_id: str,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> InstallationProjectOut:
    return project_out(_project_or_404(session, project_id))


@router.patch("/{project_id}/status", response_model=InstallationProjectOut)
def set_installation_status(
    project_id: str,
    payload: AdvanceStatusRequest,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> InstallationProjectOut:
    """Admin override of the stage. Validates membership in
    INSTALLATION_STAGES (a typo'd stage would silently break every
    progress display) but not ordering — an admin correcting a mistake
    needs to move backwards."""
    existing = _project_or_404(session, project_id)
    # A plain string snapshot, not a reference — existing and the row
    # repo.advance_status() returns share the same SQLAlchemy identity, so
    # existing.status would otherwise already read back the NEW value.
    previous_status = existing.status
    if payload.status not in repo.INSTALLATION_STAGES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"unknown stage: {payload.status}")
    row = repo.advance_status(
        session,
        project_id,
        status=payload.status,
        panel_model=payload.panel_model,
        inverter_model=payload.inverter_model,
    )
    assert row is not None  # _project_or_404 already proved it exists
    audit_repo.write_audit_log(
        session,
        **actor_audit_fields(admin),
        action="installation.status_changed",
        target=project_id,
        details=f"{admin.email} set installation project {project_id} to {payload.status}",
        entity_type="installation_project",
        project_id=str(existing.site_id),
        vendor_id=str(existing.assigned_vendor_id) if existing.assigned_vendor_id else None,
        previous_value={"status": previous_status},
        new_value={"status": payload.status},
    )
    session.commit()
    return project_out(row)


# --------------------------------------------------------------------- #
# QC checklist
# --------------------------------------------------------------------- #


@router.get("/{project_id}/qc", response_model=InstallationQcChecklistOut)
def get_qc_checklist(
    project_id: str,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> InstallationQcChecklistOut:
    _project_or_404(session, project_id)
    row = repo.get_checklist(session, project_id)
    return empty_qc_out(project_id) if row is None else qc_out(row)


@router.patch("/{project_id}/qc", response_model=InstallationQcChecklistOut)
def save_qc_checklist(
    project_id: str,
    payload: QcChecklistRequest,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> InstallationQcChecklistOut:
    """Admin correction of a vendor-filled checklist. Replaces the blob
    wholesale, same as every assessment section on app_vendor.py. Does
    NOT stamp submitted_at — that is the vendor's own declaration."""
    _project_or_404(session, project_id)
    row = repo.set_checklist(session, project_id, checklist=payload.checklist, notes=payload.notes)
    session.commit()
    return qc_out(row)


@router.post("/{project_id}/qc/approve", response_model=InstallationQcChecklistOut)
def approve_qc_checklist(
    project_id: str,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> InstallationQcChecklistOut:
    """A review gate, so it gets approve_assessment()'s exact shape:
    409 unless the vendor has actually submitted the checklist (and
    unless it isn't already approved), flip the state, audit, commit."""
    existing = _project_or_404(session, project_id)
    row = repo.get_checklist(session, project_id)
    if row is None or row.submitted_at is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "the QC checklist has not been submitted by the vendor yet"
        )
    if row.approved_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "the QC checklist is already approved")

    row = repo.approve_checklist(session, project_id, admin_email=admin.email)
    assert row is not None
    audit_repo.write_audit_log(
        session,
        **actor_audit_fields(admin),
        action="installation.qc_approved",
        target=project_id,
        details=f"{admin.email} approved the QC checklist for installation project {project_id}",
        entity_type="installation_project",
        project_id=str(existing.site_id),
        vendor_id=str(existing.assigned_vendor_id) if existing.assigned_vendor_id else None,
    )
    session.commit()
    return qc_out(row)


# --------------------------------------------------------------------- #
# photos
# --------------------------------------------------------------------- #


@router.get("/{project_id}/photos", response_model=list[InstallationPhotoOut])
def list_installation_photos(
    project_id: str,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
    stage: str | None = None,
) -> list[InstallationPhotoOut]:
    _project_or_404(session, project_id)
    return [photo_out(p) for p in repo.list_photos(session, project_id, stage=stage)]


# --------------------------------------------------------------------- #
# commissioning
# --------------------------------------------------------------------- #


@router.get("/{project_id}/commissioning", response_model=CommissioningRecordOut)
def get_commissioning_record(
    project_id: str,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> CommissioningRecordOut:
    _project_or_404(session, project_id)
    row = repo.get_commissioning(session, project_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no commissioning record for this project")
    return commissioning_out(row)


@router.patch("/{project_id}/commissioning", response_model=CommissioningRecordOut)
def save_commissioning_record(
    project_id: str,
    payload: CommissioningUpdateRequest,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> CommissioningRecordOut:
    """Admin correction of the vendor's technical figures. exclude_unset
    is load-bearing: an omitted field must stay untouched rather than
    being nulled, since the customer's and vendor's sign-off flags live
    on this same row."""
    _project_or_404(session, project_id)
    row = repo.set_commissioning(
        session, project_id, fields=payload.model_dump(by_alias=False, exclude_unset=True)
    )
    session.commit()
    return commissioning_out(row)


@router.post("/{project_id}/commissioning/approve", response_model=CommissioningRecordOut)
def approve_commissioning(
    project_id: str,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> CommissioningRecordOut:
    """The final gate. Requires the vendor to have confirmed first (the
    admin approves a submission, they don't author one), 409s if already
    approved, and moves the project itself to "completed" in the same
    transaction — nothing else would."""
    existing = _project_or_404(session, project_id)
    row = repo.get_commissioning(session, project_id)
    if row is None or not row.vendor_confirmed:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "the vendor has not confirmed commissioning yet"
        )
    if row.admin_approved:
        raise HTTPException(status.HTTP_409_CONFLICT, "commissioning is already approved")

    fields: dict = {"admin_approved": True}
    if row.commissioning_date is None:
        fields["commissioning_date"] = datetime.now(UTC)
    row = repo.set_commissioning(session, project_id, fields=fields)
    repo.advance_status(session, project_id, status="completed")
    audit_repo.write_audit_log(
        session,
        **actor_audit_fields(admin),
        action="installation.commissioning_approved",
        target=project_id,
        details=f"{admin.email} approved commissioning for installation project {project_id}",
        entity_type="installation_project",
        project_id=str(existing.site_id),
        vendor_id=str(existing.assigned_vendor_id) if existing.assigned_vendor_id else None,
        new_value={"status": "completed", "adminApproved": True},
    )
    session.commit()
    return commissioning_out(row)
