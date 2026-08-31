"""Owner: Person 4 (Scoring, USN & Assessment API).

Implements §9.9 Calibration (CAL-01..05) of
Solar_Fitness_Engine_Development_Document_v1.2 — tasks 8 and 9 of
Person 4's list in Rooftop_Backend_Implementation_Plan.html:

  CAL-01  On field survey submission, compute variance between remote
          and measured usable area; store the labelled pair with site
          type, region, geometry source, class.
  CAL-02  Flag variance-exceeds-threshold records; mark the remote
          estimate superseded.
  CAL-03  Recompute utilisation factors per class once the sample count
          crosses a threshold — surface for approval, never apply
          silently. Coordinate the config value itself with Person 2
          (solarfit.packs.config_pack).
  CAL-04  (Should) Variance-distribution report.
  CAL-05  Feed calibration state into FIT-04 confidence and the ML
          retraining set (engine/ml_score.py).

Assumption (flagged, not silent): CAL-01's "site type, region, geometry
source, class" — no definition of "class" exists anywhere in the source
material. Treated as synonymous with site_type, not a separate column.

Depends on: solarfit.domain.site.Site (frozen, Day 0),
solarfit.repositories.sites (Person 1's, still stub),
solarfit.repositories.analysis_cache (Person 3's, still stub except
round_latlng()), solarfit.packs.config_pack (frozen loader + this
person's own CAL-* accessors, Phase 0b).
"""

import statistics
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, select
from sqlalchemy.orm import Mapped, mapped_column

from solarfit.db import Base, session_scope
from solarfit.packs.config_pack import (
    get_calibration_sample_count_threshold,
    get_calibration_variance_threshold,
    get_utilisation_factor,
)
from solarfit.repositories import analysis_cache as analysis_cache_repo
from solarfit.repositories import sites as sites_repo


class CalibrationRecord(Base):
    __tablename__ = "calibration_records"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    site_id: Mapped[str] = mapped_column(String, index=True)
    site_type: Mapped[str] = mapped_column(String, index=True)
    region: Mapped[str] = mapped_column(String)  # site.jurisdiction
    geometry_source: Mapped[str | None] = mapped_column(String, nullable=True)
    remote_area_m2: Mapped[float | None] = mapped_column(Float, nullable=True)
    measured_area_m2: Mapped[float] = mapped_column(Float)
    variance_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    flagged_superseded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UtilisationFactorProposal(Base):
    __tablename__ = "utilisation_factor_proposals"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    site_type: Mapped[str] = mapped_column(String, index=True)
    current_factor: Mapped[float] = mapped_column(Float)
    proposed_factor: Mapped[float] = mapped_column(Float)
    sample_count: Mapped[int] = mapped_column(Integer)
    based_on_record_ids: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String)  # "proposed" | "approved" | "rejected"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String, nullable=True)


# ---------------------------------------------------------------------------
# Task 8 — CAL-01/02
# ---------------------------------------------------------------------------


def _remote_area_m2(site) -> float | None:
    """Looks up the cached remote usable-area estimate for a site's
    location via Person 3's analysis cache. Returns None (never a
    guess) if nothing is cached there yet."""
    lng, lat = site.centroid["coordinates"]
    lat_r, lng_r = analysis_cache_repo.round_latlng(lat, lng)
    cached = analysis_cache_repo.find_by_key(lat_r, lng_r)
    return cached.usable_area_m2 if cached else None


def record_field_survey(site_id: str, measured_area_m2: float) -> dict:
    """CAL-01/02. Computes variance between the remote (cached) usable
    area and a field-measured one, stores the labelled pair, and flags
    it when the variance exceeds the configured threshold."""
    with session_scope() as read_session:
        site = sites_repo.get(read_session, site_id)
    remote_area_m2 = _remote_area_m2(site) if site is not None else None

    with session_scope() as session:
        variance_pct: float | None = None
        if remote_area_m2:  # guard None and 0 — never divide by zero, never guess
            variance_pct = (measured_area_m2 - remote_area_m2) / remote_area_m2

        flagged = variance_pct is not None and abs(variance_pct) > get_calibration_variance_threshold()

        record = CalibrationRecord(
            id=str(uuid4()),
            site_id=site_id,
            site_type=site.site_type if site is not None else "UNKNOWN",
            region=site.jurisdiction if site is not None else "UNKNOWN",
            geometry_source=site.geometry_source if site is not None else None,
            remote_area_m2=remote_area_m2,
            measured_area_m2=measured_area_m2,
            variance_pct=variance_pct,
            flagged_superseded=flagged,
            created_at=datetime.now(UTC),
        )
        session.add(record)
        session.commit()

        return {
            "record_id": record.id,
            "remote_area_m2": remote_area_m2,
            "measured_area_m2": measured_area_m2,
            "variance_pct": variance_pct,
            "flagged_superseded": flagged,
        }


# ---------------------------------------------------------------------------
# Task 9 — CAL-03/04/05
# ---------------------------------------------------------------------------


