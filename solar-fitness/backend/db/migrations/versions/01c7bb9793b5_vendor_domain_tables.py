"""vendor domain tables

Owner: keerthana (Vendor domain, customer-account admin, jurisdictions).

Four new tables backing the vendor portal: vendors, vendor_jobs,
vendor_payouts, vendor_accuracy_history. district/state are stored
directly on vendor_jobs (denormalized) rather than read from sites,
since sites has no district/state columns yet (that's karthik's
separate, not-yet-landed site-domain workstream) — this table doesn't
need to wait on it.

Also backfills the FK the users migration (f8a3c1d9e6b2) deliberately
left off users.vendor_id, now that vendors exists.

There is deliberately no seed/creation path for vendor_jobs here or
anywhere yet — the frontend has no "assign a vendor to a site" flow at
all (see keerthana's build-plan gap note). This migration only creates
the schema; the table is expected to stay empty until that gap is
closed.

Revision ID: 01c7bb9793b5
Revises: f8a3c1d9e6b2
Create Date: 2026-08-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "01c7bb9793b5"
down_revision: str | Sequence[str] | None = "f8a3c1d9e6b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vendors",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("verification_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("availability", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("accuracy_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "service_area",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("payout_method_type", sa.String(16), nullable=False),
        sa.Column("payout_masked_account", sa.String(64), nullable=False),
        sa.Column(
            "documents",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "verification_status in ('verified', 'pending', 'rejected', 'suspended')",
            name="ck_vendors_verification_status",
        ),
        sa.CheckConstraint(
            "payout_method_type in ('UPI', 'Bank transfer')", name="ck_vendors_payout_method_type"
        ),
    )

    op.create_table(
        "vendor_jobs",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "site_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sites.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "vendor_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vendors.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("district", sa.String(255), nullable=False),
        sa.Column("state", sa.String(255), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payout_inr", sa.Numeric(), nullable=False),
        sa.Column(
            "requirements",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("distance_km", sa.Float(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("estimated_capacity_kwp", sa.Float(), nullable=True),
        sa.Column("measured_capacity_kwp", sa.Float(), nullable=True),
        sa.Column("reconciled_payout_inr", sa.Numeric(), nullable=True),
        sa.Column("variance_pct", sa.Float(), nullable=True),
        sa.Column("dispute_status", sa.String(16), nullable=True, server_default="none"),
        sa.Column("dispute_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status in ('queued', 'accepted', 'in_progress', 'submitted', 'sla_at_risk', 'overdue')",
            name="ck_vendor_jobs_status",
        ),
        sa.CheckConstraint(
            "dispute_status in ('none', 'open', 'resolved')", name="ck_vendor_jobs_dispute_status"
        ),
    )

    op.create_table(
        "vendor_payouts",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "vendor_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vendors.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "job_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vendor_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("amount", sa.Numeric(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.CheckConstraint(
            "status in ('pending', 'paid', 'disputed')", name="ck_vendor_payouts_status"
        ),
        sa.CheckConstraint(
            "method in ('UPI', 'Bank transfer')", name="ck_vendor_payouts_method"
        ),
    )

    op.create_table(
        "vendor_accuracy_history",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "vendor_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vendors.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("label", sa.String(64), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    # Backfill the FK the users migration deliberately left off.
    op.create_foreign_key(
        "fk_users_vendor_id", "users", "vendors", ["vendor_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_vendor_id", "users", type_="foreignkey")
    op.drop_table("vendor_accuracy_history")
    op.drop_table("vendor_payouts")
    op.drop_table("vendor_jobs")
    op.drop_table("vendors")
