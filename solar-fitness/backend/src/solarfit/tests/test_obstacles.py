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
        patch("solarfit.repositories.sites.applied_obstacle_ids", return_value=set()),
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
    assert kwargs["applied_obstacle_polygons"] == {
        above.id: {
            "polygon": above.bounding_polygon,
            "type": above.type,
            "confidence": above.confidence,
            "source": above.source,
        }
    }
    recompute.assert_called_once()
    force_refresh.assert_called_once()


def test_apply_or_flag_calls_force_refresh_on_successful_auto_apply():
    site = _site()  # centroid: [78.4867, 17.3850] -> lng, lat
    above = _obstacle_within_boundary(confidence=0.95)

    with (
        patch("solarfit.packs.config_pack.get_auto_apply_confidence_threshold", return_value=0.85),
        patch("solarfit.engine.obstacles.session_scope", _fake_session_scope),
        patch("solarfit.repositories.sites.applied_obstacle_ids", return_value=set()),
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
        patch("solarfit.repositories.sites.applied_obstacle_ids", return_value=set()),
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
        patch("solarfit.repositories.sites.applied_obstacle_ids", return_value=set()),
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


def test_apply_or_flag_skips_an_already_applied_obstacle():
    """OBS-04 idempotency: the same detection can be replayed for this
    site (repeat assessment call, or a different site reusing the same
    cached location) — an obstacle this site's own history already shows
    as applied must not be unioned into exclusions a second time, but
    still reports .applied = True in the result."""
    site = _site()
    above = _obstacle_within_boundary(confidence=0.95)

    with (
        patch("solarfit.packs.config_pack.get_auto_apply_confidence_threshold", return_value=0.85),
        patch("solarfit.engine.obstacles.session_scope", _fake_session_scope),
        patch("solarfit.repositories.sites.applied_obstacle_ids", return_value={above.id}),
        patch("solarfit.repositories.sites.new_geometry_version") as new_version,
        patch("solarfit.engine.area.compute_usable_area_m2") as recompute,
        patch("solarfit.repositories.analysis_cache.force_refresh") as force_refresh,
    ):
        result = apply_or_flag(site, [above])

    assert result[0].applied is True
    new_version.assert_not_called()  # nothing new to persist
    recompute.assert_not_called()
    force_refresh.assert_not_called()


def test_apply_or_flag_applies_only_the_new_obstacle_alongside_an_already_applied_one():
    site = _site()
    already = _obstacle_within_boundary(confidence=0.95, obstacle_type="chimney")
    new_one = _obstacle_within_boundary(confidence=0.95, obstacle_type="water_tank")

    with (
        patch("solarfit.packs.config_pack.get_auto_apply_confidence_threshold", return_value=0.85),
        patch("solarfit.engine.obstacles.session_scope", _fake_session_scope),
        patch("solarfit.repositories.sites.applied_obstacle_ids", return_value={already.id}),
        patch("solarfit.repositories.sites.new_geometry_version") as new_version,
        patch("solarfit.repositories.sites.get", return_value=site),
        patch("solarfit.engine.area.compute_usable_area_m2", return_value=42.0),
        patch("solarfit.repositories.analysis_cache.force_refresh"),
    ):
        result = apply_or_flag(site, [already, new_one])

    applied = {o.id: o.applied for o in result}
    assert applied[already.id] is True
    assert applied[new_one.id] is True
    _, kwargs = new_version.call_args
    assert kwargs["applied_obstacle_ids"] == [new_one.id]  # only the new one persisted


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
        patch("solarfit.repositories.sites.applied_obstacle_ids", return_value=set()),
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


def _obstacle_straddling_boundary_edge(source: str) -> Obstacle:
    """Half inside the site's roof, half past its east edge (lng 78.4874)."""
    return Obstacle(
        type="other",
        confidence=0.5,
        source=source,
        bounding_polygon={
            "type": "Polygon",
            "coordinates": [
                [[78.4872, 17.3847], [78.4876, 17.3847], [78.4876, 17.3849], [78.4872, 17.3849], [78.4872, 17.3847]]
            ],
        },
    )


def _run_apply_or_flag(site, obstacles, known=()):
    with (
        patch("solarfit.repositories.sites.ever_applied_obstacle_polygons", return_value=list(known)),
        patch("solarfit.packs.config_pack.get_auto_apply_confidence_threshold", return_value=0.85),
        patch("solarfit.engine.obstacles.session_scope", _fake_session_scope),
        patch("solarfit.repositories.sites.applied_obstacle_ids", return_value=set()),
        patch("solarfit.repositories.sites.new_geometry_version"),
        patch("solarfit.repositories.sites.get", return_value=site),
        patch("solarfit.engine.area.compute_usable_area_m2", return_value=42.0),
        patch("solarfit.repositories.analysis_cache.force_refresh"),
    ):
        return apply_or_flag(site, obstacles)


def test_a_detector_obstacle_straddling_the_roof_edge_is_clipped_not_dropped():
    """Detections are found on the cached Google boundary, which is bigger
    than the roof the customer drew. The part on this roof must survive."""
    from shapely.geometry import shape

    site = _site()
    straddling = _obstacle_straddling_boundary_edge("cv_detector")

    result = _run_apply_or_flag(site, [straddling])

    assert [o.id for o in result] == [straddling.id]
    assert shape(BOUNDARY).covers(shape(result[0].bounding_polygon))
    assert shape(result[0].bounding_polygon).bounds[2] == pytest.approx(78.4874)


def test_a_vision_llm_obstacle_straddling_the_roof_edge_is_still_dropped():
    """Clipping is for detector output only - existing vision-LLM behaviour
    (OBS-03 drops anything the boundary does not fully cover) is unchanged."""
    site = _site()

    result = _run_apply_or_flag(site, [_obstacle_straddling_boundary_edge("vision_llm")])

    assert result == []


def _within_boundary(confidence: float, source: str) -> Obstacle:
    obstacle = _obstacle_within_boundary(confidence)
    obstacle.source = source
    return obstacle


def test_a_vision_llm_obstacle_at_the_same_score_is_still_only_advisory():
    site = _site()
    guessed = _within_boundary(0.45, "vision_llm")

    result = _run_apply_or_flag(site, [guessed])

    assert [o.id for o in result] == [guessed.id]
    assert result[0].applied is False


def test_a_redetected_obstacle_is_not_applied_twice():
    """Detector obstacles get new random ids each run, so a second scan of
    the same roof (e.g. the assessment after the obstacles screen) finds
    the same objects again. They must not be listed/applied a second time."""
    site = _site()
    already_there = _obstacle_within_boundary(confidence=0.5)  # same polygon as the new one
    again = _within_boundary(0.5, "cv_detector")

    result = _run_apply_or_flag(site, [again], known=[already_there.bounding_polygon])

    assert result == []


def test_a_detection_the_customer_removed_does_not_come_back():
    """A removed obstacle's polygon is still in the site's history (only a
    tombstone is added), and is passed in `known` exactly like an applied
    one - so a re-scan cannot resurrect a false positive."""
    site = _site()
    removed_earlier = _obstacle_within_boundary(confidence=0.5)
    rescanned = _within_boundary(0.5, "cv_detector")

    result = _run_apply_or_flag(site, [rescanned], known=[removed_earlier.bounding_polygon])

    assert result == []


def test_the_vision_llm_obstacles_are_not_geometrically_deduplicated():
    """De-duplication is for detector output (fresh ids per run). The
    vision-LLM path keeps its existing id-based idempotency untouched."""
    site = _site()
    llm = _within_boundary(0.95, "vision_llm")

    result = _run_apply_or_flag(site, [llm], known=[llm.bounding_polygon])

    assert [o.id for o in result] == [llm.id]


def _run_capturing(site, obstacles, known=()):
    """Like _run_apply_or_flag, but also returns the mocks that show what
    was written: the exclusions version and the review candidates."""
    with (
        patch("solarfit.packs.config_pack.get_auto_apply_confidence_threshold", return_value=0.85),
        patch("solarfit.engine.obstacles.session_scope", _fake_session_scope),
        patch("solarfit.repositories.sites.ever_applied_obstacle_polygons", return_value=list(known)),
        patch("solarfit.repositories.sites.applied_obstacle_ids", return_value=set()),
        patch("solarfit.repositories.sites.new_geometry_version") as new_version,
        patch("solarfit.repositories.sites.get", return_value=site),
        patch("solarfit.engine.area.compute_usable_area_m2", return_value=42.0),
        patch("solarfit.repositories.analysis_cache.force_refresh"),
        patch("solarfit.repositories.obstacle_candidates.add_candidates") as add_candidates,
        patch("solarfit.repositories.obstacle_candidates.all_polygons", return_value=[]),
    ):
        result = apply_or_flag(site, obstacles)
    return result, new_version, add_candidates


def test_a_model_detection_is_held_for_review_never_applied():
    """THE rule: a detection must not shrink the customer's usable roof
    until they have confirmed it - however confident the models are."""
    site = _site()
    sure_thing = _within_boundary(0.99, "cv_detector")

    result, new_version, add_candidates = _run_capturing(site, [sure_thing])

    assert [o.id for o in result] == [sure_thing.id]
    assert result[0].applied is False
    new_version.assert_not_called()  # exclusions untouched
    add_candidates.assert_called_once()
    stored = add_candidates.call_args.args[2]
    assert [o.id for o in stored] == [sure_thing.id]


def test_only_the_vision_llm_can_still_auto_apply():
    site = _site()
    llm = _within_boundary(0.95, "vision_llm")
    detected = _within_boundary(0.95, "cv_detector")
    detected.bounding_polygon = _obstacle_straddling_boundary_edge("cv_detector").bounding_polygon

    result, new_version, add_candidates = _run_capturing(site, [llm, detected])

    applied = {o.id: o.applied for o in result}
    assert applied[llm.id] is True
    assert applied[detected.id] is False
    new_version.assert_called_once()
    assert new_version.call_args.kwargs["applied_obstacle_ids"] == [llm.id]
    assert [o.id for o in add_candidates.call_args.args[2]] == [detected.id]


def test_a_new_detection_elsewhere_on_the_roof_is_offered_for_review():
    site = _site()
    elsewhere = Obstacle(
        type="other",
        confidence=0.5,
        source="cv_detector",
        bounding_polygon={
            "type": "Polygon",
            "coordinates": [
                [[78.4868, 17.3851], [78.4870, 17.3851], [78.4870, 17.3853], [78.4868, 17.3853], [78.4868, 17.3851]]
            ],
        },
    )
    known = [_obstacle_within_boundary(confidence=0.5).bounding_polygon]

    result, _new_version, add_candidates = _run_capturing(site, [elsewhere], known=known)

    assert [o.id for o in result] == [elsewhere.id]
    assert [o.id for o in add_candidates.call_args.args[2]] == [elsewhere.id]


def test_a_redetection_of_a_reviewed_candidate_is_not_offered_again():
    """Candidates the customer has already seen (pending, confirmed or
    ignored) are part of what the site knows - passed in `known` here,
    exactly as the candidates' polygons are read in production."""
    site = _site()
    again = _within_boundary(0.6, "cv_detector")
    seen_before = _obstacle_within_boundary(confidence=0.5).bounding_polygon

    result, _new_version, add_candidates = _run_capturing(site, [again], known=[seen_before])

    assert result == []
    add_candidates.assert_not_called()
