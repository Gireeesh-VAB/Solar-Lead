"""Tests for repositories/calibration.py — §9.9 Calibration (CAL-01..05),
tasks 8 and 9 of Person 4's list.

DB-touching tests run against an in-memory SQLite database (via the
sqlite_engine fixture) — calibration_records/utilisation_factor_proposals
have no PostGIS columns, so this is a faithful substitute and doesn't
depend on docker-compose being up. Person 1's sites.get() and Person 3's
analysis_cache.find_by_key() are always monkeypatched — both are still
stubs (NotImplementedError) in the real codebase.
"""

import pytest
from sqlalchemy.orm import sessionmaker

from solarfit.domain.assessment import AnalysisResult
from solarfit.repositories import calibration
from solarfit.repositories.calibration import CalibrationRecord, UtilisationFactorProposal


@pytest.fixture
def calibration_session_factory(sqlite_engine, monkeypatch):
    """Creates the calibration tables on the shared in-memory engine and
    points repositories.calibration.session_scope at it."""
    CalibrationRecord.metadata.create_all(
        sqlite_engine, tables=[CalibrationRecord.__table__, UtilisationFactorProposal.__table__]
    )
    session_local = sessionmaker(bind=sqlite_engine)
    monkeypatch.setattr(calibration, "session_scope", lambda: session_local())
    return session_local


@pytest.fixture
def mock_site_and_cache(monkeypatch, make_site):
    """Monkeypatches sites.get() and analysis_cache.find_by_key()/
    round_latlng() so record_field_survey() can run without either
    Person 1's or Person 3's real (still-stub) implementations. Returns
    a helper to set the "remote" usable area for the next lookup."""
    site = make_site(site_type="ROOFTOP_RESIDENTIAL", jurisdiction="AP", geometry_source="solar_api")
    monkeypatch.setattr(calibration.sites_repo, "get", lambda session, site_id: site)

    state = {"remote_area_m2": 100.0}

    def _fake_find_by_key(lat_rounded, lng_rounded):
        if state["remote_area_m2"] is None:
            return None
        return AnalysisResult(boundary={"type": "Polygon", "coordinates": []}, usable_area_m2=state["remote_area_m2"])

    monkeypatch.setattr(calibration.analysis_cache_repo, "find_by_key", _fake_find_by_key)
    monkeypatch.setattr(calibration.analysis_cache_repo, "round_latlng", lambda lat, lng: (lat, lng))

    def _set_remote_area(value: float | None) -> None:
        state["remote_area_m2"] = value

    return site, _set_remote_area


# ---------------------------------------------------------------------------
# Task 8 — CAL-01/02
# ---------------------------------------------------------------------------


def test_record_field_survey_computes_variance_and_stores(calibration_session_factory, mock_site_and_cache):
    site, set_remote_area = mock_site_and_cache
    set_remote_area(100.0)

    result = calibration.record_field_survey(site.id, measured_area_m2=110.0)

    assert result["remote_area_m2"] == 100.0
    assert result["measured_area_m2"] == 110.0
    assert result["variance_pct"] == pytest.approx(0.10)
    assert result["flagged_superseded"] is False  # under the 0.15 placeholder threshold

    with calibration_session_factory() as session:
        row = session.get(CalibrationRecord, result["record_id"])
        assert row is not None
        assert row.site_type == "ROOFTOP_RESIDENTIAL"
        assert row.region == "AP"
        assert row.geometry_source == "solar_api"


def test_record_field_survey_flags_when_variance_exceeds_threshold(
    calibration_session_factory, mock_site_and_cache
):
    site, set_remote_area = mock_site_and_cache
    set_remote_area(100.0)

    result = calibration.record_field_survey(site.id, measured_area_m2=140.0)  # 40% variance

    assert result["variance_pct"] == pytest.approx(0.40)
    assert result["flagged_superseded"] is True


def test_record_field_survey_does_not_flag_within_threshold(calibration_session_factory, mock_site_and_cache):
    site, set_remote_area = mock_site_and_cache
    set_remote_area(100.0)

    result = calibration.record_field_survey(site.id, measured_area_m2=105.0)  # 5% variance

    assert result["flagged_superseded"] is False


