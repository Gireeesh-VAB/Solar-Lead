"""§16 Testing — §9.16 Obstacle Detection's auto-apply/reversal half
(OBS-04..06), against Person 1's real repositories/sites.py (merged
Day 8). session_scope() is faked with a plain in-memory context manager
(these are unit tests of the orchestration logic, not integration tests
of sites.py itself — that's test_sites_repository.py's job) so no live
DB round trip is needed here; sites_repo.{get,new_geometry_version,
versions} are mocked the same way GEO/weather/VIZ/ML are mocked in
test_analysis_cache.py. validate_obstacle_polygon (OBS-03) is real and
exercised directly, not mocked, so these tests also prove the
threshold/validation split behaves correctly end to end.
"""

from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from solarfit.domain.assessment import Obstacle
from solarfit.domain.site import Site
from solarfit.engine.obstacles import apply_or_flag, reject_applied_obstacle

BOUNDARY = {
    "type": "Polygon",
    "coordinates": [[[78.4860, 17.3845], [78.4874, 17.3845], [78.4874, 17.3855], [78.4860, 17.3855], [78.4860, 17.3845]]],
}


@contextmanager
def _fake_session_scope():
    yield MagicMock(name="fake-session")


def _site(**overrides) -> Site:
    defaults = {
        "id": "site-1",
        "site_type": "ROOFTOP_RESIDENTIAL",
        "name": "Test Site",
        "owner_org": "Test Org",
        "jurisdiction": "TS",
        "centroid": {"type": "Point", "coordinates": [78.4867, 17.3850]},
        "boundary": BOUNDARY,
        "exclusions": None,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return Site(**defaults)


def _obstacle_within_boundary(confidence: float, obstacle_type: str = "water_tank") -> Obstacle:
    return Obstacle(
        type=obstacle_type,
        confidence=confidence,
        bounding_polygon={
            "type": "Polygon",
            "coordinates": [
                [[78.4862, 17.3847], [78.4864, 17.3847], [78.4864, 17.3849], [78.4862, 17.3849], [78.4862, 17.3847]]
            ],
        },
    )


def _obstacle_outside_boundary(confidence: float = 0.9) -> Obstacle:
    return Obstacle(
        type="hvac_unit",
        confidence=confidence,
        bounding_polygon={
            "type": "Polygon",
            "coordinates": [
                [[78.5000, 17.4000], [78.5002, 17.4000], [78.5002, 17.4002], [78.5000, 17.4002], [78.5000, 17.4000]]
            ],
        },
    )


def test_apply_or_flag_splits_by_confidence_threshold():
    site = _site()
    above = _obstacle_within_boundary(confidence=0.95)
    below = _obstacle_within_boundary(confidence=0.10, obstacle_type="vent")

    with (
        patch("solarfit.packs.config_pack.get_auto_apply_confidence_threshold", return_value=0.85),
        patch("solarfit.engine.obstacles.session_scope", _fake_session_scope),
        patch("solarfit.repositories.sites.new_geometry_version") as new_version,
        patch("solarfit.repositories.sites.get", return_value=site),
        patch("solarfit.engine.area.compute_usable_area_m2", return_value=42.0) as recompute,
        patch("solarfit.repositories.analysis_cache.force_refresh") as force_refresh,
    ):
        result = apply_or_flag(site, [above, below])

    assert {o.id for o in result} == {above.id, below.id}
    applied = {o.id: o.applied for o in result}
    assert applied[above.id] is True
    assert applied[below.id] is False
    new_version.assert_called_once()
    _, kwargs = new_version.call_args
    assert kwargs["source"] == "obstacle_detection"
    assert kwargs["applied_obstacle_ids"] == [above.id]
    assert kwargs["applied_obstacle_polygons"] == {above.id: above.bounding_polygon}
    recompute.assert_called_once()
    force_refresh.assert_called_once()


def test_apply_or_flag_calls_force_refresh_on_successful_auto_apply():
    site = _site()  # centroid: [78.4867, 17.3850] -> lng, lat
    above = _obstacle_within_boundary(confidence=0.95)

    with (
        patch("solarfit.packs.config_pack.get_auto_apply_confidence_threshold", return_value=0.85),
        patch("solarfit.engine.obstacles.session_scope", _fake_session_scope),
        patch("solarfit.repositories.sites.new_geometry_version"),
        patch("solarfit.repositories.sites.get", return_value=site),
        patch("solarfit.engine.area.compute_usable_area_m2", return_value=42.0),
        patch("solarfit.repositories.analysis_cache.force_refresh") as force_refresh,
    ):
        apply_or_flag(site, [above])

    force_refresh.assert_called_once_with(17.3850, 78.4867)  # VIZ-04: invalidate any stale cache entry


def test_apply_or_flag_degrades_to_advisory_on_db_failure():
    site = _site()
    above = _obstacle_within_boundary(confidence=0.95)

    with (
        patch("solarfit.packs.config_pack.get_auto_apply_confidence_threshold", return_value=0.85),
        patch("solarfit.engine.obstacles.session_scope", _fake_session_scope),
        patch("solarfit.repositories.sites.new_geometry_version", side_effect=RuntimeError("db down")),
        patch("solarfit.engine.area.compute_usable_area_m2") as recompute,
    ):
        result = apply_or_flag(site, [above])  # must not raise

    assert result[0].id == above.id
    assert result[0].applied is False  # fell back to advisory, not auto-applied
    recompute.assert_not_called()


def test_apply_or_flag_drops_invalid_obstacles():
    site = _site()
    valid = _obstacle_within_boundary(confidence=0.95)
    invalid = _obstacle_outside_boundary(confidence=0.95)

    with (
        patch("solarfit.packs.config_pack.get_auto_apply_confidence_threshold", return_value=0.85),
        patch("solarfit.engine.obstacles.session_scope", _fake_session_scope),
        patch("solarfit.repositories.sites.new_geometry_version"),
        patch("solarfit.repositories.sites.get", return_value=site),
        patch("solarfit.engine.area.compute_usable_area_m2", return_value=42.0),
        patch("solarfit.repositories.analysis_cache.force_refresh"),
    ):
        result = apply_or_flag(site, [valid, invalid])

    assert [o.id for o in result] == [valid.id]


def test_apply_or_flag_never_versions_when_nothing_meets_threshold():
    site = _site()
    below = _obstacle_within_boundary(confidence=0.10)

    with (
        patch("solarfit.packs.config_pack.get_auto_apply_confidence_threshold", return_value=0.85),
        patch("solarfit.repositories.sites.new_geometry_version") as new_version,
        patch("solarfit.engine.area.compute_usable_area_m2") as recompute,
    ):
        result = apply_or_flag(site, [below])

    assert result[0].applied is False
    new_version.assert_not_called()
    recompute.assert_not_called()


def test_apply_or_flag_site_without_boundary_is_all_advisory():
    site = _site(boundary=None)
    obstacle = _obstacle_within_boundary(confidence=0.95)

    with (
        patch("solarfit.repositories.sites.new_geometry_version") as new_version,
        patch("solarfit.engine.area.compute_usable_area_m2") as recompute,
    ):
        result = apply_or_flag(site, [obstacle])

    assert result == [obstacle]
    assert result[0].applied is False
    new_version.assert_not_called()
    recompute.assert_not_called()


def test_apply_or_flag_unions_with_existing_exclusions():
    existing_exclusions = {
        "type": "MultiPolygon",
        "coordinates": [
            [[[78.4870, 17.3851], [78.4872, 17.3851], [78.4872, 17.3853], [78.4870, 17.3853], [78.4870, 17.3851]]]
        ],
    }
    site = _site(exclusions=existing_exclusions)
    above = _obstacle_within_boundary(confidence=0.95)

    with (
        patch("solarfit.packs.config_pack.get_auto_apply_confidence_threshold", return_value=0.85),
        patch("solarfit.engine.obstacles.session_scope", _fake_session_scope),
        patch("solarfit.repositories.sites.new_geometry_version") as new_version,
        patch("solarfit.repositories.sites.get", return_value=site),
        patch("solarfit.engine.area.compute_usable_area_m2", return_value=42.0),
        patch("solarfit.repositories.analysis_cache.force_refresh"),
    ):
        apply_or_flag(site, [above])

    _, kwargs = new_version.call_args
    new_exclusions = kwargs["exclusions"]
    assert new_exclusions["type"] == "MultiPolygon"
    # Union must cover both the pre-existing exclusion and the new obstacle —
    # at least 2 polygon parts, since they don't overlap.
    assert len(new_exclusions["coordinates"]) >= 2


def test_reject_applied_obstacle_supersedes_and_recomputes():
    obstacle = _obstacle_within_boundary(confidence=0.95)
    site = _site(exclusions={"type": "MultiPolygon", "coordinates": [obstacle.bounding_polygon["coordinates"]]})
    version = SimpleNamespace(
        applied_obstacle_ids=[obstacle.id],
        applied_obstacle_polygons={obstacle.id: obstacle.bounding_polygon},
    )
    updated_site = _site()

    with (
        patch("solarfit.engine.obstacles.session_scope", _fake_session_scope),
        patch("solarfit.repositories.sites.get", side_effect=[site, updated_site]),
        patch("solarfit.repositories.sites.versions", return_value=[version]),
        patch("solarfit.repositories.sites.new_geometry_version") as new_version,
        patch("solarfit.engine.area.compute_usable_area_m2", return_value=100.0) as recompute,
    ):
        result = reject_applied_obstacle(site.id, obstacle.id, actor="admin@example.com")

    assert result is updated_site
    _, kwargs = new_version.call_args
    assert kwargs["source"] == "obstacle_rejected"
    recompute.assert_called_once_with(updated_site)


def test_reject_applied_obstacle_unknown_obstacle_raises():
    site = _site()
    with (
        patch("solarfit.engine.obstacles.session_scope", _fake_session_scope),
        patch("solarfit.repositories.sites.get", return_value=site),
        patch("solarfit.repositories.sites.versions", return_value=[]),
        pytest.raises(ValueError),
    ):
        reject_applied_obstacle(site.id, "nonexistent-obstacle-id", actor="admin@example.com")


def test_reject_applied_obstacle_unknown_site_raises():
    with (
        patch("solarfit.engine.obstacles.session_scope", _fake_session_scope),
        patch("solarfit.repositories.sites.get", return_value=None),
        pytest.raises(ValueError),
    ):
        reject_applied_obstacle("nonexistent-site-id", "obstacle-id", actor="admin@example.com")
