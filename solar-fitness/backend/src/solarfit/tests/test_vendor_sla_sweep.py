"""Owner: keerthana (Vendor domain, customer-account admin, jurisdictions).

The time-bound lead engine — repositories/vendors.py::sweep_vendor_job_sla().
Before this, "sla_at_risk"/"overdue" existed only as status literals
nothing ever set (confirmed by a full-codebase grep before writing this
feature) — these tests lock in the real behavior that now backs them,
plus the actual "lead passing" reassignment step.

sweep_vendor_job_sla() deliberately scans the WHOLE vendor_jobs table
(it's a global sweep, not scoped to one vendor/site) — this dev database
carries real seed data (26 pre-existing vendor_jobs rows, confirmed via
`SELECT status, count(*) FROM vendor_jobs GROUP BY status`), so these
tests assert on the SPECIFIC row(s) each test creates, never on the
sweep's aggregate counts (those reflect the whole table, not just this
test's fixtures).
"""

from datetime import UTC, datetime, timedelta

import pytest

from solarfit.repositories import sites as sites_repo
from solarfit.repositories.vendors import (
    VendorJobRow,
    VendorRow,
    get_latest_job_for_site,
    sweep_vendor_job_sla,
)

LON, LAT = 78.4867, 17.3850

AT_RISK_WINDOW = timedelta(hours=24)
REASSIGN_EXTENSION = timedelta(days=2)


@pytest.fixture
def site(db_session):
    return sites_repo.create(
        db_session,
        site_type="ROOFTOP_RESIDENTIAL",
        name="Test Rooftop",
        owner_org="Test Org",
        jurisdiction="IN-TG",
        centroid={"type": "Point", "coordinates": [LON, LAT]},
    )


def _vendor(db_session, **overrides) -> VendorRow:
    defaults = {
        "name": "Vendor",
        "verification_status": "verified",
        "availability": True,
        "accuracy_score": 0.5,
        "service_area": {"region": "Telangana", "districts": ["Hyderabad"]},
        "payout_method_type": "UPI",
        "payout_masked_account": "vendor@upi",
    }
    defaults.update(overrides)
    row = VendorRow(**defaults)
    db_session.add(row)
    db_session.flush()
    return row


def _job(db_session, site, vendor, **overrides) -> VendorJobRow:
    defaults = {
        "site_id": site.id,
        "vendor_id": vendor.id if vendor else None,
        "status": "queued",
        "district": "Hyderabad",
        "state": "Telangana",
        "deadline": datetime.now(UTC) + timedelta(days=3),
        "payout_inr": 1500,
        "requirements": [],
    }
    defaults.update(overrides)
    row = VendorJobRow(**defaults)
    db_session.add(row)
    db_session.flush()
    return row


def test_a_job_well_within_deadline_is_untouched(db_session, site):
    vendor = _vendor(db_session)
    job = _job(db_session, site, vendor, status="queued", deadline=datetime.now(UTC) + timedelta(days=3))

    sweep_vendor_job_sla(db_session, at_risk_window=AT_RISK_WINDOW, reassignment_extension=REASSIGN_EXTENSION)

    assert job.status == "queued"
    assert job.vendor_id == vendor.id


def test_a_job_inside_the_at_risk_window_is_flagged_not_reassigned(db_session, site):
    vendor = _vendor(db_session)
    job = _job(db_session, site, vendor, status="accepted", deadline=datetime.now(UTC) + timedelta(hours=2))

    result = sweep_vendor_job_sla(
        db_session, at_risk_window=AT_RISK_WINDOW, reassignment_extension=REASSIGN_EXTENSION
    )

    assert result["marked_at_risk"] >= 1
    assert job.status == "sla_at_risk"
    assert job.vendor_id == vendor.id  # still owned by the same vendor — just a warning


def test_an_overdue_accepted_job_is_marked_overdue_never_reassigned(db_session, site):
    """Committed work (accepted/in_progress) is never yanked away mid-
    survey — only a never-accepted "queued" job can pass to someone else."""
    vendor = _vendor(db_session)
    job = _job(db_session, site, vendor, status="accepted", deadline=datetime.now(UTC) - timedelta(hours=1))
    _vendor(db_session, name="Other", service_area={"districts": ["Hyderabad"]})  # a real candidate exists

    sweep_vendor_job_sla(db_session, at_risk_window=AT_RISK_WINDOW, reassignment_extension=REASSIGN_EXTENSION)

    assert job.status == "overdue"
    assert job.vendor_id == vendor.id


def test_an_overdue_queued_job_passes_to_the_next_eligible_vendor(db_session, site):
    original = _vendor(db_session, name="Original", accuracy_score=0.5)
    better = _vendor(
        db_session, name="Better", accuracy_score=0.9, service_area={"districts": ["Hyderabad"]}
    )
    job = _job(db_session, site, original, status="queued", deadline=datetime.now(UTC) - timedelta(hours=1))

    result = sweep_vendor_job_sla(
        db_session, at_risk_window=AT_RISK_WINDOW, reassignment_extension=REASSIGN_EXTENSION
    )

    assert result["reassigned"] >= 1
    assert job.status == "queued"  # a fresh, live lead for the new vendor — not damaged goods
    assert job.vendor_id == better.id
    assert str(original.id) in job.previous_vendor_ids
    now = datetime.now(UTC)
    assert now + timedelta(days=1, hours=23) < job.deadline < now + timedelta(days=2, hours=1)


