"""The detect() flow around the models, with the YOLO predictions faked - no weights, no network."""
from io import BytesIO

import pytest
from affine import Affine
from PIL import Image
from shapely.geometry import box

from obstacle_service import ensemble as ensemble_module
from obstacle_service.ensemble import Ensemble, get_ensemble
from obstacle_service.satellite_frame import Frame
from obstacle_service.settings import get_settings

# A 100 x 100 px frame in lng/lat (EPSG:4326): 1 px = 0.000002 deg (~0.22 m). The roof is the left half (x 0-50).
_FRAME = None
_ROOF = {"type": "Polygon", "coordinates": [[[78.0, 17.0], [78.0001, 17.0], [78.0001, 16.9998], [78.0, 16.9998], [78.0, 17.0]]]}


def _frame() -> Frame:
    out = BytesIO()
    Image.new("RGB", (100, 100), (90, 90, 90)).save(out, format="PNG")
    return Frame(png_bytes=out.getvalue(), transform=Affine(0.000002, 0, 78.0, 0, -0.000002, 17.0), width=100, height=100, epsg=4326)


def _ensemble_with(monkeypatch, per_model: list[list[tuple]]) -> Ensemble:
    """An ensemble of len(per_model) fake models; model i returns per_model[i] = [(polygon, confidence), ...]."""
    ens = Ensemble([ensemble_module.Path(f"m{i}.pt") for i in range(len(per_model))])
    monkeypatch.setattr(Ensemble, "_load", lambda self: list(range(len(per_model))))
    monkeypatch.setattr(Ensemble, "_predict_one", staticmethod(lambda model, image, s: per_model[model]))
    return ens


def test_no_models_reports_no_models():
    assert Ensemble([]).detect(_ROOF, frame=_frame()).status == "no_models"


def test_no_key_and_no_supplied_frame_reports_no_imagery(tmp_path):
    ens = Ensemble([tmp_path / "a.pt"])
    assert ens.detect(_ROOF).status == "no_imagery"


def test_an_undecodable_picture_degrades_instead_of_raising(tmp_path):
    ens = Ensemble([tmp_path / "a.pt"])
    bad = Frame(png_bytes=b"not a png", transform=Affine.identity(), width=1, height=1, epsg=4326)
    assert ens.detect(_ROOF, frame=bad).status == "bad_image"


def test_an_obstacle_on_the_roof_is_returned_with_its_votes_and_area(monkeypatch):
    on_roof = box(10, 10, 30, 30)  # inside x 0-50 -> on the roof
    ens = _ensemble_with(monkeypatch, [[(on_roof, 0.8)], [(box(11, 11, 30, 30), 0.6)], []])
    res = ens.detect(_ROOF, frame=_frame())

    assert res.status == "ok" and len(res.obstacles) == 1
    assert res.obstacles[0].votes == 2 and res.obstacles[0].confidence == pytest.approx(0.8)
    assert res.obstacles[0].area_m2 > 0
    assert res.stats["raw_per_model"] == {"m0.pt": 1, "m1.pt": 1, "m2.pt": 0}
    assert res.stats["after_merge"] == 1 and res.stats["returned"] == 1


def test_an_obstacle_on_a_neighbouring_building_is_dropped_and_counted(monkeypatch):
    # The frame covers 100 px (0.0002 deg) but the roof only 0.0001 deg: x 60-90 is off the roof.
    ens = _ensemble_with(monkeypatch, [[(box(60, 10, 90, 30), 0.9)], [], []])
    res = ens.detect(_ROOF, frame=_frame())

    assert res.obstacles == [] and res.stats["dropped_off_roof"] == 1


def test_the_roof_overlap_setting_decides_a_straddling_obstacle(monkeypatch):
    # 40% of this outline is on the roof (x 30-50 of 30-80)
    straddler = box(30, 10, 80, 30)
    ens = _ensemble_with(monkeypatch, [[(straddler, 0.9)], [], []])
    strict = ens.detect(_ROOF, frame=_frame(), settings=_replace(get_settings(), roof_overlap_min=0.5))
    loose = ens.detect(_ROOF, frame=_frame(), settings=_replace(get_settings(), roof_overlap_min=0.3))

    assert strict.obstacles == [] and len(loose.obstacles) == 1  # kept at 0.3, clipped to the roof
    from shapely.geometry import shape

    assert shape(_ROOF).covers(shape(loose.obstacles[0].polygon))


def _replace(settings, **changes):
    from dataclasses import replace

    return replace(settings, **changes)


def test_a_model_that_fails_to_run_is_skipped_and_the_others_still_vote(monkeypatch):
    ens = Ensemble([ensemble_module.Path("a.pt"), ensemble_module.Path("b.pt")])
    monkeypatch.setattr(Ensemble, "_load", lambda self: [0, 1])

    def _predict(model, image, s):
        if model == 0:
            raise RuntimeError("boom")
        return [(box(10, 10, 30, 30), 0.7)]

    monkeypatch.setattr(Ensemble, "_predict_one", staticmethod(_predict))
    res = ens.detect(_ROOF, frame=_frame())

    assert len(res.obstacles) == 1 and res.stats["raw_per_model"] == {"a.pt": -2, "b.pt": 1}


def test_missing_models_are_not_remembered(tmp_path, monkeypatch):
    """A service started before the .pt files were copied in must find them on the next call - "no models" used to be cached for the life of
    the process, which kept the detector off until a restart."""
    folder = tmp_path / "weights"
    folder.mkdir()
    monkeypatch.setenv("OBSTACLE_MODEL_DIR", str(folder))

    assert get_ensemble() is None  # nothing there yet
    (folder / "a.pt").write_bytes(b"x")  # weights arrive (not loaded until first use, so a stub file is enough)
    found = get_ensemble()
    assert found is not None and found.n_models == 1
    assert get_ensemble() is found  # a successful lookup IS reused
