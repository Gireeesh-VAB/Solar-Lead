"""Phase 7 — providers/obstacle_detectors.py's pluggable detector seam.

These tests exercise the seam itself (the Protocol, the combiner's
failure isolation, the merge into refine_vision_task) using a small fake
detector. The real YOLO ensemble has its own tests in
test_yolo_obstacle_detector.py.
"""

import pytest
from affine import Affine

from solarfit.domain.assessment import Obstacle
from solarfit.providers.obstacle_detectors import detect_obstacles, get_configured_detectors
from solarfit.providers.vision import CroppedImagery

_BOUNDARY = {
    "type": "Polygon",
    "coordinates": [[[78.4860, 17.3845], [78.4874, 17.3845], [78.4874, 17.3855], [78.4860, 17.3855], [78.4860, 17.3845]]],
}


@pytest.fixture(autouse=True)
def _isolate_from_local_env(monkeypatch):
    """The developer's own .env may point yolo_model_dir at real weights;
    these tests must not depend on that."""
    from solarfit.config import get_settings

    monkeypatch.setattr(get_settings(), "yolo_model_dir", "")


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


def test_no_detectors_configured_without_a_model_dir():
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
    from solarfit.config import get_settings
    from solarfit.domain.assessment import VisionRefinement
    from solarfit.workers.celery_app import refine_vision_task

    monkeypatch.setattr(get_settings(), "openai_api_key", "sk-test")

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
    """With get_configured_detectors() == [], the result is exactly what
    refine_with_vision_model() alone returned."""
    from solarfit.config import get_settings
    from solarfit.domain.assessment import VisionRefinement
    from solarfit.workers.celery_app import refine_vision_task

    monkeypatch.setattr(get_settings(), "openai_api_key", "sk-test")

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


def test_detectors_still_contribute_when_the_gpt_step_is_skipped(monkeypatch):
    """No OPENAI_API_KEY: the vision-LLM is skipped (never called), but the
    independent detectors must still run and keep their obstacles."""
    from solarfit.config import get_settings
    from solarfit.workers.celery_app import refine_vision_task

    cv_obstacle = _obstacle(source="cv_detector")
    monkeypatch.setattr(get_settings(), "openai_api_key", "")
    monkeypatch.setattr(
        "solarfit.providers.vision.fetch_rgb_imagery", lambda lat, lng, r: b"fake-tiff"
    )
    monkeypatch.setattr("solarfit.providers.vision.crop_to_boundary", lambda imagery, boundary: _cropped())

    def _must_not_be_called(cropped, boundary):
        raise AssertionError("the GPT-4 Vision step ran without an API key")

    monkeypatch.setattr("solarfit.providers.vision.refine_with_vision_model", _must_not_be_called)
    monkeypatch.setattr(
        "solarfit.providers.obstacle_detectors.get_configured_detectors",
        lambda: [_FakeDetector([cv_obstacle])],
    )

    result = refine_vision_task(17.385, 78.4867, _BOUNDARY)

    assert result["status"] == "insufficient_data"  # describes the GPT step only
    assert [o["id"] for o in result["obstacles"]] == [cv_obstacle.id]


# ---------------------------------------------------------------------------
# workers/celery_app.py::detect_site_obstacles_task - the on-demand scan of
# one customer's selected roof (backs POST /app/checks/{id}/obstacles/detect).
# ---------------------------------------------------------------------------


def _patch_scan(monkeypatch, *, site, detectors=None, imagery_raises=None, applied=None):
    from contextlib import contextmanager

    @contextmanager
    def _fake_session_scope():
        yield object()

    monkeypatch.setattr("solarfit.db.session_scope", _fake_session_scope)
    monkeypatch.setattr("solarfit.repositories.sites.get", lambda session, site_id: site)
    monkeypatch.setattr(
        "solarfit.providers.obstacle_detectors.get_configured_detectors",
        lambda: detectors if detectors is not None else [],
    )

    def _fetch(lat, lng, *a, **k):
        if imagery_raises:
            raise imagery_raises
        return b"fake-tiff"

    monkeypatch.setattr("solarfit.providers.vision.fetch_rgb_imagery", _fetch)
    monkeypatch.setattr("solarfit.providers.vision.crop_to_boundary", lambda imagery, boundary: _cropped())
    seen = {}

    def _apply(s, obstacles):
        seen["site"], seen["obstacles"] = s, obstacles
        return applied if applied is not None else obstacles

    monkeypatch.setattr("solarfit.engine.obstacles.apply_or_flag", _apply)
    return seen