def test_reassignment_picks_the_highest_accuracy_eligible_vendor(db_session, site):
    original = _vendor(db_session, name="Original")
    _low = _vendor(db_session, name="Low", accuracy_score=0.3, service_area={"districts": ["Hyderabad"]})
    high = _vendor(db_session, name="High", accuracy_score=0.95, service_area={"districts": ["Hyderabad"]})
    job = _job(db_session, site, original, status="queued", deadline=datetime.now(UTC) - timedelta(hours=1))

    sweep_vendor_job_sla(db_session, at_risk_window=AT_RISK_WINDOW, reassignment_extension=REASSIGN_EXTENSION)

    assert job.vendor_id == high.id


def test_reassignment_never_offers_to_an_unverified_or_unavailable_vendor(db_session, site):
    original = _vendor(db_session, name="Original")
    _vendor(
        db_session,
        name="Unverified",
        verification_status="pending",
        service_area={"districts": ["Hyderabad"]},
    )
    _vendor(db_session, name="Unavailable", availability=False, service_area={"districts": ["Hyderabad"]})
    job = _job(db_session, site, original, status="queued", deadline=datetime.now(UTC) - timedelta(hours=1))

    sweep_vendor_job_sla(db_session, at_risk_window=AT_RISK_WINDOW, reassignment_extension=REASSIGN_EXTENSION)

    # No eligible candidate — stays with the original vendor, marked overdue.
    assert job.status == "overdue"
    assert job.vendor_id == original.id


def test_reassignment_never_offers_to_the_current_vendor(db_session, site):
    original = _vendor(db_session, name="Original", service_area={"districts": ["Hyderabad"]})
    job = _job(
        db_session,
        site,
        original,
        status="queued",
        deadline=datetime.now(UTC) - timedelta(hours=1),
        previous_vendor_ids=[],
    )

    # Only the current vendor itself is "eligible" by district — must not
    # be offered the job it already has.
    sweep_vendor_job_sla(db_session, at_risk_window=AT_RISK_WINDOW, reassignment_extension=REASSIGN_EXTENSION)
    assert job.status == "overdue"
    assert job.vendor_id == original.id


def test_reassignment_never_offers_to_a_previously_tried_vendor(db_session, site):
    original = _vendor(db_session, name="Original")
    tried_before = _vendor(
        db_session, name="TriedBefore", service_area={"districts": ["Hyderabad"]}
    )
    job = _job(
        db_session,
        site,
        original,
        status="queued",
        deadline=datetime.now(UTC) - timedelta(hours=1),
        previous_vendor_ids=[str(tried_before.id)],
    )

    sweep_vendor_job_sla(db_session, at_risk_window=AT_RISK_WINDOW, reassignment_extension=REASSIGN_EXTENSION)

    assert job.status == "overdue"
    assert job.vendor_id == original.id


def test_a_job_with_no_district_match_is_never_reassigned(db_session, site):
    original = _vendor(db_session, name="Original")
    _vendor(db_session, name="WrongArea", service_area={"districts": ["Vizag"]})
    job = _job(db_session, site, original, status="queued", deadline=datetime.now(UTC) - timedelta(hours=1))

    sweep_vendor_job_sla(db_session, at_risk_window=AT_RISK_WINDOW, reassignment_extension=REASSIGN_EXTENSION)

    assert job.status == "overdue"
    assert job.vendor_id == original.id


def test_submitted_jobs_are_never_touched_by_the_sweep(db_session, site):
    vendor = _vendor(db_session)
    job = _job(
        db_session,
        site,
        vendor,
        status="submitted",
        deadline=datetime.now(UTC) - timedelta(days=10),
        submitted_at=datetime.now(UTC),
    )

    sweep_vendor_job_sla(db_session, at_risk_window=AT_RISK_WINDOW, reassignment_extension=REASSIGN_EXTENSION)

    assert job.status == "submitted"


# ---------------------------------------------------------------------------
# get_latest_job_for_site — the customer-facing "vendor display" lookup.
# ---------------------------------------------------------------------------


def test_get_latest_job_for_site_returns_none_when_nothing_queued(db_session, site):
    assert get_latest_job_for_site(db_session, site.id) is None


def test_get_latest_job_for_site_returns_the_most_recent_job(db_session, site):
    vendor = _vendor(db_session)
    older = _job(db_session, site, vendor, status="overdue")
    older.created_at = datetime.now(UTC) - timedelta(days=5)
    db_session.flush()
    newer = _job(db_session, site, vendor, status="accepted")

    result = get_latest_job_for_site(db_session, site.id)

    assert result is not None
    assert result.id == newer.id
    assert result.id != older.id
