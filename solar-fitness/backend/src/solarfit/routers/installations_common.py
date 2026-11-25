"""Shared request/response shapes for the installation-project surface.

Three routers read and write the same four tables from different angles
— app_admin_installations.py (oversight + QC/commissioning approval),
app_vendor_installations.py (the crew doing the work), and the
customer-facing endpoints on app_checks.py — so the wire shapes live
here rather than being redefined three times. Same reasoning as
routers/common.py's CamelModel: purely additive, no existing router
changes.

Every model is a CamelModel, so JSON keys match lib/types.ts
field-for-field the way the rest of the /app/* surface does.

CRITICAL: InstallationProjectOut's field names are deliberately
identical to InstallationProjectRow's column names. Anything that
round-trips a model through the ORM via **model_dump() breaks the
moment they diverge ("invalid keyword argument"), and the divergence is
invisible until runtime.
"""

from __future__ import annotations

from datetime import datetime

from solarfit.repositories import installations as repo
from solarfit.repositories.installations import (
    CommissioningRecordRow,
    InstallationPhotoRow,
    InstallationProjectRow,
    InstallationQcChecklistRow,
)
from solarfit.routers.common import CamelModel

__all__ = [
    "AdvanceStatusRequest",
    "CommissioningRecordOut",
    "CommissioningUpdateRequest",
    "InstallationPhotoOut",
    "InstallationPhotoRequest",
    "InstallationProjectOut",
    "InstallationQcChecklistOut",
    "QcChecklistRequest",
    "commissioning_out",
    "photo_out",
    "project_out",
    "qc_out",
]


class InstallationProjectOut(CamelModel):
    id: str
    site_id: str
    vendor_job_id: str | None = None
    assigned_vendor_id: str | None = None
    status: str
    approved_capacity_kwp: float
    panel_model: str | None = None
    inverter_model: str | None = None
    created_at: datetime
    updated_at: datetime
    # Derived, not stored: position of `status` within
    # repo.INSTALLATION_STAGES, and that whole ordered list — the same
    # "backend emits the ordered symbolic keys, frontend owns the copy"
    # contract routers/assessments.py::ASSESSMENT_STAGES set. -1 for a
    # status that isn't a known stage.
    stage_index: int
    stages: list[str]


class InstallationQcChecklistOut(CamelModel):
    project_id: str
    checklist: dict
    notes: str | None = None
    submitted_at: datetime | None = None
    approved_at: datetime | None = None
    approved_by: str | None = None


class QcChecklistRequest(CamelModel):
    """The whole checklist blob, replaced wholesale — the field form is
    one page, same convention as app_vendor.py's assessment sections.
    Item keys are repo.QC_CHECKLIST_ITEMS; each value is a nullable bool
    (None = not yet inspected, distinct from False = failed)."""

    checklist: dict[str, bool | None] = {}
    notes: str | None = None


class InstallationPhotoOut(CamelModel):
    id: str
    project_id: str
    stage: str
    lat: float | None = None
    lng: float | None = None
    data_url: str
    captured_at: datetime
    surveyor: str | None = None


class InstallationPhotoRequest(CamelModel):
    """Inline base64 data URL plus optional GPS — the same per-item
    shape ObstacleSurveyItem uses. There is no upload endpoint or file
    store anywhere in this project."""

    stage: str
    data_url: str
    lat: float | None = None
    lng: float | None = None


class CommissioningRecordOut(CamelModel):
    project_id: str
    installed_capacity_kwp: float | None = None
    installed_panel_count: int | None = None
    panel_serial_numbers: list[str] = []
    inverter_serial_number: str | None = None
    meter_number: str | None = None
    voltage_reading: float | None = None
    current_reading: float | None = None
    earthing_test_passed: bool | None = None
    insulation_test_passed: bool | None = None
    commissioning_date: datetime | None = None
    customer_accepted: bool = False
    vendor_confirmed: bool = False
    admin_approved: bool = False
    final_photo_data_urls: list[str] = []


class CommissioningUpdateRequest(CamelModel):
    """Every field optional and only written when explicitly supplied —
    the vendor's technical submission, the customer's acceptance and the
    admin's approval each touch their own slice of the one row without
    clobbering the others (see repo.set_commissioning())."""

    installed_capacity_kwp: float | None = None
    installed_panel_count: int | None = None
    panel_serial_numbers: list[str] | None = None
    inverter_serial_number: str | None = None
    meter_number: str | None = None
    voltage_reading: float | None = None
    current_reading: float | None = None
    earthing_test_passed: bool | None = None
    insulation_test_passed: bool | None = None
    commissioning_date: datetime | None = None
    final_photo_data_urls: list[str] | None = None


class AdvanceStatusRequest(CamelModel):
    """`status` is a free string by design (VendorJobRow.status's
    convention) — the routers validate it against repo.INSTALLATION_STAGES
    only to catch typos, they do not enforce transition order."""

    status: str
    panel_model: str | None = None
    inverter_model: str | None = None


def project_out(row: InstallationProjectRow) -> InstallationProjectOut:
    return InstallationProjectOut(
        id=row.id,
        site_id=str(row.site_id),
        vendor_job_id=str(row.vendor_job_id) if row.vendor_job_id else None,
        assigned_vendor_id=str(row.assigned_vendor_id) if row.assigned_vendor_id else None,
        status=row.status,
        approved_capacity_kwp=row.approved_capacity_kwp,
        panel_model=row.panel_model,
        inverter_model=row.inverter_model,
        created_at=row.created_at,
        updated_at=row.updated_at,
        stage_index=repo.stage_index(row.status),
        stages=repo.INSTALLATION_STAGES,
    )


def qc_out(row: InstallationQcChecklistRow) -> InstallationQcChecklistOut:
    return InstallationQcChecklistOut(
        project_id=row.project_id,
        checklist=row.checklist or {},
        notes=row.notes,
        submitted_at=row.submitted_at,
        approved_at=row.approved_at,
        approved_by=row.approved_by,
    )


def empty_qc_out(project_id: str) -> InstallationQcChecklistOut:
    """A never-yet-saved checklist reads back as every item None rather
    than a 404 — the vendor's form needs the item list to render, and
    "not yet inspected" is a real state, not a missing resource."""
    return InstallationQcChecklistOut(
        project_id=project_id,
        checklist=dict.fromkeys(repo.QC_CHECKLIST_ITEMS),
    )


def photo_out(row: InstallationPhotoRow) -> InstallationPhotoOut:
    return InstallationPhotoOut(
        id=row.id,
        project_id=row.project_id,
        stage=row.stage,
        lat=row.lat,
        lng=row.lng,
        data_url=row.data_url,
        captured_at=row.captured_at,
        surveyor=row.surveyor,
    )


def commissioning_out(row: CommissioningRecordRow) -> CommissioningRecordOut:
    return CommissioningRecordOut(
        project_id=row.project_id,
        installed_capacity_kwp=row.installed_capacity_kwp,
        installed_panel_count=row.installed_panel_count,
        panel_serial_numbers=list(row.panel_serial_numbers or []),
        inverter_serial_number=row.inverter_serial_number,
        meter_number=row.meter_number,
        voltage_reading=row.voltage_reading,
        current_reading=row.current_reading,
        earthing_test_passed=row.earthing_test_passed,
        insulation_test_passed=row.insulation_test_passed,
        commissioning_date=row.commissioning_date,
        customer_accepted=row.customer_accepted,
        vendor_confirmed=row.vendor_confirmed,
        admin_approved=row.admin_approved,
        final_photo_data_urls=list(row.final_photo_data_urls or []),
    )