def _site_stub(boundary=_BOUNDARY):
    from types import SimpleNamespace

    return SimpleNamespace(
        id="site-1",
        boundary=boundary,
        centroid={"type": "Point", "coordinates": [78.4867, 17.385]},
    )


def test_scan_of_a_missing_site_or_roof_reports_no_roof(monkeypatch):
    from solarfit.workers.celery_app import detect_site_obstacles_task

    _patch_scan(monkeypatch, site=None)
    assert detect_site_obstacles_task("site-1") == {"status": "no_roof", "obstacles": []}

    _patch_scan(monkeypatch, site=_site_stub(boundary=None))
    assert detect_site_obstacles_task("site-1") == {"status": "no_roof", "obstacles": []}


def test_scan_without_a_configured_detector_says_so(monkeypatch):
    from solarfit.workers.celery_app import detect_site_obstacles_task

    _patch_scan(monkeypatch, site=_site_stub(), detectors=[])

    assert detect_site_obstacles_task("site-1") == {"status": "not_configured", "obstacles": []}


def test_scan_with_no_satellite_imagery_is_an_ordinary_outcome(monkeypatch):
    from solarfit.workers.celery_app import detect_site_obstacles_task

    _patch_scan(
        monkeypatch,
        site=_site_stub(),
        detectors=[_FakeDetector([_obstacle()])],
        imagery_raises=ValueError("no imagery here"),
    )

    assert detect_site_obstacles_task("site-1") == {"status": "no_imagery", "obstacles": []}


def test_scan_detects_on_the_sites_own_boundary_then_applies(monkeypatch):
    from solarfit.workers.celery_app import detect_site_obstacles_task

    found = _obstacle()
    site = _site_stub()
    seen = _patch_scan(monkeypatch, site=site, detectors=[_FakeDetector([found])])

    result = detect_site_obstacles_task("site-1")

    assert result["status"] == "ok"
    assert [o["id"] for o in result["obstacles"]] == [found.id]
    assert seen["site"] is site  # applied against THIS site
    assert [o.id for o in seen["obstacles"]] == [found.id]


class _SelfSourcedDetector(_FakeDetector):
    """Like the YOLO ensemble with a Maps key: fetches its own satellite
    frame, so the shared Solar API crop is not needed."""

    needs_solar_imagery = False

    def __init__(self, obstacles=None):
        super().__init__(obstacles)
        self.received = "unset"

    def detect(self, cropped, boundary):
        self.received = cropped
        return self._obstacles


def test_scan_skips_the_solar_download_when_the_detector_brings_its_own_imagery(monkeypatch):
    from solarfit.workers.celery_app import detect_site_obstacles_task

    detector = _SelfSourcedDetector([_obstacle()])
    # If the Solar imagery were fetched this would turn the scan into "no_imagery".
    _patch_scan(monkeypatch, site=_site_stub(), detectors=[detector], imagery_raises=ValueError("must not be called"))

    result = detect_site_obstacles_task("site-1")

    assert result["status"] == "ok"
    assert len(result["obstacles"]) == 1
    assert detector.received is None


def test_scan_still_fetches_solar_imagery_for_a_detector_that_needs_it(monkeypatch):
    from solarfit.workers.celery_app import detect_site_obstacles_task

    detector = _SelfSourcedDetector([_obstacle()])
    detector.needs_solar_imagery = True
    _patch_scan(monkeypatch, site=_site_stub(), detectors=[detector])

    detect_site_obstacles_task("site-1")

    assert detector.received is not None


def test_solar_imagery_needed_defaults_to_true_for_a_detector_that_does_not_say():
    from solarfit.providers.obstacle_detectors import solar_imagery_needed

    assert solar_imagery_needed([_FakeDetector()]) is True
    assert solar_imagery_needed([_SelfSourcedDetector()]) is False
    assert solar_imagery_needed([_SelfSourcedDetector(), _FakeDetector()]) is True
    assert solar_imagery_needed([]) is False


def test_scan_reports_only_what_apply_or_flag_kept(monkeypatch):
    """apply_or_flag drops duplicates/invalid ones - the scan reports its
    result, not the raw detections."""
    from solarfit.workers.celery_app import detect_site_obstacles_task

    _patch_scan(
        monkeypatch,
        site=_site_stub(),
        detectors=[_FakeDetector([_obstacle(), _obstacle()])],
        applied=[],
    )

    assert detect_site_obstacles_task("site-1") == {"status": "ok", "obstacles": []}
