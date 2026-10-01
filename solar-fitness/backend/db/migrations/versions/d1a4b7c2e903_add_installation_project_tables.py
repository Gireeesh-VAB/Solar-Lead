"""add installation project tables

The post-quotation half of the pipeline, which had no schema at all:
once a customer accepts the quotation on an approved assessment, an
installation_projects row opens and tracks material procurement, the
physical install stages, QC and commissioning.

Four tables rather than a discriminator on vendor_jobs — see
repositories/installations.py's module docstring for why (vendor_jobs'
~15 survey-only columns don't apply, and an install needs child rows a
survey never has).

installation_projects.id is a String uuid (AssessmentRow.id's pattern),
so the child tables' project_id FKs are String too; the FKs pointing at
other teams' tables (sites, vendors, vendor_jobs) stay native UUID
because that is what those columns already are.

Revision ID: d1a4b7c2e903
Revises: c9d2e5f8a1b4
Create Date: 2026-09-09

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d1a4b7c2e903"
down_revision: str | Sequence[str] | None = "c9d2e5f8a1b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "installation_projects",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "site_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "vendor_job_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vendor_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "assigned_vendor_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vendors.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="created"),
        sa.Column("approved_capacity_kwp", sa.Float(), nullable=False, server_default="0"),
        sa.Column("panel_model", sa.String(255), nullable=True),
        sa.Column("inverter_model", sa.String(255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_installation_projects_site_id", "installation_projects", ["site_id"])
    op.create_index(
        "ix_installation_projects_assigned_vendor_id", "installation_projects", ["assigned_vendor_id"]
    )

    op.create_table(
        "installation_qc_checklist",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(),
            sa.ForeignKey("installation_projects.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("checklist", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.String(255), nullable=True),
    )

    op.create_table(
        "installation_photos",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(),
            sa.ForeignKey("installation_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lng", sa.Float(), nullable=True),
        sa.Column("data_url", sa.Text(), nullable=False),
        sa.Column(
            "captured_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("surveyor", sa.String(255), nullable=True),
    )
    op.create_index("ix_installation_photos_project_id", "installation_photos", ["project_id"])

    op.create_table(
        "commissioning_records",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(),
            sa.ForeignKey("installation_projects.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("installed_capacity_kwp", sa.Float(), nullable=True),
        sa.Column("installed_panel_count", sa.Integer(), nullable=True),
        sa.Column("panel_serial_numbers", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("inverter_serial_number", sa.String(255), nullable=True),
        sa.Column("meter_number", sa.String(255), nullable=True),
        sa.Column("voltage_reading", sa.Float(), nullable=True),
        sa.Column("current_reading", sa.Float(), nullable=True),
        sa.Column("earthing_test_passed", sa.Boolean(), nullable=True),
        sa.Column("insulation_test_passed", sa.Boolean(), nullable=True),
        sa.Column("commissioning_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("customer_accepted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("vendor_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("admin_approved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("final_photo_data_urls", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_table("commissioning_records")
    op.drop_index("ix_installation_photos_project_id", table_name="installation_photos")
    op.drop_table("installation_photos")
    op.drop_table("installation_qc_checklist")
    op.drop_index(
        "ix_installation_projects_assigned_vendor_id", table_name="installation_projects"
    )
    op.drop_index("ix_installation_projects_site_id", table_name="installation_projects")
    op.drop_table("installation_projects")
