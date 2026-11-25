"""Step 1: turn what customers did with detections into a YOLO-seg dataset.

Where the labels come from (obstacle_candidates, read-only):
  * confirmed  -> an obstacle (its outline is the customer's corrected one if they used Edit)      -> a label
  * ignored    -> a false alarm: the model drew something that is not an obstacle                  -> NO label (background), so training
                  teaches it that this is not one; a roof with only ignored detections is a pure "nothing here" example
  * pending    -> not reviewed yet                                                                  -> skipped
  Obstacles the customer DREW because the scan missed them are confirmed candidates too (source customer_drawn), so they are labels.
  Customer-TAPPED obstacles are NOT used: a tap becomes a fixed-size square, not a real outline.

The training picture is the same frame the service builds at detection time (frames.py); outlines are converted from lng/lat to its pixels.
Each roof is written `repeat` times per epoch (random flips/colour make the copies differ) plus once as the check copy.
Run alone:  python export_dataset.py --out work/test_export
"""
import argparse
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np
from pyproj import Transformer
from shapely.geometry import Polygon, box

import config
import frames
from db import query_json

_TO_MERCATOR = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
#: Outlines smaller than this many pixels in area are noise.
_MIN_PX_AREA = 4.0

_REVIEWED_SQL = """
SELECT jsonb_agg(t) FROM (
  SELECT s.id::text AS id,
         ST_AsGeoJSON(s.boundary::geometry)::jsonb AS boundary,
         (SELECT jsonb_agg(jsonb_build_object('id', c.id, 'ordinal', c.ordinal, 'polygon', c.polygon, 'status', c.status) ORDER BY c.ordinal)
            FROM obstacle_candidates c WHERE c.site_id = s.id AND c.status IN ('confirmed', 'ignored')) AS candidates
    FROM sites s
   WHERE s.boundary IS NOT NULL
     AND EXISTS (SELECT 1 FROM obstacle_candidates c WHERE c.site_id = s.id AND c.status IN ('confirmed', 'ignored'))
   ORDER BY s.updated_at DESC
) t"""


def fetch_reviewed_sites() -> list[dict]:
    """Every roof with at least one reviewed (confirmed or ignored) detection: {id, boundary, candidates[{id, ordinal, polygon, status}]}."""
    return query_json(_REVIEWED_SQL) or []


def polygon_to_pixels(geojson: dict, transform, width: int, height: int) -> list[tuple[float, float]] | None:
    """A lng/lat GeoJSON polygon -> pixel outline in the frame (clipped to the picture); None if nothing usable is left."""
    try:
        ring = geojson["coordinates"][0]
        inverse = ~transform
        pixels = [tuple(inverse * _TO_MERCATOR.transform(lng, lat)) for lng, lat in ring]
        poly = Polygon(pixels).buffer(0).intersection(box(0, 0, width, height))
    except Exception:  # noqa: BLE001 - one malformed outline must not stop a run
        return None
    if poly.is_empty:
        return None
    if poly.geom_type != "Polygon":
        parts = [g for g in getattr(poly, "geoms", []) if g.geom_type == "Polygon"]
        if not parts:
            return None
        poly = max(parts, key=lambda g: g.area)
    if poly.area < _MIN_PX_AREA:
        return None
    return [(float(x), float(y)) for x, y in poly.exterior.coords]


def to_yolo_line(polygon_px: list, width: int, height: int) -> str | None:
    """One YOLO-seg line (class 0 = obstacle) with the polygon scaled to 0-1; None if it is not a real polygon."""
    pts = [(float(x), float(y)) for x, y in polygon_px]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        return None
    coords: list[str] = []
    for x, y in pts:
        coords += [f"{min(max(x / width, 0.0), 1.0):.6f}", f"{min(max(y / height, 0.0), 1.0):.6f}"]
    return " ".join(["0"] + coords)


