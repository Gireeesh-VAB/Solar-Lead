"""§9.1 Site Model — SITE-01, SITE-05 versioning. Person 1.

DB-backed: these run against the real Postgres+PostGIS service, because
the thing under test is largely the geography round-trip and the
append-only history, neither of which a mock would exercise.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from shapely.geometry import box as shapely_box
from shapely.geometry import mapping

from solarfit.domain.site import ShadingEstimate
from solarfit.engine.area import compute_usable_area_m2
from solarfit.repositories import sites as repo

LON, LAT = 78.4867, 17.3850  # Hyderabad


def _poly(dlon: float = 0.0, dlat: float = 0.0, size: float = 0.0005) -> dict:
    """A small lat/lng box — roughly 50 m on a side at this latitude."""
    return mapping(shapely_box(LON + dlon, LAT + dlat, LON + dlon + size, LAT + dlat + size))


def _multipoly(*polys: dict) -> dict:
    return {"type": "MultiPolygon", "coordinates": [p["coordinates"] for p in polys]}


def _create(session, **kwargs):
    defaults = {
        "site_type": "ROOFTOP_RESIDENTIAL",
        "name": "Test roof",
        "owner_org": "org-alpha",
        "jurisdiction": "IN-TG",
        "centroid": {"type": "Point", "coordinates": [LON, LAT]},
        "actor": "tester",
    }
    return repo.create(session, **{**defaults, **kwargs})


# --------------------------------------------------------------------- #
# SITE-01 — round-trip
# --------------------------------------------------------------------- #


def test_create_and_get_round_trips_geometry(db_session):
    site = _create(db_session, boundary=_poly(), geometry_source="manual_polygon")

    fetched = repo.get(db_session, site.id)
    assert fetched is not None
    assert fetched.site_type == "ROOFTOP_RESIDENTIAL"
    assert fetched.geometry_source == "manual_polygon"
    assert fetched.boundary is not None
    assert fetched.boundary["type"] == "Polygon"
    assert fetched.centroid["coordinates"] == pytest.approx([LON, LAT], abs=1e-9)


def test_get_returns_none_for_unknown_id(db_session):
    assert repo.get(db_session, "00000000-0000-0000-0000-000000000000") is None


def test_site_without_boundary_is_allowed(db_session):
    """A site exists before a geometry provider resolves anything for it."""
    site = _create(db_session)
    assert site.boundary is None
    assert repo.versions(db_session, site.id) == []


def test_shading_round_trips_as_the_frozen_contract(db_session):
    """SHADE-01 — stored as JSONB, read back as a ShadingEstimate."""
    site = _create(
        db_session,
        boundary=_poly(),
        shading=ShadingEstimate(
            sunshine_hours_per_year=1850.0, shading_score=0.82, source="solar_api"
        ),
    )
    fetched = repo.get(db_session, site.id)
    assert fetched.shading is not None
    assert fetched.shading.source == "solar_api"
    assert fetched.shading.shading_score == pytest.approx(0.82)


def test_shading_defaults_to_absent_for_non_solar_api_geometry(db_session):
    """SHADE-01 — MANUAL_POLYGON carries no shading data. Absent, never
    guessed; SHADE-04 reads that as INSUFFICIENT_DATA."""
    site = _create(db_session, boundary=_poly(), geometry_source="manual_polygon")
    assert repo.get(db_session, site.id).shading is None


def test_usn_round_trips_when_supplied_at_creation(db_session):
    """Regression: create() validated usn/usn_source only at the API
    boundary (SITE-02) and never actually persisted either — a
    validated USN was silently discarded on every write."""
    site = _create(db_session, usn="1234567890", usn_source="manual")
    assert site.usn is not None
    assert site.usn.usn == "1234567890"
    assert site.usn.usn_source == "manual"

    fetched = repo.get(db_session, site.id)
    assert fetched.usn.usn == "1234567890"
    assert fetched.usn.usn_source == "manual"


def test_usn_is_none_when_not_supplied(db_session):
    site = _create(db_session)
    assert site.usn is None


def test_update_usn_persists_onto_an_existing_site(db_session):
    site = _create(db_session)
    assert site.usn is None

    updated = repo.update_usn(db_session, site.id, usn="9876543210", usn_source="bill_ocr")
    assert updated.usn.usn == "9876543210"
    assert updated.usn.usn_source == "bill_ocr"

    fetched = repo.get(db_session, site.id)
    assert fetched.usn.usn == "9876543210"
    assert fetched.usn.usn_source == "bill_ocr"


def test_update_usn_unknown_site_raises(db_session):
    with pytest.raises(LookupError):
        repo.update_usn(
            db_session, "00000000-0000-0000-0000-000000000000", usn="123", usn_source="manual"
        )


# --------------------------------------------------------------------- #
# tenant scoping
# --------------------------------------------------------------------- #


def test_list_is_scoped_by_owner_org(db_session):
    # Unique orgs per run: the table is shared with whatever else has
    # been created against this database, so a test that assumes an empty
    # `sites` table is testing the fixture, not the scoping.
    alpha = f"org-alpha-{uuid4().hex[:8]}"
    beta = f"org-beta-{uuid4().hex[:8]}"

    _create(db_session, owner_org=alpha, name="Alpha roof")
    _create(db_session, owner_org=beta, name="Beta roof")

    assert [s.name for s in repo.list_sites(db_session, owner_org=alpha)] == ["Alpha roof"]
    assert [s.name for s in repo.list_sites(db_session, owner_org=beta)] == ["Beta roof"]


# --------------------------------------------------------------------- #
# SITE-05 — version, never overwrite
# --------------------------------------------------------------------- #


def test_initial_geometry_becomes_version_1(db_session):
    """History starts at the first geometry, not the first change — there
    is never a current boundary with no corresponding history row."""
    site = _create(db_session, boundary=_poly(), geometry_source="manual_polygon")

    history = repo.versions(db_session, site.id)
    assert len(history) == 1
    assert history[0].version_no == 1
    assert history[0].source == "manual_polygon"
    assert history[0].note == "initial geometry"


def test_boundary_change_appends_a_version_and_keeps_the_old_one(db_session):
    site = _create(db_session, boundary=_poly(), geometry_source="manual_polygon")
    original = repo.get(db_session, site.id).boundary

    repo.new_geometry_version(
        db_session, site.id, boundary=_poly(dlon=0.001), actor="admin-1", source="manual_edit"
    )

    history = repo.versions(db_session, site.id)
    assert [v.version_no for v in history] == [1, 2]
    assert [v.actor for v in history] == ["tester", "admin-1"]
    # SITE-05: the superseded geometry is still readable, not overwritten.
    assert repo._to_geojson(history[0].boundary) == original
    assert repo._to_geojson(history[1].boundary) != original


def test_version_carries_the_imagery_it_was_traced_from(db_session):
    """SITE-04: geometry_source, imagery_date, imagery_quality and
    geometry_confidence must all persist per version, not just on the
    current sites row — otherwise a site's history loses that context
    the moment a second version is written."""
    imagery_date = datetime(2026, 6, 1, tzinfo=UTC)
    site = _create(
        db_session,
        boundary=_poly(),
        geometry_source="solar_api",
        imagery_date=imagery_date,
        imagery_quality="HIGH",
        geometry_confidence=0.82,
    )
    v1 = repo.versions(db_session, site.id)[0]
    assert v1.geometry_source == "solar_api"
    assert v1.imagery_date == imagery_date
    assert v1.imagery_quality == "HIGH"
    assert v1.geometry_confidence == pytest.approx(0.82)

    # An exclusions-only change (OBS-04's own shape) doesn't re-trace the
    # boundary from new imagery — the prior version's imagery context
    # carries forward rather than going missing.
    repo.new_geometry_version(
        db_session,
        site.id,
        exclusions=_multipoly(_poly(dlon=0.0001, dlat=0.0001, size=0.0001)),
        actor="system:obstacle_detection",
        source="obstacle_detection",
    )
    v2 = repo.versions(db_session, site.id)[1]
    assert v2.imagery_date == imagery_date
    assert v2.imagery_quality == "HIGH"
    assert v2.geometry_confidence == pytest.approx(0.82)

    # An explicit override (a real re-trace) replaces it going forward.
    new_imagery_date = datetime(2026, 8, 1, tzinfo=UTC)
    repo.new_geometry_version(
        db_session,
        site.id,
        boundary=_poly(dlon=0.001),
        actor="admin-1",
        source="manual_edit",
        imagery_date=new_imagery_date,
        imagery_quality="BASE",
        geometry_confidence=0.5,
    )
    v3 = repo.versions(db_session, site.id)[2]
    assert v3.imagery_date == new_imagery_date
    assert v3.imagery_quality == "BASE"
    assert v3.geometry_confidence == pytest.approx(0.5)


def test_exclusions_only_change_keeps_the_boundary(db_session):
    """Person 3's OBS-04 changes exclusions, not the boundary. The Day-0
    stub signature could not express this — see the module docstring."""
    site = _create(db_session, boundary=_poly(), geometry_source="solar_api")
    boundary_before = repo.get(db_session, site.id).boundary

    updated = repo.new_geometry_version(
        db_session,
        site.id,
        exclusions=_multipoly(_poly(dlon=0.0001, dlat=0.0001, size=0.0001)),
        actor="obstacle-worker",
        source="obstacle_detection",
    )

    assert updated.boundary == boundary_before
    assert updated.exclusions is not None
    assert repo.versions(db_session, site.id)[-1].source == "obstacle_detection"


def test_applied_obstacle_ids_collects_across_every_version(db_session):
    """OBS-04 idempotency: engine/obstacles.py's apply_or_flag() reads
    this before unioning a new obstacle into exclusions, so it must see
    every id ever applied across this site's whole history, not just the
    latest version."""
    site = _create(db_session, boundary=_poly(), geometry_source="solar_api")
    assert repo.applied_obstacle_ids(db_session, site.id) == set()

    repo.new_geometry_version(
        db_session,
        site.id,
        exclusions=_multipoly(_poly(dlon=0.0001, dlat=0.0001, size=0.0001)),
        actor="system:obstacle_detection",
        source="obstacle_detection",
        applied_obstacle_ids=["obstacle-a"],
        applied_obstacle_polygons={"obstacle-a": _poly(dlon=0.0001, dlat=0.0001, size=0.0001)},
    )
    assert repo.applied_obstacle_ids(db_session, site.id) == {"obstacle-a"}

    repo.new_geometry_version(
        db_session,
        site.id,
        exclusions=_multipoly(
            _poly(dlon=0.0001, dlat=0.0001, size=0.0001), _poly(dlon=0.0002, dlat=0.0002, size=0.0001)
        ),
        actor="system:obstacle_detection",
        source="obstacle_detection",
        applied_obstacle_ids=["obstacle-b"],
        applied_obstacle_polygons={"obstacle-b": _poly(dlon=0.0002, dlat=0.0002, size=0.0001)},
    )
    assert repo.applied_obstacle_ids(db_session, site.id) == {"obstacle-a", "obstacle-b"}


def test_version_records_actor_and_timestamp(db_session):
    """SITE-05 requires both."""
    site = _create(db_session, boundary=_poly())
    repo.new_geometry_version(
        db_session, site.id, boundary=_poly(dlon=0.001), actor="admin-7", source="manual_edit"
    )
    latest = repo.versions(db_session, site.id)[-1]
    assert latest.actor == "admin-7"
    assert latest.created_at is not None


def test_version_with_no_change_is_rejected(db_session):
    site = _create(db_session, boundary=_poly())
    with pytest.raises(ValueError, match="requires a boundary or exclusions"):
        repo.new_geometry_version(db_session, site.id, actor="x", source="y")


def test_unknown_site_raises(db_session):
    with pytest.raises(LookupError):
        repo.new_geometry_version(
            db_session,
            "00000000-0000-0000-0000-000000000000",
            boundary=_poly(),
            actor="x",
            source="y",
        )


# --------------------------------------------------------------------- #
# OBS-06 — reversal writes forward, never deletes
# --------------------------------------------------------------------- #


def test_restore_writes_a_new_version_rather_than_deleting(db_session):
    """An admin rejecting an auto-applied obstacle must leave both the
    apply and the reversal visible in history."""
    site = _create(db_session, boundary=_poly(), geometry_source="solar_api")
    clean_area = compute_usable_area_m2(repo.get(db_session, site.id))

    # OBS-04: a high-confidence obstacle auto-applies.
    repo.new_geometry_version(
        db_session,
        site.id,
        exclusions=_multipoly(_poly(dlon=0.0001, dlat=0.0001, size=0.0002)),
        actor="obstacle-worker",
        source="obstacle_detection",
    )
    reduced_area = compute_usable_area_m2(repo.get(db_session, site.id))
    assert reduced_area < clean_area

    # OBS-06: the admin rejects it.
    repo.restore_version(db_session, site.id, 1, actor="admin-1", source="obstacle_rejected")

    history = repo.versions(db_session, site.id)
    assert [v.version_no for v in history] == [1, 2, 3]
    assert [v.source for v in history] == [
        "solar_api",
        "obstacle_detection",
        "obstacle_rejected",
    ]
    # Nothing deleted — version 2 still records that the obstacle applied.
    assert history[1].exclusions is not None
    # And usable area is back where it started.
    assert compute_usable_area_m2(repo.get(db_session, site.id)) == pytest.approx(clean_area)


def test_restore_of_unknown_version_raises(db_session):
    site = _create(db_session, boundary=_poly())
    with pytest.raises(LookupError, match="no version 99"):
        repo.restore_version(db_session, site.id, 99, actor="admin-1")


# --------------------------------------------------------------------- #
# the whole point: a stored site yields a usable area
# --------------------------------------------------------------------- #


def test_stored_site_produces_a_plausible_usable_area(db_session):
    """End-to-end for Day 1: geometry in, square metres out, through the
    real database and the real projection path."""
    site = _create(db_session, boundary=_poly(size=0.0005), geometry_source="manual_polygon")
    usable = compute_usable_area_m2(repo.get(db_session, site.id))

    # ~53 m x ~55 m at this latitude, x 0.70 utilisation, minus a 0.5 m
    # setback — a few thousand square metres, and definitely not a
    # fraction of a square degree.
    assert 1_000.0 < usable < 3_000.0