def test_record_field_survey_handles_missing_remote_area_gracefully(
    calibration_session_factory, mock_site_and_cache
):
    site, set_remote_area = mock_site_and_cache
    set_remote_area(None)  # nothing cached yet for this location

    result = calibration.record_field_survey(site.id, measured_area_m2=110.0)

    assert result["remote_area_m2"] is None
    assert result["variance_pct"] is None
    assert result["flagged_superseded"] is False


def test_record_field_survey_handles_zero_remote_area_gracefully(
    calibration_session_factory, mock_site_and_cache
):
    site, set_remote_area = mock_site_and_cache
    set_remote_area(0.0)

    result = calibration.record_field_survey(site.id, measured_area_m2=50.0)

    assert result["variance_pct"] is None  # no divide-by-zero
    assert result["flagged_superseded"] is False


def test_record_field_survey_unknown_site_still_records(calibration_session_factory, monkeypatch):
    """A site.get() that returns None (site not found) shouldn't crash —
    it should still store a record, just without site-derived fields."""
    monkeypatch.setattr(calibration.sites_repo, "get", lambda session, site_id: None)

    result = calibration.record_field_survey("does-not-exist", measured_area_m2=50.0)

    assert result["remote_area_m2"] is None
    with calibration_session_factory() as session:
        row = session.get(CalibrationRecord, result["record_id"])
        assert row.site_type == "UNKNOWN"


# ---------------------------------------------------------------------------
# Task 9 — CAL-03
# ---------------------------------------------------------------------------


def _seed_records(session_factory, site_type, ratios):
    """Directly inserts CalibrationRecord rows with the given
    measured/remote ratios, bypassing record_field_survey() for
    test-setup speed."""
    from datetime import UTC, datetime
    from uuid import uuid4

    with session_factory() as session:
        for ratio in ratios:
            remote = 100.0
            session.add(
                CalibrationRecord(
                    id=str(uuid4()),
                    site_id="site-x",
                    site_type=site_type,
                    region="AP",
                    geometry_source="solar_api",
                    remote_area_m2=remote,
                    measured_area_m2=remote * ratio,
                    variance_pct=ratio - 1,
                    flagged_superseded=False,
                    created_at=datetime.now(UTC),
                )
            )
        session.commit()


def test_propose_utilisation_factor_update_returns_none_below_sample_threshold(
    calibration_session_factory,
):
    _seed_records(calibration_session_factory, "ROOFTOP_RESIDENTIAL", [1.05] * 5)  # threshold is 20

    result = calibration.propose_utilisation_factor_update("ROOFTOP_RESIDENTIAL")

    assert result is None


def test_propose_utilisation_factor_update_returns_proposal_above_threshold(calibration_session_factory):
    _seed_records(calibration_session_factory, "ROOFTOP_RESIDENTIAL", [1.10] * 25)

    result = calibration.propose_utilisation_factor_update("ROOFTOP_RESIDENTIAL")

    assert result is not None
    assert result["sample_count"] == 25
    assert result["status"] == "proposed"
    # current_factor (0.70 placeholder) * median ratio (1.10), clamped
    assert result["proposed_factor"] == pytest.approx(0.70 * 1.10, rel=1e-6)

    with calibration_session_factory() as session:
        row = session.get(UtilisationFactorProposal, result["proposal_id"])
        assert row is not None
        assert row.status == "proposed"
        assert len(row.based_on_record_ids) == 25


def test_propose_utilisation_factor_update_uses_median_robust_to_outlier(calibration_session_factory):
    ratios = [1.00] * 24 + [5.00]  # one wild outlier among 25 samples
    _seed_records(calibration_session_factory, "ROOFTOP_RESIDENTIAL", ratios)

    result = calibration.propose_utilisation_factor_update("ROOFTOP_RESIDENTIAL")

    mean_based = 0.70 * (sum(ratios) / len(ratios))
    median_based = 0.70 * 1.00

    assert result["proposed_factor"] == pytest.approx(median_based, rel=1e-6)
    assert result["proposed_factor"] != pytest.approx(mean_based, rel=1e-2)


