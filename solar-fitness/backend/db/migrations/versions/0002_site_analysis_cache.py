"""site analysis cache

CACHE-01: the shared, cross-tenant result cache, keyed on rounded
lat/long. See repositories/analysis_cache.py's SiteAnalysisCache ORM
model — this migration mirrors it and §14's DDL exactly.

Revision ID: a9fdffad41ca
Revises: 9e903dd3f06b
Create Date: 2026-08-25

"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a9fdffad41ca"
down_revision: str | Sequence[str] | None = "9e903dd3f06b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "site_analysis_cache",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lat_rounded", sa.Numeric(), nullable=False),
        sa.Column("lng_rounded", sa.Numeric(), nullable=False),
        sa.Column("boundary", geoalchemy2.Geometry("POLYGON", srid=4326), nullable=True),
        sa.Column("vision_refinement", postgresql.JSONB(), nullable=True),
        sa.Column("weather_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("panorama_url", sa.String(), nullable=True),
        sa.Column("ml_suitability_score", sa.Numeric(), nullable=True),
        sa.Column("ml_model_version", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_reused_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint(
        "uq_cache_latlng", "site_analysis_cache", ["lat_rounded", "lng_rounded"]
    )
    op.create_index(
        "ix_site_analysis_cache_lat_rounded", "site_analysis_cache", ["lat_rounded"]
    )
    op.create_index(
        "ix_site_analysis_cache_lng_rounded", "site_analysis_cache", ["lng_rounded"]
    )


def downgrade() -> None:
    op.drop_index("ix_site_analysis_cache_lng_rounded", table_name="site_analysis_cache")
    op.drop_index("ix_site_analysis_cache_lat_rounded", table_name="site_analysis_cache")
    op.drop_constraint("uq_cache_latlng", "site_analysis_cache", type_="unique")
    op.drop_table("site_analysis_cache")
