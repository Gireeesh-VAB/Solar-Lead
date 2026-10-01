"""Phase 7 — providers/obstacle_detectors.py's pluggable detector seam.

No second detector exists yet (get_configured_detectors() returns []) —
these tests exercise the seam itself (the Protocol, the combiner's
failure isolation, the merge into refine_vision_task) using a small fake
detector, so the architecture is proven correct before a real CV
detector is ever plugged into it.
"""

from affine import Affine

from solarfit.domain.assessment import Obstacle
from solarfit.providers.obstacle_detectors import detect_obstacles, get_configured_detectors
from solarfit.providers.vision import CroppedImagery

_BOUNDARY = {
    "type": "Polygon",
    "coordinates": [[[78.4860, 17.3845], [78.4874, 17.3845], [78.4874, 17.3855], [78.4860, 17.3855], [78.4860, 17.3845]]],
}


def _cropped() -> CroppedImagery:
    return CroppedImagery(png_bytes=b"", transform=Affine.identity(), crs=None, width=10, height=10)


def _obstacle(source: str = "cv_detector") -> Obstacle:
    return Obstacle(
        type="water_tank",
        bounding_polygon={
            "type": "Polygon",
            "coordinates": [[[78.4861, 17.3846], [78.4862, 17.3846], [78.4862, 17.3847], [78.4861, 17.3847], [78.4861, 17.3846]]],
        },
        confidence=0.9,
        source=source,
    )


class _FakeDetector:
    name = "fake_cv_detector"

    def __init__(self, obstacles=None, *, raises=False):
        self._obstacles = obstacles or []
        self._raises = raises

    def detect(self, cropped, boundary):
        if self._raises:
            raise RuntimeError("detector blew up")
        return self._obstacles


def test_no_detectors_configured_today():
    """Documents current state — the seam exists, nothing plugs into it
    yet. This test is EXPECTED to start failing the day a real detector
    is registered; that's the point."""
    assert get_configured_detectors() == []


def test_combines_obstacles_from_multiple_detectors():
    obstacle_a = _obstacle()
    obstacle_b = _obstacle()
    detectors = [_FakeDetector([obstacle_a]), _FakeDetector([obstacle_b])]

    result = detect_obstacles(_cropped(), _BOUNDARY, detectors=detectors)

    assert result == [obstacle_a, obstacle_b]


def test_a_failing_detector_does_not_take_down_the_others():
    obstacle = _obstacle()
    detectors = [_FakeDetector(raises=True), _FakeDetector([obstacle])]

    result = detect_obstacles(_cropped(), _BOUNDARY, detectors=detectors)

    assert result == [obstacle]


def test_no_detectors_returns_empty_list():
    assert detect_obstacles(_cropped(), _BOUNDARY, detectors=[]) == []


def test_every_detector_failing_degrades_to_empty_not_an_exception():
    detectors = [_FakeDetector(raises=True), _FakeDetector(raises=True)]

    assert detect_obstacles(_cropped(), _BOUNDARY, detectors=detectors) == []


# ---------------------------------------------------------------------------
# workers/celery_app.py::refine_vision_task — the merge wiring itself.
# ---------------------------------------------------------------------------


def test_refine_vision_task_merges_a_configured_detectors_obstacles(monkeypatch):
    from solarfit.domain.assessment import VisionRefinement
    from solarfit.workers.celery_app import refine_vision_task

    llm_obstacle = _obstacle(source="vision_llm")
    cv_obstacle = _obstacle(source="cv_detector")

    monkeypatch.setattr(
        "solarfit.providers.vision.fetch_rgb_imagery", lambda lat, lng, r: b"fake-tiff"
    )
    monkeypatch.setattr("solarfit.providers.vision.crop_to_boundary", lambda imagery, boundary: _cropped())
    monkeypatch.setattr(
        "solarfit.providers.vision.refine_with_vision_model",
        lambda cropped, boundary: VisionRefinement(obstacles=[llm_obstacle], confidence=0.9, status="ok"),
    )
    monkeypatch.setattr(
        "solarfit.providers.obstacle_detectors.get_configured_detectors",
        lambda: [_FakeDetector([cv_obstacle])],
    )

    result = refine_vision_task(17.385, 78.4867, _BOUNDARY)

    assert {o["id"] for o in result["obstacles"]} == {llm_obstacle.id, cv_obstacle.id}


def test_refine_vision_task_is_unchanged_with_no_detectors_configured(monkeypatch):
    """Today's actual behaviour (get_configured_detectors() == []): the
    result is exactly what refine_with_vision_model() alone returned."""
    from solarfit.domain.assessment import VisionRefinement
    from solarfit.workers.celery_app import refine_vision_task

    llm_obstacle = _obstacle(source="vision_llm")
    monkeypatch.setattr(
        "solarfit.providers.vision.fetch_rgb_imagery", lambda lat, lng, r: b"fake-tiff"
    )
    monkeypatch.setattr("solarfit.providers.vision.crop_to_boundary", lambda imagery, boundary: _cropped())
    monkeypatch.setattr(
        "solarfit.providers.vision.refine_with_vision_model",
        lambda cropped, boundary: VisionRefinement(obstacles=[llm_obstacle], confidence=0.9, status="ok"),
    )

    result = refine_vision_task(17.385, 78.4867, _BOUNDARY)

    assert [o["id"] for o in result["obstacles"]] == [llm_obstacle.id]
