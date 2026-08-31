"""Manual live smoke test for §9.11 Vision Refinement — NOT part of the
automated pytest suite (no `test_` prefix, not discovered by pytest).

Makes real calls: Google Solar API Data Layers, then GPT-4 Vision.
Costs real money/quota on both. Run deliberately, not in CI.

Requires GOOGLE_SOLAR_API_KEY and OPENAI_API_KEY in solar-fitness/.env.

Usage:
    uv run python -m solarfit.manual_smoke_test_vision
    uv run python -m solarfit.manual_smoke_test_vision --lat 17.3850 --lng 78.4867
"""

import argparse
import json
import sys

from solarfit.config import get_settings
from solarfit.providers.vision import crop_to_boundary, fetch_rgb_imagery, refine_with_vision_model


def _placeholder_boundary(lat: float, lng: float, half_side_m: float = 10.0) -> dict:
    """A small square around (lat, lng) — NOT real roof geometry.
    Person 1's GEO-04 (Google Solar API building insights) is what
    produces an actual boundary; that isn't built yet, so this script
    stands in with an approximate square just to exercise the VIS
    pipeline end to end against real imagery."""
    # ~1 degree latitude ≈ 111,320 m; longitude scales by cos(latitude).
    import math

    dlat = half_side_m / 111_320
    dlng = half_side_m / (111_320 * math.cos(math.radians(lat)))
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [lng - dlng, lat - dlat],
                [lng + dlng, lat - dlat],
                [lng + dlng, lat + dlat],
                [lng - dlng, lat + dlat],
                [lng - dlng, lat - dlat],
            ]
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lat", type=float, default=17.3850, help="Latitude (default: Hyderabad reference point)")
    parser.add_argument("--lng", type=float, default=78.4867, help="Longitude")
    args = parser.parse_args()

    settings = get_settings()
    missing = [
        name
        for name, value in [
            ("GOOGLE_SOLAR_API_KEY", settings.google_solar_api_key),
            ("OPENAI_API_KEY", settings.openai_api_key),
        ]
        if not value
    ]
    if missing:
        print(f"Missing from solar-fitness/.env: {', '.join(missing)}", file=sys.stderr)
        return 1

    boundary = _placeholder_boundary(args.lat, args.lng)
    print(f"1/3 Fetching real Solar API Data Layers imagery for ({args.lat}, {args.lng})...")
    imagery = fetch_rgb_imagery(args.lat, args.lng)
    print(f"    got {len(imagery):,} bytes of GeoTIFF")

    print("2/3 Cropping to the placeholder boundary via rasterio/GDAL...")
    cropped = crop_to_boundary(imagery, boundary)
    print(f"    got {len(cropped.png_bytes):,} bytes of PNG ({cropped.width}x{cropped.height})")

    print("3/3 Calling GPT-4 Vision for refinement...")
    result = refine_with_vision_model(cropped, boundary)

    print("\n--- VisionRefinement result ---")
    print(json.dumps(result.model_dump(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
