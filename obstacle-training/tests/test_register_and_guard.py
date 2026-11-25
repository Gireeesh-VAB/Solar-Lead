import json

import pytest

import frames
import register
from train import should_install

_BIG = b"w" * 1_100_000  # a stand-in for a real weights file (the install check wants > 1 MB)


def _check(found, labels=5, extra=0):
    return {"images": 3, "labels": labels, "found": found, "extra": extra, "conf": 0.25}


# --- the install guard ---------------------------------------------------------------------------------------------------------------------


def test_a_model_that_improved_or_held_its_ground_is_installed():
    assert should_install(_check(4), _check(2), positives=5) == (True, "ok")
    assert should_install(_check(3), _check(3), positives=5)[0] is True


def test_a_model_that_learned_nothing_is_never_installed():
    ok, why = should_install(_check(0), _check(0), positives=5)
    assert ok is False and "none of the confirmed obstacles" in why


def test_a_model_worse_than_the_one_it_started_from_is_never_installed():
    ok, why = should_install(_check(2), _check(4), positives=5)
    assert ok is False and "fewer obstacles" in why


def test_nothing_is_installed_without_confirmed_obstacles():
    assert should_install(_check(0, labels=0), _check(0, labels=0), positives=0)[0] is False


# --- installing ----------------------------------------------------------------------------------------------------------------------------


def test_install_backs_up_the_live_model_replaces_it_and_writes_the_ledger(tmp_path):
    live = tmp_path / "weights" / "obstacle_combined_v2.pt"
    live.parent.mkdir()
    live.write_bytes(b"old" * 400_000)
    base = tmp_path / "weights" / "_base" / "obstacle_combined_v2.base.pt"
    base.parent.mkdir()
    base.write_bytes(b"base" * 300_000)
    candidate = tmp_path / "work" / "obstacle_combined_v2.pt"
    candidate.parent.mkdir()
    candidate.write_bytes(_BIG)
    ledger = tmp_path / "runs.jsonl"

    result = register.install(candidate, live, base, {"positives": 4}, ledger)

    assert live.read_bytes() == _BIG  # the live model is the new one
    assert result["backup"].read_bytes() == b"old" * 400_000  # ... and the old one is kept, byte for byte
    assert result["backup"].parent.name == "_backup"
    assert not (live.parent / "obstacle_combined_v2.pt.new").exists()  # no half-written staging file left behind
    assert base.read_bytes() == b"base" * 300_000  # the frozen base is untouched
    entry = json.loads(ledger.read_text().splitlines()[0])
    assert entry["positives"] == 4 and entry["backup"] == str(result["backup"]) and entry["weights_sha"] != entry["backup_sha"]


def test_a_truncated_candidate_is_refused_and_the_live_model_is_left_alone(tmp_path):
    live = tmp_path / "live.pt"
    live.write_bytes(b"old" * 400_000)
    bad = tmp_path / "cand.pt"
    bad.write_bytes(b"tiny")

    with pytest.raises(SystemExit, match="incomplete"):
        register.install(bad, live, tmp_path / "base.pt", {}, tmp_path / "runs.jsonl")
    assert live.read_bytes() == b"old" * 400_000


def test_the_base_is_created_once_from_the_live_model_and_never_overwritten(tmp_path):
    live = tmp_path / "live.pt"
    live.write_bytes(b"first")
    base = tmp_path / "_base" / "base.pt"

    register.ensure_base(live, base)
    live.write_bytes(b"second")  # the live model changes later (a retrain)
    register.ensure_base(live, base)

    assert base.read_bytes() == b"first"


def test_reloading_the_service_never_raises():
    assert "restart obstacle-service" in register.reload_service("")
    assert "could not reach" in register.reload_service("http://127.0.0.1:1")  # nothing listens there


# --- frames ---------------------------------------------------------------------------------------------------------------------------------


def test_a_frame_is_downloaded_once_cached_and_refreshed_when_the_outline_changes(monkeypatch):
    import cv2
    import numpy as np
    from affine import Affine

    from obstacle_service import satellite_frame

    calls = []
    png = cv2.imencode(".png", np.full((40, 50, 3), 90, np.uint8))[1].tobytes()

    def fake_fetch(boundary, key, max_zoom=19, crop_margin=0.3):
        calls.append(key)
        return satellite_frame.Frame(png_bytes=png, transform=Affine(0.5, 0, 100, 0, -0.5, 200), width=50, height=40, epsg=3857)

    monkeypatch.setattr(satellite_frame, "fetch_roof_frame", fake_fetch)
    monkeypatch.setattr(frames, "maps_key", lambda: "test-key")
    site = "33333333-3333-4333-8333-333333333333"
    boundary = {"type": "Polygon", "coordinates": [[[78, 17], [78.001, 17], [78.001, 17.001], [78, 17]]]}

    first = frames.get_frame(site, boundary)
    again = frames.get_frame(site, boundary)
    assert len(calls) == 1 and first.image.shape == (40, 50, 3) and tuple(again.transform)[:6] == tuple(first.transform)[:6]

    moved = {**boundary, "coordinates": [[[78, 17], [78.002, 17], [78.002, 17.002], [78, 17]]]}
    frames.get_frame(site, moved)
    assert len(calls) == 2  # the outline changed, so the old picture no longer fits


def test_no_download_and_no_cache_means_no_frame_and_no_key_means_no_download(monkeypatch):
    site = "44444444-4444-4444-8444-444444444444"
    boundary = {"type": "Polygon", "coordinates": [[[78, 17], [78.001, 17], [78.001, 17.001], [78, 17]]]}
    assert frames.get_frame(site, boundary, allow_download=False) is None

    monkeypatch.setattr(frames, "maps_key", lambda: "")
    assert frames.get_frame(site, boundary) is None


def test_a_site_id_that_is_not_a_uuid_is_refused_before_it_can_become_a_path():
    with pytest.raises(ValueError):
        frames.cached_frame("..\\..\\evil", {})
