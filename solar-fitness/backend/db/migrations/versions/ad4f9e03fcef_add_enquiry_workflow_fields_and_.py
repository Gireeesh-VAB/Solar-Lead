"""add enquiry workflow fields and declined status

Customer/vendor/admin enquiry workflow — the feasibility check and the
vendor enquiry are now separate stages (see repositories/assessments.py::
save_assessment()'s updated docstring: a good verdict starts at
review_status="not_submitted", not "pending", until the customer
explicitly raises an enquiry via raise_enquiry()). These two new nullable
columns record that customer action distinctly from the admin's own
approve/reject action (reviewed_by/reviewed_at, already existing).

Also adds "declined" as a real, preserved vendor_jobs status — a vendor
declining an offered job used to delete the row entirely
(repositories/vendors.py::remove_job()); it now sets status="declined"
instead (decline_job()) so an admin can still see and reassign it.

No backfill: existing assessment rows already sitting in "pending" (or
beyond) predate this change and stay exactly where they are — they are
already real, in-flight reviews, never retroactively demoted to
"not_submitted".

Revision ID: ad4f9e03fcef
Revises: adcbefcf0240
Create Date: 2026-09-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ad4f9e03fcef"
down_revision: str | Sequence[str] | None = "adcbefcf0240"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assessments",
        sa.Column("customer_selected_vendor_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "assessments",
        sa.Column("enquiry_submitted_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Postgres has no ALTER CONSTRAINT — drop and recreate with the new value.
    op.drop_constraint("ck_vendor_jobs_status", "vendor_jobs", type_="check")
    op.create_check_constraint(
        "ck_vendor_jobs_status",
        "vendor_jobs",
        "status in ('queued', 'accepted', 'in_progress', 'submitted', 'sla_at_risk', 'overdue', 'declined')",
    )


def downgrade() -> None:
    # One-way risk, same as every other additive-then-behavior-changing
    # migration in this codebase: any row already sitting in "declined"
    # would violate the reverted constraint. Accepted, not backfilled.
    op.drop_constraint("ck_vendor_jobs_status", "vendor_jobs", type_="check")
    op.create_check_constraint(
        "ck_vendor_jobs_status",
        "vendor_jobs",
        "status in ('queued', 'accepted', 'in_progress', 'submitted', 'sla_at_risk', 'overdue')",
    )
    op.drop_column("assessments", "enquiry_submitted_at")
    op.drop_column("assessments", "customer_selected_vendor_id")
