import pytest
from conftest import SIZE, TRANSFORM, square

import export_dataset
import frames
from export_dataset import export, polygon_to_pixels, to_yolo_line

SITE_A = "11111111-1111-4111-8111-111111111111"
SITE_B = "22222222-2222-4222-8222-222222222222"
_BOUNDARY = square(10, 10, 180)


def _sites():
    return [
        {  # two confirmed obstacles and one ignored false alarm
            "id": SITE_A, "boundary": _BOUNDARY,
            "candidates": [
                {"id": "c1", "ordinal": 1, "status": "confirmed", "polygon": square(20, 20, 30)},
                {"id": "c2", "ordinal": 2, "status": "confirmed", "polygon": square(100, 100, 40)},
                {"id": "c3", "ordinal": 3, "status": "ignored", "polygon": square(150, 30, 20)},
            ],
        },
        {  # only a false alarm: a pure background picture
            "id": SITE_B, "boundary": _BOUNDARY,
            "candidates": [{"id": "c4", "ordinal": 1, "status": "ignored", "polygon": square(60, 60, 30)}],
        },
    ]


@pytest.fixture
def patched(monkeypatch, frame):
    monkeypatch.setattr(export_dataset, "fetch_reviewed_sites", _sites)
    monkeypatch.setattr(frames, "get_frame", lambda site_id, boundary, allow_download=True: frame)


def test_polygon_pixels_round_trip_through_the_frames_transform():
    pts = polygon_to_pixels(square(20, 30, 40), TRANSFORM, SIZE, SIZE)

    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    assert min(xs) == pytest.approx(20, abs=0.2) and max(xs) == pytest.approx(60, abs=0.2)
    assert min(ys) == pytest.approx(30, abs=0.2) and max(ys) == pytest.approx(70, abs=0.2)


def test_an_outline_poking_out_of_the_picture_is_clipped_and_one_wholly_outside_is_dropped():
    clipped = polygon_to_pixels(square(170, 170, 60), TRANSFORM, SIZE, SIZE)
    assert max(p[0] for p in clipped) <= SIZE and max(p[1] for p in clipped) <= SIZE
    assert polygon_to_pixels(square(500, 500, 30), TRANSFORM, SIZE, SIZE) is None
    assert polygon_to_pixels(square(50, 50, 1), TRANSFORM, SIZE, SIZE) is None  # a 1 px speck is noise
    assert polygon_to_pixels({"type": "Polygon", "coordinates": []}, TRANSFORM, SIZE, SIZE) is None


def test_yolo_line_is_class_zero_with_coordinates_scaled_to_0_1():
    line = to_yolo_line([(0, 0), (100, 0), (100, 50), (0, 50), (0, 0)], 200, 100)
    parts = line.split()

    assert parts[0] == "0" and len(parts) == 1 + 2 * 4  # the repeated closing point is dropped
    assert [float(v) for v in parts[1:3]] == [0.0, 0.0] and [float(v) for v in parts[3:5]] == [0.5, 0.0]
    assert to_yolo_line([(0, 0), (1, 1)], 10, 10) is None


def test_export_writes_labels_for_confirmed_and_background_for_ignored(patched, tmp_path):
    out = tmp_path / "ds"
    r = export(out, repeat=2)

    assert r["positives"] == 2
    assert {u["id"]: (u["confirmed"], u["ignored"]) for u in r["sites"]} == {SITE_A: (2, 1), SITE_B: (0, 1)}
    label_a = (out / "labels" / "train" / f"{SITE_A}.txt").read_text().splitlines()
    assert len(label_a) == 2 and all(line.startswith("0 ") for line in label_a)  # the ignored one is NOT a label
    assert (out / "labels" / "train" / f"{SITE_B}.txt").read_text() == ""  # background picture: empty label file
    assert sorted(p.name for p in (out / "images" / "train").iterdir()) == sorted(
        [f"{SITE_A}.png", f"{SITE_A}_r1.png", f"{SITE_B}.png", f"{SITE_B}_r1.png"]
    )  # repeat copies
    assert sorted(p.name for p in (out / "images" / "val").iterdir()) == sorted([f"{SITE_A}.png", f"{SITE_B}.png"])  # one check copy each
    assert "train: images/train" in (out / "data.yaml").read_text()


def test_export_draws_a_preview_per_roof(patched, tmp_path):
    export(tmp_path / "ds", repeat=1)
    from config import PREVIEWS_DIR

    assert (PREVIEWS_DIR / f"{SITE_A}.png").is_file() and (PREVIEWS_DIR / f"{SITE_B}.png").is_file()


def test_export_refuses_when_there_is_no_confirmed_obstacle_to_learn_from(monkeypatch, frame, tmp_path):
    only_ignored = [{"id": SITE_B, "boundary": _BOUNDARY, "candidates": [{"id": "c", "ordinal": 1, "status": "ignored", "polygon": square(60, 60, 30)}]}]
    monkeypatch.setattr(export_dataset, "fetch_reviewed_sites", lambda: only_ignored)
    monkeypatch.setattr(frames, "get_frame", lambda *a, **k: frame)

    with pytest.raises(SystemExit, match="Confirm at least one real obstacle"):
        export(tmp_path / "ds")


def test_a_roof_without_a_frame_is_skipped_and_the_rest_still_train(monkeypatch, frame, tmp_path):
    monkeypatch.setattr(export_dataset, "fetch_reviewed_sites", _sites)
    monkeypatch.setattr(frames, "get_frame", lambda site_id, boundary, allow_download=True: None if site_id == SITE_B else frame)

    r = export(tmp_path / "ds", repeat=1)

    assert [u["id"] for u in r["sites"]] == [SITE_A] and r["skipped"][0]["id"] == SITE_B


def test_all_frames_missing_or_no_reviews_stop_with_a_clear_message(monkeypatch, tmp_path):
    monkeypatch.setattr(export_dataset, "fetch_reviewed_sites", lambda: [])
    with pytest.raises(SystemExit, match="No reviewed detections yet"):
        export(tmp_path / "ds")

    monkeypatch.setattr(export_dataset, "fetch_reviewed_sites", _sites)
    monkeypatch.setattr(frames, "get_frame", lambda *a, **k: None)
    with pytest.raises(SystemExit, match="satellite frame"):
        export(tmp_path / "ds")


def test_the_database_helper_refuses_anything_that_is_not_a_read():
    import db

    for sql in ("DELETE FROM obstacle_candidates", "update sites set name='x'", "DROP TABLE sites", "INSERT INTO sites VALUES (1)"):
        with pytest.raises(ValueError, match="only accepts SELECT"):
            db.run_sql(sql)
