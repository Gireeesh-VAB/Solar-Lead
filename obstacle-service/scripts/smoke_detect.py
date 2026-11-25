"""Call a RUNNING obstacle-service on one roof and print what came back and where detections were lost.

    python scripts/smoke_detect.py roof.json                  # roof.json = a GeoJSON Polygon (lng/lat), or a Feature with one
    python scripts/smoke_detect.py roof.json --url http://127.0.0.1:8200 --overlap 0.5

Uses only the standard library, so it runs in any Python.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("roof", help="JSON file: a GeoJSON Polygon (or Feature) in lng/lat")
    ap.add_argument("--url", default="http://127.0.0.1:8200")
    ap.add_argument("--overlap", type=float, help="override roof_overlap_min for this call")
    ap.add_argument("--conf", type=float, help="override the per-model confidence floor for this call")
    a = ap.parse_args()

    with open(a.roof, encoding="utf-8") as f:
        boundary = json.load(f)
    if boundary.get("type") == "Feature":
        boundary = boundary["geometry"]
    body = {"boundary": boundary}
    if a.overlap is not None:
        body["roof_overlap_min"] = a.overlap
    if a.conf is not None:
        body["model_conf"] = a.conf

    req = urllib.request.Request(f"{a.url}/detect", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            out = json.load(resp)
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.read().decode()[:400]}")
        return 1
    except OSError as exc:
        print(f"cannot reach {a.url}: {exc}")
        return 1

    s = out["stats"]
    print(f"status: {out['status']}   frame: {s.get('frame_source')} {s.get('frame_px')}")
    print(f"raw detections per model: {s.get('raw_per_model')}")
    print(f"after merge: {s.get('after_merge')}  ->  dropped off-roof: {s.get('dropped_off_roof')}, implausible: {s.get('dropped_implausible')}  ->  returned: {s.get('returned')}")
    for i, o in enumerate(out["obstacles"], 1):
        print(f"  #{i}: confidence {o['confidence']:.2f}, seen by {o['votes']} model(s), {o['area_m2']} m2")
    return 0


if __name__ == "__main__":
    sys.exit(main())
