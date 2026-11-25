"""add vendor_reviews table

Real customer reviews of a vendor's completed work — nothing like this
existed before (VendorRow.accuracy_score is a separate, dormant field
that nothing computes for a real vendor; see repositories/vendors.py's
own module docstring). One review per installation project (the unique
constraint on installation_project_id), left only after the customer has
accepted the finished installation — app_checks.py::accept_installation
sets commissioning.customer_accepted, which the new review endpoint
gates on.

Revision ID: b935e7d7db65
Revises: 56d6f0c69930
Create Date: 2026-09-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b935e7d7db65"
down_revision: str | Sequence[str] | None = "56d6f0c69930"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vendor_reviews",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "vendor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vendors.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "installation_project_id",
            sa.String(),
            sa.ForeignKey("installation_projects.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("customer_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
    )
    op.create_check_constraint(
        "ck_vendor_reviews_rating_range", "vendor_reviews", "rating >= 1 AND rating <= 5"
    )
    op.create_index("ix_vendor_reviews_vendor_id", "vendor_reviews", ["vendor_id"])
    op.create_index("ix_vendor_reviews_created_at", "vendor_reviews", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_vendor_reviews_created_at", table_name="vendor_reviews")
    op.drop_index("ix_vendor_reviews_vendor_id", table_name="vendor_reviews")
    op.drop_table("vendor_reviews")
