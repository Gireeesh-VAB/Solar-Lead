"""The vendor crew's view of an installation project.

Split into its own module rather than appended to app_vendor.py: that
file is already ~670 lines covering the whole survey portal (jobs,
profile, payouts, submissions, six assessment sections), and the install
flow is a second, independent lifecycle on different tables. It keeps
app_vendor.py's every convention though — same /app/vendor prefix, same
require_role("vendor"), same "which vendor am I comes from
current_user().vendor_id, never from the request" rule, same
replace-wholesale semantics for the checklist.

Scoping: every route resolves the caller's own vendor_id and then
refuses any project not assigned to it, with a 404 rather than a 403 —
app_vendor.py's _job_or_404() sets that precedent, and leaking "this id
exists but isn't yours" would be a small enumeration oracle.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from solarfit.auth_users import AuthenticatedUser, require_role
from solarfit.db import get_session
from solarfit.repositories import audit as audit_repo
from solarfit.repositories import installations as repo
from solarfit.routers.common import actor_audit_fields, request_audit_meta
from solarfit.routers.installations_common import (
    AdvanceStatusRequest,
    CommissioningRecordOut,
    CommissioningUpdateRequest,
    InstallationPhotoOut,
    InstallationPhotoRequest,
    InstallationProjectOut,
    InstallationQcChecklistOut,
    QcChecklistRequest,
    commissioning_out,
    empty_qc_out,
    photo_out,
    project_out,
    qc_out,
)

router = APIRouter(prefix="/app/vendor/installations", tags=["app-vendor-installations"])


def _require_vendor_id(user: AuthenticatedUser) -> str:
    """Identical to app_vendor.py's helper — duplicated rather than
    imported so this module has no dependency on that file's internals."""
    if user.vendor_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no vendor profile linked to this account")
    return user.vendor_id


def _own_project_or_404(
    session: Session, project_id: str, vendor_id: str
) -> repo.InstallationProjectRow:
    row = repo.get_project(session, project_id)
    if row is None or str(row.assigned_vendor_id) != str(vendor_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "installation project not found")
    return row


def _audit_installation_action(
    session: Session,
    request: Request,
    user: AuthenticatedUser,
    project: repo.InstallationProjectRow,
    *,
    action: str,
    details: str,
    previous_value: dict | None = None,
    new_value: dict | None = None,
) -> None:
    """Same shared-helper shape as app_vendor.py::_audit_job_action — the
    install pipeline's own "Technical/Project Work"/"Site Visit" audit
    categories (spec section 6). project_id is the site id, matching the
    convention every other stage of this lifecycle (assessment ->
    vendor_job -> installation) already logs under."""
    audit_repo.write_audit_log(
        session,
        **actor_audit_fields(user),
        action=action,
        target=str(project.id),
        details=details,
        entity_type="installation_project",
        project_id=str(project.site_id),
        vendor_id=str(project.assigned_vendor_id) if project.assigned_vendor_id else None,
        previous_value=previous_value,
        new_value=new_value,
        **request_audit_meta(request),
    )


@router.get("", response_model=list[InstallationProjectOut])
def list_my_installations(
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
    project_status: Annotated[str | None, Query(alias="status")] = None,
) -> list[InstallationProjectOut]:
    vendor_id = _require_vendor_id(user)
    return [
        project_out(r)
        for r in repo.list_projects_for_vendor(session, vendor_id, status=project_status)
    ]


@router.get("/{project_id}", response_model=InstallationProjectOut)
def get_my_installation(
    project_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> InstallationProjectOut:
    vendor_id = _require_vendor_id(user)
    return project_out(_own_project_or_404(session, project_id, vendor_id))


@router.patch("/{project_id}/status", response_model=InstallationProjectOut)
def advance_installation_status(
    project_id: str,
    payload: AdvanceStatusRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> InstallationProjectOut:
    """The crew moving the job along. `status` is validated against
    INSTALLATION_STAGES to catch typos only — no ordering enforcement
    (VendorJobRow.status's convention), because real installs skip
    stages (no battery, no lightning protection on a small roof) and a
    crew must be able to correct a mis-tap.

    "completed" is refused here on purpose: only the admin's
    commissioning approval ends a project."""
    vendor_id = _require_vendor_id(user)
    existing = _own_project_or_404(session, project_id, vendor_id)
    # A plain string snapshot, not a reference — existing and the row
    # repo.advance_status() returns share the same SQLAlchemy identity, so
    # existing.status would otherwise already read back the NEW value.
    previous_status = existing.status
    if payload.status not in repo.INSTALLATION_STAGES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"unknown stage: {payload.status}")
    if payload.status == "completed":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "a project is only completed by admin commissioning approval",
        )
    row = repo.advance_status(
        session,
        project_id,
        status=payload.status,
        panel_model=payload.panel_model,
        inverter_model=payload.inverter_model,
    )
    assert row is not None
    _audit_installation_action(
        session, request, user, row, action="installation.status_changed",
        details=f"{user.email} set installation project {project_id} to {payload.status}",
        previous_value={"status": previous_status},
        new_value={"status": payload.status},
    )
    session.commit()
    return project_out(row)


# --------------------------------------------------------------------- #
# QC checklist
# --------------------------------------------------------------------- #


