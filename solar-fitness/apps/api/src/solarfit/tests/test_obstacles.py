"""§16 Testing — Day 3 implementation of §9.16 Obstacle Detection's
auto-apply/reversal half (OBS-04..06).

engine/obstacles.py's dependencies (repositories.sites,
engine.area.compute_usable_area_m2) are still NotImplementedError stubs
owned by Person 1/2 — mocked here via unittest.mock.patch on the
lazy-imported names, same discipline as test_analysis_cache.py's
GEO/weather/VIZ/ML mocks. validate_obstacle_polygon (OBS-03) is real
and exercised directly, not mocked, so these tests also prove the
threshold/validation split behaves correctly end to end.
"""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from solarfit.domain.assessment import Obstacle
from solarfit.domain.site import Site
from solarfit.engine.obstacles import apply_or_flag, reject_applied_obstacle
from solarfit.repositories.sites import SiteVersion

BOUNDARY = {
    "type": "Polygon",
    "coordinates": [[[78.4860, 17.3845], [78.4874, 17.3845], [78.4874, 17.3855], [78.4860, 17.3855], [78.4860, 17.3845]]],
}


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
        patch("solarfit.repositories.sites.new_boundary_version", return_value=site) as new_version,
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
    recompute.assert_called_once()
    force_refresh.assert_called_once()


def test_apply_or_flag_calls_force_refresh_on_successful_auto_apply():
    site = _site()  # centroid: [78.4867, 17.3850] -> lng, lat
    above = _obstacle_within_boundary(confidence=0.95)

    with (
        patch("solarfit.packs.config_pack.get_auto_apply_confidence_threshold", return_value=0.85),
        patch("solarfit.repositories.sites.new_boundary_version", return_value=site),
        patch("solarfit.engine.area.compute_usable_area_m2", return_value=42.0),
        patch("solarfit.repositories.analysis_cache.force_refresh") as force_refresh,
    ):
        apply_or_flag(site, [above])

    force_refresh.assert_called_once_with(17.3850, 78.4867)  # VIZ-04: invalidate any stale cache entry


def test_apply_or_flag_degrades_to_advisory_when_sites_repo_not_implemented():
    site = _site()
    above = _obstacle_within_boundary(confidence=0.95)

    with (
        patch("solarfit.packs.config_pack.get_auto_apply_confidence_threshold", return_value=0.85),
        patch("solarfit.repositories.sites.new_boundary_version", side_effect=NotImplementedError),
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
        patch("solarfit.repositories.sites.new_boundary_version", return_value=site),
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
        patch("solarfit.repositories.sites.new_boundary_version") as new_version,
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
        patch("solarfit.repositories.sites.new_boundary_version") as new_version,
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
        patch("solarfit.repositories.sites.new_boundary_version", return_value=site) as new_version,
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
    version = SiteVersion(
        id="v-1",
        site_id=site.id,
        boundary=BOUNDARY,
        exclusions=site.exclusions,
        source="obstacle_detection",
        applied_obstacle_ids=[obstacle.id],
        applied_obstacle_polygon=obstacle.bounding_polygon,
        actor="system:obstacle_detection",
        created_at=datetime.now(UTC),
    )
    updated_site = _site()

    with (
        patch("solarfit.repositories.sites.get", return_value=site),
        patch("solarfit.repositories.sites.find_version_applying_obstacle", return_value=version),
        patch("solarfit.repositories.sites.new_boundary_version", return_value=updated_site) as new_version,
        patch("solarfit.engine.area.compute_usable_area_m2", return_value=100.0) as recompute,
    ):
        result = reject_applied_obstacle(site.id, obstacle.id, actor="admin@example.com")

    assert result is updated_site
    _, kwargs = new_version.call_args
    assert kwargs["source"] == "obstacle_rejection"
    recompute.assert_called_once_with(updated_site)


def test_reject_applied_obstacle_unknown_obstacle_raises():
    site = _site()
    with (
        patch("solarfit.repositories.sites.get", return_value=site),
        patch("solarfit.repositories.sites.find_version_applying_obstacle", return_value=None),
        pytest.raises(ValueError),
    ):
        reject_applied_obstacle(site.id, "nonexistent-obstacle-id", actor="admin@example.com")


def test_reject_applied_obstacle_unknown_site_raises():
    with patch("solarfit.repositories.sites.get", return_value=None), pytest.raises(ValueError):
        reject_applied_obstacle("nonexistent-site-id", "obstacle-id", actor="admin@example.com")


def test_reject_applied_obstacle_raises_clear_error_when_sites_repo_not_implemented():
    with (
        patch("solarfit.repositories.sites.get", side_effect=NotImplementedError),
        pytest.raises(NotImplementedError, match="no safe advisory fallback"),
    ):
        reject_applied_obstacle("site-1", "obstacle-1", actor="admin@example.com")
