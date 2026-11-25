import pytest

from obstacle_service import ensemble as ensemble_module


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    """No real key, no real models, no leftover shared ensemble: every test starts clean."""
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_SOLAR_API_KEY", raising=False)
    monkeypatch.setenv("OBSTACLE_MODEL_DIR", str(tmp_path / "no-models"))
    ensemble_module._ENSEMBLES.clear()
    yield
    ensemble_module._ENSEMBLES.clear()