def test_propose_never_writes_yaml(calibration_session_factory):
    from solarfit.packs.config_pack import get_utilisation_factor

    before = get_utilisation_factor("ROOFTOP_RESIDENTIAL")
    _seed_records(calibration_session_factory, "ROOFTOP_RESIDENTIAL", [1.20] * 25)

    calibration.propose_utilisation_factor_update("ROOFTOP_RESIDENTIAL")

    after = get_utilisation_factor("ROOFTOP_RESIDENTIAL")
    assert before == after


def test_propose_utilisation_factor_update_ignores_zero_remote_area_rows(calibration_session_factory):
    from datetime import UTC, datetime
    from uuid import uuid4

    with calibration_session_factory() as session:
        for _ in range(25):
            session.add(
                CalibrationRecord(
                    id=str(uuid4()),
                    site_id="site-x",
                    site_type="ROOFTOP_CI",
                    region="AP",
                    geometry_source=None,
                    remote_area_m2=0.0,
                    measured_area_m2=10.0,
                    variance_pct=None,  # record_field_survey wouldn't set variance for these either
                    flagged_superseded=False,
                    created_at=datetime.now(UTC),
                )
            )
        session.commit()

    result = calibration.propose_utilisation_factor_update("ROOFTOP_CI")

    assert result is None  # no rows have a non-null variance_pct at all


# ---------------------------------------------------------------------------
# Task 9 — CAL-04
# ---------------------------------------------------------------------------


def test_variance_distribution_matches_hand_computed_stats(calibration_session_factory):
    _seed_records(calibration_session_factory, "ROOFTOP_RESIDENTIAL", [1.00, 1.10, 1.20, 0.90, 1.05])

    stats = calibration.get_variance_distribution(site_type="ROOFTOP_RESIDENTIAL")

    assert stats["count"] == 5
    variances = [1.00 - 1, 1.10 - 1, 1.20 - 1, 0.90 - 1, 1.05 - 1]
    assert stats["mean"] == pytest.approx(sum(variances) / 5)
    assert stats["median"] == pytest.approx(sorted(variances)[2])


def test_variance_distribution_empty_when_no_matching_records(calibration_session_factory):
    stats = calibration.get_variance_distribution(site_type="ROOFTOP_GOVT")

    assert stats["count"] == 0
    assert stats["mean"] is None


def test_variance_distribution_respects_filters(calibration_session_factory):
    _seed_records(calibration_session_factory, "ROOFTOP_RESIDENTIAL", [1.10] * 3)
    _seed_records(calibration_session_factory, "ROOFTOP_CI", [1.50] * 3)

    residential_stats = calibration.get_variance_distribution(site_type="ROOFTOP_RESIDENTIAL")
    ci_stats = calibration.get_variance_distribution(site_type="ROOFTOP_CI")

    assert residential_stats["count"] == 3
    assert ci_stats["count"] == 3
    assert residential_stats["mean"] != ci_stats["mean"]


# ---------------------------------------------------------------------------
# Task 9 — CAL-05
# ---------------------------------------------------------------------------


def test_calibration_confidence_no_data_is_neutral(calibration_session_factory):
    adjustment = calibration.get_calibration_confidence_adjustment("ROOFTOP_RESIDENTIAL")
    assert adjustment == 0.5


def test_calibration_confidence_high_variance_is_low(calibration_session_factory):
    _seed_records(calibration_session_factory, "ROOFTOP_RESIDENTIAL", [1.50, 1.60, 0.40])  # big spread

    adjustment = calibration.get_calibration_confidence_adjustment("ROOFTOP_RESIDENTIAL")

    assert adjustment == 0.2


def test_calibration_confidence_validated_is_high(calibration_session_factory):
    _seed_records(calibration_session_factory, "ROOFTOP_RESIDENTIAL", [1.02, 0.98, 1.01])  # tight spread

    adjustment = calibration.get_calibration_confidence_adjustment("ROOFTOP_RESIDENTIAL")

    assert adjustment == 0.9