def propose_utilisation_factor_update(site_type: str) -> dict | None:
    """CAL-03. Surfaces a proposed utilisation-factor correction for
    Person 2 to review — never writes packages/config-packs/*.yaml
    directly. Returns None below the configured minimum sample count."""
    with session_scope() as session:
        stmt = select(CalibrationRecord).where(
            CalibrationRecord.site_type == site_type,
            CalibrationRecord.variance_pct.is_not(None),
        )
        records = list(session.scalars(stmt).all())

        if len(records) < get_calibration_sample_count_threshold():
            return None

        ratios = [
            r.measured_area_m2 / r.remote_area_m2
            for r in records
            if r.remote_area_m2 is not None and r.remote_area_m2 > 0
        ]
        if not ratios:
            return None

        current_factor = get_utilisation_factor(site_type)
        proposed_factor = max(0.3, min(1.0, current_factor * statistics.median(ratios)))

        proposal = UtilisationFactorProposal(
            id=str(uuid4()),
            site_type=site_type,
            current_factor=current_factor,
            proposed_factor=proposed_factor,
            sample_count=len(records),
            based_on_record_ids=[r.id for r in records],
            status="proposed",
            created_at=datetime.now(UTC),
        )
        session.add(proposal)
        session.commit()

        return {
            "proposal_id": proposal.id,
            "site_type": site_type,
            "current_factor": current_factor,
            "proposed_factor": proposed_factor,
            "sample_count": len(records),
            "status": "proposed",
        }


def approve_utilisation_factor_proposal(proposal_id: str, approved_by: str) -> dict:
    """Admin approval step for CAL-03's proposal — mirrors
    repositories/ml_models.py::approve_version(). Does NOT write
    packages/config-packs/*.yaml directly; CAL-03 stays propose-only,
    approving here only flips the record's status for visibility/audit.
    Raises ValueError on an unknown id or a proposal that isn't
    currently "proposed" (can't re-approve/re-reject a decided one)."""
    with session_scope() as session:
        proposal = session.get(UtilisationFactorProposal, proposal_id)
        if proposal is None:
            raise ValueError(f"No utilisation_factor_proposals row for id={proposal_id}")
        if proposal.status != "proposed":
            raise ValueError(f"Proposal {proposal_id} is already {proposal.status}")

        proposal.status = "approved"
        proposal.reviewed_at = datetime.now(UTC)
        proposal.reviewed_by = approved_by
        session.commit()

        return {
            "proposal_id": proposal.id,
            "site_type": proposal.site_type,
            "status": proposal.status,
            "reviewed_by": proposal.reviewed_by,
        }


def reject_utilisation_factor_proposal(proposal_id: str, rejected_by: str) -> dict:
    """Counterpart to approve_utilisation_factor_proposal() above."""
    with session_scope() as session:
        proposal = session.get(UtilisationFactorProposal, proposal_id)
        if proposal is None:
            raise ValueError(f"No utilisation_factor_proposals row for id={proposal_id}")
        if proposal.status != "proposed":
            raise ValueError(f"Proposal {proposal_id} is already {proposal.status}")

        proposal.status = "rejected"
        proposal.reviewed_at = datetime.now(UTC)
        proposal.reviewed_by = rejected_by
        session.commit()

        return {
            "proposal_id": proposal.id,
            "site_type": proposal.site_type,
            "status": proposal.status,
            "reviewed_by": proposal.reviewed_by,
        }


def get_variance_distribution(
    site_type: str | None = None,
    region: str | None = None,
    geometry_source: str | None = None,
) -> dict:
    """CAL-04 (Should). Basic distribution stats over stored variance
    records, optionally filtered."""
    with session_scope() as session:
        stmt = select(CalibrationRecord).where(CalibrationRecord.variance_pct.is_not(None))
        if site_type is not None:
            stmt = stmt.where(CalibrationRecord.site_type == site_type)
        if region is not None:
            stmt = stmt.where(CalibrationRecord.region == region)
        if geometry_source is not None:
            stmt = stmt.where(CalibrationRecord.geometry_source == geometry_source)

        values = [r.variance_pct for r in session.scalars(stmt).all()]

    if not values:
        return {"count": 0, "mean": None, "median": None, "p10": None, "p90": None, "stdev": None}

    sorted_values = sorted(values)

    def _percentile(data: list[float], pct: float) -> float:
        if len(data) == 1:
            return data[0]
        index = pct * (len(data) - 1)
        lower, upper = int(index), min(int(index) + 1, len(data) - 1)
        fraction = index - lower
        return data[lower] + (data[upper] - data[lower]) * fraction

    return {
        "count": len(values),
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "p10": _percentile(sorted_values, 0.10),
        "p90": _percentile(sorted_values, 0.90),
        "stdev": statistics.pstdev(values) if len(values) > 1 else 0.0,
    }


def get_calibration_confidence_adjustment(site_type: str, geometry_source: str | None = None) -> float:
    """CAL-05 (FIT-04 half). Returns a 0..1 figure matching
    engine/fitness.py's params["calibration_state"] expectation — that
    function already treats None as neutral (0.5), so this function
    mirrors the same neutral default for the "no data yet" case rather
    than inventing a different scale."""
    with session_scope() as session:
        stmt = select(CalibrationRecord).where(
            CalibrationRecord.site_type == site_type,
            CalibrationRecord.variance_pct.is_not(None),
        )
        if geometry_source is not None:
            stmt = stmt.where(CalibrationRecord.geometry_source == geometry_source)
        values = [r.variance_pct for r in session.scalars(stmt).all()]

    if not values:
        return 0.5  # NO_DATA — neutral, not a penalty

    mean_abs_variance = statistics.mean(abs(v) for v in values)
    if mean_abs_variance > get_calibration_variance_threshold():
        return 0.2  # HIGH_VARIANCE
    return 0.9  # VALIDATED