@router.get("/{project_id}/qc", response_model=InstallationQcChecklistOut)
def get_my_qc_checklist(
    project_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> InstallationQcChecklistOut:
    vendor_id = _require_vendor_id(user)
    _own_project_or_404(session, project_id, vendor_id)
    row = repo.get_checklist(session, project_id)
    return empty_qc_out(project_id) if row is None else qc_out(row)


@router.patch("/{project_id}/qc", response_model=InstallationQcChecklistOut)
def save_my_qc_checklist(
    project_id: str,
    payload: QcChecklistRequest,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> InstallationQcChecklistOut:
    """A working save — the crew's in-progress checklist, replaced
    wholesale on every save (the form is one page). Does not submit."""
    vendor_id = _require_vendor_id(user)
    _own_project_or_404(session, project_id, vendor_id)
    row = repo.set_checklist(session, project_id, checklist=payload.checklist, notes=payload.notes)
    session.commit()
    return qc_out(row)


@router.post("/{project_id}/qc/submit", response_model=InstallationQcChecklistOut)
def submit_my_qc_checklist(
    project_id: str,
    payload: QcChecklistRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> InstallationQcChecklistOut:
    """Declares the checklist done — stamps submitted_at, which is what
    the admin's /qc/approve gate requires. 409s once approved, so an
    approved checklist can't be quietly rewritten underneath the
    approval."""
    vendor_id = _require_vendor_id(user)
    project = _own_project_or_404(session, project_id, vendor_id)
    existing = repo.get_checklist(session, project_id)
    if existing is not None and existing.approved_at is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "this QC checklist is already approved and cannot be resubmitted"
        )
    row = repo.set_checklist(
        session, project_id, checklist=payload.checklist, notes=payload.notes, submitted=True
    )
    _audit_installation_action(
        session, request, user, project, action="installation.qc_submitted",
        details=f"{user.email} submitted the QC checklist for installation project {project_id}",
    )
    session.commit()
    return qc_out(row)


# --------------------------------------------------------------------- #
# photos
# --------------------------------------------------------------------- #


@router.post(
    "/{project_id}/photos",
    response_model=InstallationPhotoOut,
    status_code=status.HTTP_201_CREATED,
)
def add_installation_photo(
    project_id: str,
    payload: InstallationPhotoRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> InstallationPhotoOut:
    """Geotagged stage evidence. The photo is an inline base64 data URL
    (there is no file-storage service in this project) and lat/lng sit
    beside it exactly as they do on ObstacleSurveyItem."""
    vendor_id = _require_vendor_id(user)
    project = _own_project_or_404(session, project_id, vendor_id)
    if payload.stage not in repo.INSTALLATION_STAGES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"unknown stage: {payload.stage}")
    row = repo.add_photo(
        session,
        project_id,
        stage=payload.stage,
        data_url=payload.data_url,
        lat=payload.lat,
        lng=payload.lng,
        surveyor=user.email,
    )
    _audit_installation_action(
        session, request, user, project, action="installation.photo_uploaded",
        details=f"{user.email} uploaded a {payload.stage} photo for installation project {project_id}",
        new_value={"stage": payload.stage, "lat": payload.lat, "lng": payload.lng},
    )
    session.commit()
    return photo_out(row)


@router.get("/{project_id}/photos", response_model=list[InstallationPhotoOut])
def list_my_installation_photos(
    project_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
    stage: str | None = None,
) -> list[InstallationPhotoOut]:
    vendor_id = _require_vendor_id(user)
    _own_project_or_404(session, project_id, vendor_id)
    return [photo_out(p) for p in repo.list_photos(session, project_id, stage=stage)]


# --------------------------------------------------------------------- #
# commissioning
# --------------------------------------------------------------------- #


@router.get("/{project_id}/commissioning", response_model=CommissioningRecordOut)
def get_my_commissioning(
    project_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> CommissioningRecordOut:
    vendor_id = _require_vendor_id(user)
    _own_project_or_404(session, project_id, vendor_id)
    row = repo.get_commissioning(session, project_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no commissioning record for this project")
    return commissioning_out(row)


@router.post("/{project_id}/commissioning", response_model=CommissioningRecordOut)
def submit_my_commissioning(
    project_id: str,
    payload: CommissioningUpdateRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(require_role("vendor"))],
) -> CommissioningRecordOut:
    """The vendor's technical handover: what was actually installed and
    how it tested. Sets vendor_confirmed=True, which is the precondition
    for the admin's approval gate. 409s after admin approval so the
    approved record is immutable.

    exclude_unset means an omitted field is left alone rather than
    nulled — customer_accepted/admin_approved live on this same row and
    are written only by their own endpoints."""
    vendor_id = _require_vendor_id(user)
    project = _own_project_or_404(session, project_id, vendor_id)
    existing = repo.get_commissioning(session, project_id)
    if existing is not None and existing.admin_approved:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "commissioning is already approved and cannot be changed"
        )
    fields = payload.model_dump(by_alias=False, exclude_unset=True)
    fields["vendor_confirmed"] = True
    row = repo.set_commissioning(session, project_id, fields=fields)
    _audit_installation_action(
        session, request, user, project, action="installation.commissioning_submitted",
        details=f"{user.email} submitted the commissioning record for installation project {project_id}",
    )
    session.commit()
    return commissioning_out(row)