def draw_preview(image: np.ndarray, confirmed: list, ignored: list, path: Path) -> None:
    """The roof with green outlines (confirmed obstacles) and red outlines (ignored false alarms), for the trainer page."""
    canvas = image.copy()
    for pts, colour in ((ignored, (0, 0, 255)), (confirmed, (0, 200, 0))):
        for poly in pts:
            cv2.polylines(canvas, [np.round(np.array(poly)).astype(np.int32)], True, colour, 2)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), canvas)


def export(out_dir: Path, repeat: int = config.REPEAT, *, allow_download: bool = True) -> dict:
    sites = fetch_reviewed_sites()
    if not sites:
        raise SystemExit("No reviewed detections yet: nothing in obstacle_candidates is confirmed or ignored. Review some scans in the app first.")

    if out_dir.exists():
        shutil.rmtree(out_dir)
    for split in ("train", "val"):
        (out_dir / "images" / split).mkdir(parents=True)
        (out_dir / "labels" / split).mkdir(parents=True)

    used: list[dict] = []
    skipped: list[dict] = []
    for s in sites:
        frame = frames.get_frame(s["id"], s["boundary"], allow_download=allow_download)
        if frame is None:
            skipped.append({"id": s["id"], "why": "no satellite frame (no Maps key, or Static Maps not enabled / unreachable)"})
            continue
        h, w = frame.image.shape[:2]
        lines: list[str] = []
        confirmed_px: list = []
        ignored_px: list = []
        for c in s["candidates"]:
            pts = polygon_to_pixels(c["polygon"], frame.transform, w, h)
            if pts is None:
                continue
            if c["status"] == "confirmed":
                line = to_yolo_line(pts, w, h)
                if line:
                    lines.append(line)
                    confirmed_px.append(pts)
            else:
                ignored_px.append(pts)
        draw_preview(frame.image, confirmed_px, ignored_px, config.PREVIEWS_DIR / f"{s['id']}.png")
        text = ("\n".join(lines) + "\n") if lines else ""  # an empty label file = a background picture
        for split in ("train", "val"):
            copies = max(1, int(repeat)) if split == "train" else 1
            for k in range(copies):
                stem = s["id"] if k == 0 else f"{s['id']}_r{k}"
                cv2.imwrite(str(out_dir / "images" / split / f"{stem}.png"), frame.image)
                (out_dir / "labels" / split / f"{stem}.txt").write_text(text, encoding="utf-8")
        used.append({"id": s["id"], "confirmed": len(lines), "ignored": len(ignored_px)})

    if not used:
        raise SystemExit(f"None of the {len(sites)} reviewed roof(s) has a satellite frame: {skipped[0]['why']}")
    positives = sum(u["confirmed"] for u in used)
    if positives == 0:
        raise SystemExit(
            "Only ignored (false-alarm) detections so far, so there is no obstacle outline to learn from yet. "
            "Confirm at least one real obstacle in the app, then train."
        )
    data_yaml = out_dir / "data.yaml"
    data_yaml.write_text(f"path: {out_dir.resolve().as_posix()}\ntrain: images/train\nval: images/val\nnames:\n  0: obstacle\n", encoding="utf-8")
    return {"data_yaml": data_yaml, "sites": used, "skipped": skipped, "positives": positives, "imgsz": config.IMGSZ}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--repeat", type=int, default=config.REPEAT)
    ap.add_argument("--no-download", action="store_true", help="use only frames already cached")
    a = ap.parse_args()
    r = export(a.out, a.repeat, allow_download=not a.no_download)
    print(f"exported {len(r['sites'])} roof(s), {r['positives']} confirmed obstacle(s) -> {r['data_yaml']}")
    for u in r["sites"]:
        print(f"  {u['id'][:8]}: {u['confirmed']} confirmed, {u['ignored']} ignored")
    for sk in r["skipped"]:
        print(f"  SKIPPED {sk['id'][:8]}: {sk['why']}")
    sys.exit(0)
