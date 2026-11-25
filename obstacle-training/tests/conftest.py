import numpy as np
import pytest
from affine import Affine
from pyproj import Transformer

import config

_TO_MERC = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
_FROM_MERC = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)

SIZE = 200  # a 200 x 200 px synthetic frame, 0.5 m per pixel, centred on a roof in Hyderabad
_CX, _CY = _TO_MERC.transform(78.4, 17.4)
TRANSFORM = Affine(0.5, 0, _CX - SIZE / 2 * 0.5, 0, -0.5, _CY + SIZE / 2 * 0.5)


def px_to_lnglat(col: float, row: float) -> list[float]:
    x, y = TRANSFORM * (col, row)
    lng, lat = _FROM_MERC.transform(x, y)
    return [lng, lat]


def square(col0: float, row0: float, side: float) -> dict:
    """A GeoJSON polygon (lng/lat) covering the given pixel square of the synthetic frame."""
    ring = [px_to_lnglat(c, r) for c, r in ((col0, row0), (col0 + side, row0), (col0 + side, row0 + side), (col0, row0 + side), (col0, row0))]
    return {"type": "Polygon", "coordinates": [ring]}


@pytest.fixture(autouse=True)
def _tmp_dirs(monkeypatch, tmp_path):
    """Every folder the pipeline writes to is a temp folder; nothing real is touched."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "FRAMES_DIR", tmp_path / "data" / "frames")
    monkeypatch.setattr(config, "PREVIEWS_DIR", tmp_path / "data" / "previews")
    monkeypatch.setattr(config, "WORK_DIR", tmp_path / "work")
    monkeypatch.setattr(config, "LEDGER", tmp_path / "runs.jsonl")
    monkeypatch.setattr(config, "APP_ENV_FILE", tmp_path / "no-app.env")


@pytest.fixture
def frame():
    import frames

    return frames.TrainingFrame(np.full((SIZE, SIZE, 3), 120, np.uint8), TRANSFORM, 3857)
