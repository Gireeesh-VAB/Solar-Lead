"""providers/remote_obstacle_detector.py - the obstacle-service as an ObstacleDetector, and how get_configured_detectors() picks it.
No network: httpx.post is replaced."""

import httpx
import pytest

from solarfit.config import get_settings
from solarfit.providers import obstacle_detectors, remote_obstacle_detector
from solarfit.providers.remote_obstacle_detector import RemoteObstacleDetector

_BOUNDARY = {
    "type": "Polygon",
    "coordinates": [[[78.4860, 17.3845], [78.4874, 17.3845], [78.4874, 17.3855], [78.4860, 17.3855], [78.4860, 17.3845]]],
}
_POLYGON = {
    "type": "Polygon",
    "coordinates": [[[78.4861, 17.3846], [78.4862, 17.3846], [78.4862, 17.3847], [78.4861, 17.3847], [78.4861, 17.3846]]],
}


class _Response:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code, self._payload, self.text = status, payload, text

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


@pytest.fixture
def post(monkeypatch):
    """Replaces httpx.post; the test sets .response (or .error) and reads .calls."""

    class _Post:
        response = _Response(200, {"status": "ok", "obstacles": [], "stats": {}})
        error: Exception | None = None
        calls: list = []

        def __call__(self, url, json=None, timeout=None):
            self.calls.append({"url": url, "json": json, "timeout": timeout})
            if self.error:
                raise self.error
            return self.response

    fake = _Post()
    fake.calls = []
    monkeypatch.setattr(remote_obstacle_detector.httpx, "post", fake)
    return fake


def test_service_obstacles_become_cv_detector_obstacles(post):
    post.response = _Response(
        200, {"status": "ok", "obstacles": [{"polygon": _POLYGON, "confidence": 0.81234, "votes": 2, "area_m2": 12.0}], "stats": {"returned": 1}}
    )

    found = RemoteObstacleDetector("http://svc:8200/").detect(None, _BOUNDARY)

    assert len(found) == 1
    assert found[0].type == "other" and found[0].source == "cv_detector"
    assert found[0].confidence == pytest.approx(0.8123) and found[0].bounding_polygon == _POLYGON


def test_the_request_carries_the_boundary_and_the_packs_tunables(post):
    RemoteObstacleDetector("http://svc:8200/", timeout_s=7).detect(None, _BOUNDARY)

    call = post.calls[0]
    assert call["url"] == "http://svc:8200/detect"  # trailing slash tidied
    assert call["json"]["boundary"] == _BOUNDARY
    assert call["json"]["roof_overlap_min"] == pytest.approx(0.3) and call["json"]["model_conf"] == pytest.approx(0.25)
    assert call["timeout"] == 7


def test_the_service_brings_its_own_imagery():
    assert RemoteObstacleDetector("http://svc:8200").needs_solar_imagery is False
    assert obstacle_detectors.solar_imagery_needed([RemoteObstacleDetector("http://svc:8200")]) is False


def test_no_boundary_means_no_call_and_no_obstacles(post):
    assert RemoteObstacleDetector("http://svc:8200").detect(None, {}) == []
    assert post.calls == []


@pytest.mark.parametrize("error", [httpx.ConnectError("refused"), httpx.ReadTimeout("slow")])
def test_an_unreachable_service_degrades_to_no_obstacles_and_never_raises(post, error, caplog):
    post.error = error
    with caplog.at_level("WARNING"):
        assert RemoteObstacleDetector("http://svc:8200").detect(None, _BOUNDARY) == []
    assert "unreachable" in caplog.text


@pytest.mark.parametrize("status", [422, 502, 503, 500])
def test_a_service_error_degrades_to_no_obstacles(post, status, caplog):
    post.response = _Response(status, text='{"detail":"no satellite view"}')
    with caplog.at_level("WARNING"):
        assert RemoteObstacleDetector("http://svc:8200").detect(None, _BOUNDARY) == []
    assert str(status) in caplog.text


def test_an_unreadable_answer_degrades_to_no_obstacles(post):
    post.response = _Response(200, payload=None)  # json() raises
    assert RemoteObstacleDetector("http://svc:8200").detect(None, _BOUNDARY) == []
    post.response = _Response(200, {"unexpected": True})  # no "obstacles"
    assert RemoteObstacleDetector("http://svc:8200").detect(None, _BOUNDARY) == []


def test_one_malformed_obstacle_is_skipped_and_the_rest_kept(post):
    post.response = _Response(
        200, {"obstacles": [{"nonsense": 1}, {"polygon": _POLYGON, "confidence": 0.7, "votes": 1, "area_m2": 3.0}], "stats": {}}
    )
    assert len(RemoteObstacleDetector("http://svc:8200").detect(None, _BOUNDARY)) == 1


# --- how the detector list is chosen --------------------------------------------------------------------------------------------------


def test_a_service_url_selects_the_remote_detector_and_loads_no_models(monkeypatch, tmp_path):
    settings = get_settings()
    monkeypatch.setattr(settings, "obstacle_service_url", "http://svc:8200")
    monkeypatch.setattr(settings, "yolo_model_dir", str(tmp_path))  # even with weights configured, the service wins
    (tmp_path / "a.pt").write_bytes(b"x")

    detectors = obstacle_detectors.get_configured_detectors()

    assert [type(d) for d in detectors] == [RemoteObstacleDetector]


def test_without_a_service_url_the_in_process_ensemble_is_unchanged(monkeypatch, tmp_path):
    settings = get_settings()
    monkeypatch.setattr(settings, "obstacle_service_url", "")
    monkeypatch.setattr(settings, "yolo_model_dir", "")

    assert obstacle_detectors.get_configured_detectors() == []
