"""Tests for providers/yolo_obstacle_detector.py's ensemble fusion and its
registration in providers/obstacle_detectors.py. No YOLO weights needed —
fusion is a pure function over per-model detections."""

import pytest
from affine import Affine
from shapely.geometry import box

from solarfit.providers import obstacle_detectors
from solarfit.providers.vision import CroppedImagery
from solarfit.providers.yolo_obstacle_detector import (
    Detection,
    YoloEnsembleDetector,
    _pixel_polygon_to_geojson,
    fuse_detections,
)


def _det(model: int, conf: float, x0=0, y0=0, x1=10, y1=10) -> Detection:
    return Detection(model, box(x0, y0, x1, y1), conf)


def _fuse(dets, n_models=3, match_iou=0.4, min_score=0.2):
    return fuse_detections(dets, n_models=n_models, match_iou=match_iou, min_score=min_score)


def test_models_agreeing_score_the_highest_confidence_and_count_their_votes():
    fused = _fuse([_det(0, 0.9), _det(1, 0.8), _det(2, 0.7)])

    assert len(fused) == 1
    assert fused[0].votes == 3
    assert fused[0].score == pytest.approx(0.9)


def test_a_detection_only_one_model_saw_is_still_reported_at_its_own_confidence():
    """The ensemble is a union: one model's 0.55 must survive, not be
    divided by three and dropped (that hid real obstacles)."""
    fused = _fuse([_det(1, 0.55)])

    assert len(fused) == 1
    assert fused[0].votes == 1
    assert fused[0].score == pytest.approx(0.55)


def test_non_overlapping_detections_stay_separate_obstacles():
    fused = _fuse([_det(0, 0.9, 0, 0, 10, 10), _det(1, 0.9, 50, 50, 60, 60)])

    assert len(fused) == 2


def test_one_model_detecting_the_same_thing_twice_counts_as_one_vote():
    fused = _fuse([_det(0, 0.9), _det(0, 0.6, 1, 1, 10, 10)])

    assert len(fused) == 1
    assert fused[0].votes == 1
    assert fused[0].score == pytest.approx(0.9)


def test_scores_below_the_floor_are_dropped():
    assert _fuse([_det(0, 0.1)]) == []


def test_fused_outline_is_the_most_confident_members_not_a_bloated_union():
    fused = _fuse([_det(0, 0.7, 2, 0, 12, 10), _det(1, 0.9, 0, 0, 10, 10)])

    assert len(fused) == 1
    assert fused[0].polygon.bounds == (0.0, 0.0, 10.0, 10.0)  # the 0.9 model's outline


def test_an_outline_mostly_inside_another_is_the_same_object():
    # A small outline wholly inside a big one: IoU is only 0.25, containment is 1.0.
    fused = _fuse([_det(0, 0.9, 0, 0, 20, 20), _det(1, 0.6, 5, 5, 15, 15)])

    assert len(fused) == 1
    assert fused[0].votes == 2


def test_results_are_ranked_most_confident_first():
    fused = _fuse(
        [
            _det(0, 0.6, 0, 0, 10, 10),  # one vote, 0.6
            _det(0, 0.9, 50, 50, 60, 60),  # two votes, best 0.9
            _det(1, 0.8, 50, 50, 60, 60),
            _det(2, 0.6, 100, 100, 110, 110),  # one vote, 0.6 - ties lose to more votes
            _det(1, 0.6, 100, 100, 110, 110),
        ]
    )

    assert [(round(f.score, 2), f.votes) for f in fused] == [(0.9, 2), (0.6, 2), (0.6, 1)]


def test_no_models_means_no_detections():
    assert _fuse([_det(0, 0.9)], n_models=0) == []


def test_pixel_polygon_is_georeferenced_through_the_crops_own_transform():
    # 1 m pixels in a UTM-less (EPSG:4326-style) frame starting at lng 78, lat 17.
    cropped = CroppedImagery(
        png_bytes=b"",
        transform=Affine(0.00001, 0, 78.0, 0, -0.00001, 17.0),
        crs=None,
        width=100,
        height=100,
    )

    geojson = _pixel_polygon_to_geojson(box(10, 10, 20, 20), cropped)

    assert geojson is not None and geojson["type"] == "Polygon"
    ring = geojson["coordinates"][0]
    assert ring[0] == ring[-1]
    lngs = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    assert min(lngs) == pytest.approx(78.0001)
    assert max(lngs) == pytest.approx(78.0002)
    assert max(lats) == pytest.approx(16.9999)
    assert min(lats) == pytest.approx(16.9998)


