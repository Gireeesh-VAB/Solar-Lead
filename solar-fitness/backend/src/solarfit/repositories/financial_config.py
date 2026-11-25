"""FIN-02 admin configuration — versioned, DB-backed financial assumptions.

Distinct from packs/config_pack.py's YAML pack: the coefficients FIN-01
already uses (installation cost/kWp, subsidy scheme, panel degradation,
system lifetime, base tariff) stay in the YAML pack unchanged, so the
two engines never disagree about a value both read. This table holds
only the NEW assumptions engine/financial_projection.py needs that never
existed anywhere in this codebase before (tariff escalation, export/
feed-in rate, default self-consumption ratio, maintenance cost,
financing defaults) — see that module's own docstring.

Versioned by insert-only: saving a change creates a new row rather than
overwriting the current one (get_current() always reads the highest
`id`), so a financial_projections row that stamped an old
assumptions_version keeps meaning exactly what it meant when it was
computed — the spec's own "old customer calculations should not
silently change unless explicitly recalculated" requirement. `id`
doubles as the version number.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Integer, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from solarfit.db import Base

__all__ = ["FinancialAssumptionsRow", "DEFAULT_ASSUMPTIONS", "get_current", "get_version", "create_version"]


# Seeded as version 1 by migration d3f8a2c1e947 — sensible placeholder
# defaults, same "placeholder pending real-world tuning" discipline as
# every other config-pack coefficient in this codebase. An admin edits
# these for real via PATCH /app/admin/financial-config, never a source
# change.
DEFAULT_ASSUMPTIONS: dict = {
    "tariff_escalation_pct_per_year": 3.0,
    "export_tariff_inr_per_kwh": 3.5,
    "default_self_consumption_ratio": 0.7,
    "annual_maintenance_cost_inr_per_kwp": 500.0,
    "inverter_replacement_year": 12,
    "inverter_replacement_cost_inr_per_kwp": 8000.0,
    "financing_default_down_payment_pct": 20.0,
    "financing_default_interest_rate_pct": 10.5,
    "financing_default_tenure_years": 5.0,
    # FIN-03 — seasonal consumption model (engine/seasonal_consumption.py).
    # Every key below is read via `.get(key, DEFAULT_ASSUMPTIONS[key])` at
    # call sites, never a bare `assumptions[key]` — so an ADMIN ROW SAVED
    # BEFORE THESE KEYS EXISTED still works unchanged, no migration/backfill
    # needed for the flexible `values` JSON column.
    "annual_consumption_growth_pct": 2.0,
    "rainy_season_factor_pct": 50.0,
    "summer_months": 4,
    "rainy_months": 4,
    "winter_months": 4,
    # FIN-03 — seasonal generation model (engine/seasonal_financial_projection.py).
    # Flat fallback shares (must sum to ~1.0), used only when no real
    # PVGIS monthly breakdown is available for this assessment.
    "summer_generation_share": 0.36,
    "rainy_generation_share": 0.28,
    "winter_generation_share": 0.36,
    # Calendar months (1=Jan..12=Dec) PVGIS's real monthly output is
    # bucketed into when it IS available — a typical Indian seasonal
    # calendar, admin-adjustable for other climates.
    "season_calendar_months": {
        "summer": [3, 4, 5, 6],
        "rainy": [7, 8, 9, 10],
        "winter": [11, 12, 1, 2],
    },
}


class FinancialAssumptionsRow(Base):
    __tablename__ = "financial_assumptions"

    # Serial PK doubles as the version number — see module docstring.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    values: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def get_current(session: Session) -> FinancialAssumptionsRow:
    """The highest-id row is always the current one — see module
    docstring. Migration d3f8a2c1e947 seeds version 1, so this never
    returns None in practice; a fresh, un-migrated database is a setup
    error the caller should let surface, not paper over."""
    stmt = select(FinancialAssumptionsRow).order_by(FinancialAssumptionsRow.id.desc()).limit(1)
    row = session.scalars(stmt).first()
    if row is None:
        raise RuntimeError("financial_assumptions has no rows — has migration d3f8a2c1e947 run?")
    return row


def get_version(session: Session, version: int) -> FinancialAssumptionsRow | None:
    """Reads a SPECIFIC historical version — what a stored
    financial_projections row's own assumptions_version points at, so a
    past projection can always be explained against the assumptions that
    actually produced it, even after the admin has since changed them."""
    return session.get(FinancialAssumptionsRow, version)


def create_version(
    session: Session, *, values: dict, created_by: str, note: str | None = None
) -> FinancialAssumptionsRow:
    """Insert-only — never updates a prior version in place."""
    row = FinancialAssumptionsRow(
        values=values, created_by=created_by, note=note, created_at=datetime.now(UTC)
    )
    session.add(row)
    session.flush()
    return row
