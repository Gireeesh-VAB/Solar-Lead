"""Post-quotation installation project tracking.

Everything in this codebase up to now stops at "admin approved the
assessment and assigned a vendor to survey it" (routers/
app_assessments.py::approve_assessment -> repositories/vendors.py::
create_job). Nothing modelled what happens after the CUSTOMER accepts
the resulting quotation: material procurement, the physical install
stages, the QC checklist, and commissioning sign-off.

Why new tables rather than a discriminator column on vendor_jobs: that
table carries ~15 survey-specific columns (obstacle_survey,
structural_assessment, shading_notes, panorama_photo_data_url, the
payout/variance reconciliation set) that mean nothing for an install,
and an install needs child rows a survey never has (per-stage geotagged
photos, a QC checklist, a commissioning record). One table serving both
would be half-null in both directions.

Conventions deliberately reused rather than reinvented:
  - `status` is a plain free-form string with no state-machine
    validator, exactly like VendorJobRow.status — each router action
    just sets its target value. INSTALLATION_STAGES below is the
    canonical ordered list (the "backend emits symbolic keys, frontend
    owns the copy" pattern routers/assessments.py::ASSESSMENT_STAGES
    already established), used for progress display and for
    advance-by-one, not as an enforcement mechanism.
  - The QC checklist is one flat JSON blob on a single row per project,
    replaced wholesale — same tradeoff vendor_jobs.structural_assessment
    makes, for the same reason (this feature's own shape, not a frozen
    cross-team contract).
  - Photos are inline base64 data URLs. There is no file-storage service
    anywhere in this project; panorama_photo_data_url and every
    ObstacleSurveyItem.photo_data_url already work this way.

`id` is a String uuid (AssessmentRow.id's pattern) rather than a native
UUID column, so the customer/admin/vendor routers can pass check ids
and project ids around as plain strings interchangeably. The FK columns
pointing at OTHER people's tables (sites, vendors, vendor_jobs) stay
native UUID, because that is what those columns actually are.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, Session, mapped_column

from solarfit.db import Base

__all__ = [
    "INSTALLATION_STAGES",
    "QC_CHECKLIST_ITEMS",
    "CommissioningRecordRow",
    "InstallationPhotoRow",
    "InstallationProjectRow",
    "InstallationQcChecklistRow",
    "add_photo",
    "advance_status",
    "approve_checklist",
    "create_project",
    "get_checklist",
    "get_commissioning",
    "get_project",
    "get_project_for_site",
    "list_photos",
    "list_projects",
    "list_projects_for_vendor",
    "set_checklist",
    "set_commissioning",
    "stage_index",
]

# The ordered install pipeline. Machine-readable keys only — the
# frontend owns every human-facing label, same contract as
# routers/assessments.py::ASSESSMENT_STAGES. Order matters: it is what
# stage_index()/advance_status() walk, and what a progress strip counts
# against.
INSTALLATION_STAGES: list[str] = [
    "created",
    "material_procurement",
    "material_delivered",
    "installation_started",
    "mounting_installed",
    "panels_installed",
    "inverter_installed",
    "dc_wiring",
    "ac_wiring",
    "earthing",
    "lightning_protection",
    "electrical_testing",
    "inspection",
    "net_metering",
    "commissioning",
    "completed",
]

# The QC items the checklist blob carries. Kept here (not in the router)
# so the default/empty checklist and any future validation share one
# definition. Each is a nullable bool in the stored blob: None = not yet
# inspected, distinct from False = inspected and failed.
QC_CHECKLIST_ITEMS: list[str] = [
    "panel_alignment",
    "panel_spacing",
    "mounting_structure",
    "roof_anchoring",
    "waterproofing",
    "dc_cable_routing",
    "ac_cable_routing",
    "cable_protection",
    "mc4_connections",
    "dc_isolator",
    "ac_isolator",
    "inverter_installation",
    "earthing",
    "lightning_protection",
    "safety_labels",
    "warning_signs",
    "electrical_connections",
    "roof_damage_check",
    "water_leakage_check",
    "final_system_testing",
]


def stage_index(status: str) -> int:
    """Position of `status` in INSTALLATION_STAGES, or -1 if it isn't a
    known stage. Never raises — status is a free string by design, and a
    progress bar should degrade rather than 500 on an unexpected value."""
    try:
        return INSTALLATION_STAGES.index(status)
    except ValueError:
        return -1


class InstallationProjectRow(Base):
    """One physical installation, created when the customer accepts the
    quotation on an approved assessment."""

    __tablename__ = "installation_projects"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Provenance: which survey job led to this install. Nullable because
    # an assessment can be approved without a vendor_jobs row surviving
    # (SET NULL on job deletion), and because an admin could in principle
    # open a project against a site with no recorded survey.
    vendor_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendor_jobs.id", ondelete="SET NULL"), nullable=True
    )
    assigned_vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Free-form, no validator — VendorJobRow.status's convention. See
    # INSTALLATION_STAGES above for the canonical values.
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="created")
    approved_capacity_kwp: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    panel_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    inverter_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class InstallationQcChecklistRow(Base):
    """One row per project (project_id is unique). `checklist` is the
    flat blob of QC_CHECKLIST_ITEMS booleans plus free-text notes —
    replaced wholesale on save, same as vendor_jobs' assessment blobs."""

    __tablename__ = "installation_qc_checklist"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("installation_projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    checklist: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class InstallationPhotoRow(Base):
    """A geotagged progress photo, many per project. lat/lng sit beside
    the data URL exactly as ObstacleSurveyItem does in the survey flow —
    there is no shared GPS/photo helper in this codebase to reuse."""

    __tablename__ = "installation_photos"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(
        String, ForeignKey("installation_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_url: Mapped[str] = mapped_column(Text, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    surveyor: Mapped[str | None] = mapped_column(String(255), nullable=True)


class CommissioningRecordRow(Base):
    """Final handover: what was actually installed, the electrical test
    results, and the three-way sign-off (customer / vendor / admin).
    One row per project."""

    __tablename__ = "commissioning_records"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("installation_projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    installed_capacity_kwp: Mapped[float | None] = mapped_column(Float, nullable=True)
    installed_panel_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    panel_serial_numbers: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    inverter_serial_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meter_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    voltage_reading: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_reading: Mapped[float | None] = mapped_column(Float, nullable=True)
    earthing_test_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    insulation_test_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    commissioning_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    customer_accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    vendor_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    admin_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    final_photo_data_urls: Mapped[list] = mapped_column(JSON, nullable=False, default=list)


# --------------------------------------------------------------------- #
# projects
# --------------------------------------------------------------------- #


def create_project(
    session: Session,
    *,
    site_id: str | uuid.UUID,
    approved_capacity_kwp: float,
    vendor_job_id: str | uuid.UUID | None = None,
    assigned_vendor_id: str | uuid.UUID | None = None,
    panel_model: str | None = None,
    inverter_model: str | None = None,
    status: str = "created",
) -> InstallationProjectRow:
    """The single insert path for installation_projects, mirroring
    repositories/vendors.py::create_job()'s role for vendor_jobs. Called
    from routers/app_checks.py::accept_quotation() — the customer's
    quotation acceptance is the one event that opens a project."""
    now = datetime.now(UTC)
    row = InstallationProjectRow(
        id=str(uuid4()),
        site_id=uuid.UUID(str(site_id)),
        vendor_job_id=uuid.UUID(str(vendor_job_id)) if vendor_job_id is not None else None,
        assigned_vendor_id=(
            uuid.UUID(str(assigned_vendor_id)) if assigned_vendor_id is not None else None
        ),
        status=status,
        approved_capacity_kwp=approved_capacity_kwp,
        panel_model=panel_model,
        inverter_model=inverter_model,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.flush()
    return row


def get_project(session: Session, project_id: str) -> InstallationProjectRow | None:
    return session.get(InstallationProjectRow, project_id)


def get_project_for_site(session: Session, site_id: str | uuid.UUID) -> InstallationProjectRow | None:
    """Newest project for a site. Nothing forbids a second project on the
    same roof (a later expansion), so this returns the most recent rather
    than assuming uniqueness."""
    try:
        sid = uuid.UUID(str(site_id))
    except (ValueError, AttributeError, TypeError):
        return None
    stmt = (
        select(InstallationProjectRow)
        .where(InstallationProjectRow.site_id == sid)
        .order_by(InstallationProjectRow.created_at.desc())
        .limit(1)
    )
    return session.scalars(stmt).first()


def list_projects(session: Session, *, status: str | None = None) -> list[InstallationProjectRow]:
    stmt = select(InstallationProjectRow).order_by(InstallationProjectRow.created_at.desc())
    if status is not None:
        stmt = stmt.where(InstallationProjectRow.status == status)
    return list(session.scalars(stmt))


def list_projects_for_vendor(
    session: Session, vendor_id: str | uuid.UUID, *, status: str | None = None
) -> list[InstallationProjectRow]:
    """Vendor scoping happens one layer up in the router (from
    current_user().vendor_id), never from a caller-supplied id — same
    rule as repositories/vendors.py."""
    try:
        vid = uuid.UUID(str(vendor_id))
    except (ValueError, AttributeError, TypeError):
        return []
    stmt = (
        select(InstallationProjectRow)
        .where(InstallationProjectRow.assigned_vendor_id == vid)
        .order_by(InstallationProjectRow.created_at.desc())
    )
    if status is not None:
        stmt = stmt.where(InstallationProjectRow.status == status)
    return list(session.scalars(stmt))


def advance_status(
    session: Session,
    project_id: str,
    *,
    status: str,
    panel_model: str | None = None,
    inverter_model: str | None = None,
) -> InstallationProjectRow | None:
    """Overwrites status outright — no transition validation, matching
    repositories/vendors.py::update_job_status(). panel_model/
    inverter_model are only written when supplied, so a plain stage
    advance never blanks equipment already recorded."""
    row = session.get(InstallationProjectRow, project_id)
    if row is None:
        return None
    row.status = status
    if panel_model is not None:
        row.panel_model = panel_model
    if inverter_model is not None:
        row.inverter_model = inverter_model
    row.updated_at = datetime.now(UTC)
    session.flush()
    return row


# --------------------------------------------------------------------- #
# QC checklist
# --------------------------------------------------------------------- #


def get_checklist(session: Session, project_id: str) -> InstallationQcChecklistRow | None:
    stmt = select(InstallationQcChecklistRow).where(
        InstallationQcChecklistRow.project_id == project_id
    )
    return session.scalars(stmt).first()


def set_checklist(
    session: Session,
    project_id: str,
    *,
    checklist: dict[str, Any],
    notes: str | None = None,
    submitted: bool = False,
) -> InstallationQcChecklistRow:
    """Upserts the project's one checklist row, replacing the blob
    wholesale (the field form is a single page, not incremental
    patches). `submitted=True` stamps submitted_at — the vendor
    declaring the checklist done, which is what an admin then approves."""
    row = get_checklist(session, project_id)
    if row is None:
        row = InstallationQcChecklistRow(id=str(uuid4()), project_id=project_id, checklist={})
        session.add(row)
    row.checklist = dict(checklist)
    row.notes = notes
    if submitted:
        row.submitted_at = datetime.now(UTC)
    session.flush()
    return row


def approve_checklist(
    session: Session, project_id: str, *, admin_email: str
) -> InstallationQcChecklistRow | None:
    row = get_checklist(session, project_id)
    if row is None:
        return None
    row.approved_at = datetime.now(UTC)
    row.approved_by = admin_email
    session.flush()
    return row


# --------------------------------------------------------------------- #
# photos
# --------------------------------------------------------------------- #


def add_photo(
    session: Session,
    project_id: str,
    *,
    stage: str,
    data_url: str,
    lat: float | None = None,
    lng: float | None = None,
    surveyor: str | None = None,
) -> InstallationPhotoRow:
    row = InstallationPhotoRow(
        id=str(uuid4()),
        project_id=project_id,
        stage=stage,
        data_url=data_url,
        lat=lat,
        lng=lng,
        surveyor=surveyor,
        captured_at=datetime.now(UTC),
    )
    session.add(row)
    session.flush()
    return row


def list_photos(
    session: Session, project_id: str, *, stage: str | None = None
) -> list[InstallationPhotoRow]:
    stmt = (
        select(InstallationPhotoRow)
        .where(InstallationPhotoRow.project_id == project_id)
        .order_by(InstallationPhotoRow.captured_at.desc())
    )
    if stage is not None:
        stmt = stmt.where(InstallationPhotoRow.stage == stage)
    return list(session.scalars(stmt))


# --------------------------------------------------------------------- #
# commissioning
# --------------------------------------------------------------------- #


def get_commissioning(session: Session, project_id: str) -> CommissioningRecordRow | None:
    stmt = select(CommissioningRecordRow).where(CommissioningRecordRow.project_id == project_id)
    return session.scalars(stmt).first()


def set_commissioning(
    session: Session, project_id: str, *, fields: dict[str, Any]
) -> CommissioningRecordRow:
    """Upserts the project's one commissioning row. Only keys actually
    present in `fields` are written, so the vendor's technical submission
    and the three separate sign-off flags (customer/vendor/admin) can each
    write their own slice without clobbering the others."""
    row = get_commissioning(session, project_id)
    if row is None:
        row = CommissioningRecordRow(id=str(uuid4()), project_id=project_id)
        session.add(row)
    for key, value in fields.items():
        if hasattr(row, key) and key not in {"id", "project_id"}:
            setattr(row, key, value)
    session.flush()
    return row
