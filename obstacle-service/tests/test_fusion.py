"""Ensemble fusion is a pure function over per-model detections - no weights needed."""
import pytest
from shapely.geometry import box

from obstacle_service.ensemble import Detection, fuse_detections


def _det(model: int, conf: float, x0=0, y0=0, x1=10, y1=10) -> Detection:
    return Detection(model, box(x0, y0, x1, y1), conf)


def _fuse(dets, n_models=3, match_iou=0.4, min_score=0.2):
    return fuse_detections(dets, n_models=n_models, match_iou=match_iou, min_score=min_score)


def test_models_agreeing_score_the_highest_confidence_and_count_their_votes():
    fused = _fuse([_det(0, 0.9), _det(1, 0.8), _det(2, 0.7)])
    assert len(fused) == 1 and fused[0].votes == 3 and fused[0].score == pytest.approx(0.9)


def test_a_detection_only_one_model_saw_is_still_reported_at_its_own_confidence():
    """The ensemble is a union: one model's 0.55 must survive, not be divided by three and dropped."""
    fused = _fuse([_det(1, 0.55)])
    assert len(fused) == 1 and fused[0].votes == 1 and fused[0].score == pytest.approx(0.55)


def test_non_overlapping_detections_stay_separate_obstacles():
    assert len(_fuse([_det(0, 0.9, 0, 0, 10, 10), _det(1, 0.9, 50, 50, 60, 60)])) == 2


def test_one_model_detecting_the_same_thing_twice_counts_as_one_vote():
    fused = _fuse([_det(0, 0.9), _det(0, 0.6, 1, 1, 10, 10)])
    assert len(fused) == 1 and fused[0].votes == 1 and fused[0].score == pytest.approx(0.9)


def test_scores_below_the_floor_are_dropped():
    assert _fuse([_det(0, 0.1)]) == []


def test_fused_outline_is_the_most_confident_members_not_a_bloated_union():
    fused = _fuse([_det(0, 0.7, 2, 0, 12, 10), _det(1, 0.9, 0, 0, 10, 10)])
    assert len(fused) == 1 and fused[0].polygon.bounds == (0.0, 0.0, 10.0, 10.0)


def test_an_outline_mostly_inside_another_is_the_same_object():
    # A small outline wholly inside a big one: IoU is only 0.25, containment is 1.0.
    fused = _fuse([_det(0, 0.9, 0, 0, 20, 20), _det(1, 0.6, 5, 5, 15, 15)])
    assert len(fused) == 1 and fused[0].votes == 2


def test_results_are_ranked_most_confident_first():
    fused = _fuse(
        [
            _det(0, 0.6, 0, 0, 10, 10),
            _det(0, 0.9, 50, 50, 60, 60), _det(1, 0.8, 50, 50, 60, 60),
            _det(2, 0.6, 100, 100, 110, 110), _det(1, 0.6, 100, 100, 110, 110),
        ]
    )
    assert [(round(f.score, 2), f.votes) for f in fused] == [(0.9, 2), (0.6, 2), (0.6, 1)]


def test_no_models_means_no_detections():
    assert _fuse([_det(0, 0.9)], n_models=0) == []