def test_detector_with_no_models_reports_nothing_instead_of_raising():
    detector = YoloEnsembleDetector([])
    cropped = CroppedImagery(png_bytes=b"", transform=Affine.identity(), crs=None, width=1, height=1)

    assert detector.detect(cropped, {}) == []


def test_undecodable_imagery_degrades_to_no_obstacles(tmp_path):
    detector = YoloEnsembleDetector([tmp_path / "a.pt"])
    cropped = CroppedImagery(png_bytes=b"not a png", transform=Affine.identity(), crs=None, width=1, height=1)

    assert detector.detect(cropped, {}) == []


def test_no_detectors_are_configured_without_a_model_dir(monkeypatch):
    monkeypatch.setattr(obstacle_detectors.get_settings(), "yolo_model_dir", "")

    assert obstacle_detectors.get_configured_detectors() == []


def test_ensemble_is_registered_when_the_model_dir_has_weights(monkeypatch, tmp_path):
    for name in ("a.pt", "b.pt", "c.pt"):
        (tmp_path / name).write_bytes(b"x")
    obstacle_detectors._yolo_ensemble_for.cache_clear()
    monkeypatch.setattr(obstacle_detectors.get_settings(), "yolo_model_dir", str(tmp_path))

    detectors = obstacle_detectors.get_configured_detectors()

    assert len(detectors) == 1
    assert detectors[0].name == "yolo_ensemble"
    assert detectors[0].n_models == 3
    obstacle_detectors._yolo_ensemble_for.cache_clear()


def test_an_empty_model_dir_disables_the_ensemble(monkeypatch, tmp_path):
    obstacle_detectors._yolo_ensemble_for.cache_clear()
    monkeypatch.setattr(obstacle_detectors.get_settings(), "yolo_model_dir", str(tmp_path))

    assert obstacle_detectors.get_configured_detectors() == []
    obstacle_detectors._yolo_ensemble_for.cache_clear()


def test_obstacle_poking_past_the_roof_edge_is_clipped_to_the_roof():
    from shapely.geometry import shape

    from solarfit.providers.yolo_obstacle_detector import _clip_to_boundary

    roof = box(0, 0, 10, 10)
    sticking_out = {"type": "Polygon", "coordinates": [[[8, 2], [12, 2], [12, 6], [8, 6], [8, 2]]]}

    clipped = _clip_to_boundary(sticking_out, roof)

    assert clipped is not None
    assert roof.covers(shape(clipped))
    assert shape(clipped).bounds == pytest.approx((8.0, 2.0, 10.0, 6.0), abs=1e-6)


def test_obstacle_entirely_outside_the_roof_is_dropped():
    from solarfit.providers.yolo_obstacle_detector import _clip_to_boundary

    outside = {"type": "Polygon", "coordinates": [[[20, 20], [22, 20], [22, 22], [20, 22], [20, 20]]]}

    assert _clip_to_boundary(outside, box(0, 0, 10, 10)) is None


def test_no_boundary_leaves_the_obstacle_untouched():
    from solarfit.providers.yolo_obstacle_detector import _clip_to_boundary

    poly = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}

    assert _clip_to_boundary(poly, None) == poly


def test_a_relative_model_dir_resolves_against_the_backend_folder(monkeypatch):
    from solarfit.config import _BACKEND_DIR

    obstacle_detectors._yolo_ensemble_for.cache_clear()
    seen = []
    monkeypatch.setattr(obstacle_detectors, "_yolo_ensemble_for", lambda d: seen.append(d))
    monkeypatch.setattr(obstacle_detectors.get_settings(), "yolo_model_dir", "models/obstacles")

    obstacle_detectors.get_configured_detectors()

    assert seen == [str(_BACKEND_DIR / "models" / "obstacles")]
