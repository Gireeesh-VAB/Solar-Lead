from fastapi.testclient import TestClient

import app as app_module
from obstacle_service.ensemble import DetectionResult, Ensemble, Obstacle

_ROOF = {"type": "Polygon", "coordinates": [[[78.0, 17.0], [78.0001, 17.0], [78.0001, 16.9998], [78.0, 16.9998], [78.0, 17.0]]]}


def _client() -> TestClient:
    return TestClient(app_module.app)  # no `with`: the startup warm-up is skipped, nothing is loaded


def test_health_reports_no_models_and_missing_imagery_without_leaking_anything():
    body = _client().get("/health").json()

    assert body["ok"] is False and body["models"] == []
    assert body["imagery"] == "missing GOOGLE_MAPS_API_KEY"
    assert "key" not in {k.lower() for k in body["settings"]}


def test_detect_without_models_answers_503():
    assert _client().post("/detect", json={"boundary": _ROOF}).status_code == 503


def test_detect_rejects_a_boundary_that_is_not_a_polygon():
    assert _client().post("/detect", json={"boundary": {"type": "Point", "coordinates": [78, 17]}}).status_code == 422
    assert _client().post("/detect", json={"boundary": {"nonsense": True}}).status_code == 422


def test_detect_returns_obstacles_and_the_stats_trail(monkeypatch, tmp_path):
    monkeypatch.setenv("OBSTACLE_MODEL_DIR", str(tmp_path))
    (tmp_path / "a.pt").write_bytes(b"x")
    obstacle = Obstacle(polygon=_ROOF, confidence=0.8, votes=2, area_m2=12.5)
    monkeypatch.setattr(Ensemble, "detect", lambda self, boundary, frame=None, settings=None: DetectionResult("ok", [obstacle], {"returned": 1}))

    body = _client().post("/detect", json={"boundary": _ROOF}).json()

    assert body["status"] == "ok" and body["stats"] == {"returned": 1}
    assert body["obstacles"] == [{"polygon": _ROOF, "confidence": 0.8, "votes": 2, "area_m2": 12.5}]


def test_detect_explains_a_missing_satellite_view(monkeypatch, tmp_path):
    monkeypatch.setenv("OBSTACLE_MODEL_DIR", str(tmp_path))
    (tmp_path / "a.pt").write_bytes(b"x")

    response = _client().post("/detect", json={"boundary": _ROOF})  # no key configured -> no imagery

    assert response.status_code == 502 and "GOOGLE_MAPS_API_KEY" in response.json()["detail"]


def test_request_overrides_reach_the_detector(monkeypatch, tmp_path):
    monkeypatch.setenv("OBSTACLE_MODEL_DIR", str(tmp_path))
    (tmp_path / "a.pt").write_bytes(b"x")
    seen = {}

    def _detect(self, boundary, frame=None, settings=None):
        seen["overlap"], seen["conf"] = settings.roof_overlap_min, settings.model_conf
        return DetectionResult("ok")

    monkeypatch.setattr(Ensemble, "detect", _detect)
    _client().post("/detect", json={"boundary": _ROOF, "roof_overlap_min": 0.6, "model_conf": 0.4})

    assert seen == {"overlap": 0.6, "conf": 0.4}


def test_reload_picks_up_weights_copied_in_after_startup(monkeypatch, tmp_path):
    monkeypatch.setenv("OBSTACLE_MODEL_DIR", str(tmp_path))
    monkeypatch.setattr(Ensemble, "warm_up", lambda self: None)  # nothing real to load

    assert _client().post("/reload").status_code == 503  # empty folder

    (tmp_path / "a.pt").write_bytes(b"x")
    first = _client().post("/reload").json()
    assert first == {"ok": True, "models": ["a.pt"]}

    (tmp_path / "b.pt").write_bytes(b"x")  # a retrained model arrives
    assert _client().post("/reload").json()["models"] == ["a.pt", "b.pt"]
