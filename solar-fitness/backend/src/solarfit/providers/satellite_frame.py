"""The picture the obstacle models are shown.

The three YOLO obstacle models were trained on *soft, tightly framed
Google satellite screenshots* (VAB-Energies obstacle-service/app.py,
backend-src aiObstacleDetection.service.ts). Shown anything else they get
much less sure of themselves: on the same roof the Solar API aerial raster
(sharp, 0.1 m/pixel, masked to black outside the outline) gave weak, partial
detections where a Static Maps satellite tile gave confident ones.

So the ensemble is fed the way the model was trained:

  1. a Google Static Maps satellite tile centred on the roof, 640 px, at a
     zoom that fits the roof with room to spare - capped at 19, because a
     sharper (20-21) view makes the models mistake roof texture for
     obstacles and break solar arrays into fragments;
  2. cropped to the roof's bounding box plus a margin on each side (real
     surroundings are kept, nothing is blacked out), then enlarged so the
     roof fills the frame the way it did in the training screenshots.

The returned CroppedImagery carries its own pixel -> EPSG:3857 transform, so
detections convert back to lat/lng through the same code path as any other
imagery (yolo_obstacle_detector._pixel_polygon_to_geojson).

Never raises: a missing key, an HTTP error or an undecodable image returns
None and the caller falls back to the Solar API crop.
"""

from __future__ import annotations

import logging
import math
from io import BytesIO

import httpx
from affine import Affine
from PIL import Image
from pyproj import Transformer
from rasterio.crs import CRS
from shapely.geometry import shape
from shapely.ops import transform as shapely_transform

from solarfit.providers.vision import CroppedImagery

logger = logging.getLogger(__name__)

__all__ = ["fetch_roof_frame", "frame_for_roof", "pick_zoom"]

STATIC_MAP_URL = "https://maps.googleapis.com/maps/api/staticmap"
IMAGE_SIZE_PX = 640
#: Metres per pixel at zoom 0 on the equator (and Web-Mercator units per pixel).
_MPP_ZOOM0 = 156543.03392
_TIMEOUT_S = 15.0
_MIN_ZOOM = 15
_HARD_MAX_ZOOM = 21
#: Never enlarge a crop more than this (it would only magnify blur).
_MAX_ENLARGE = 4.0
#: An enlargement this small gains nothing - use the whole tile instead.
_MIN_ENLARGE = 1.2

_TO_MERCATOR = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)


def pick_zoom(center_lat: float, desired_width_m: float, *, max_zoom: int = 19) -> int:
    """Integer zoom whose 640 px tile covers about `desired_width_m`, kept
    within [15, max_zoom]. Same rule as the VAB backend's pickZoomForWidth
    (+ its 19 cap)."""
    mpp0 = _MPP_ZOOM0 * math.cos(math.radians(center_lat))
    desired_mpp = max(desired_width_m, 1.0) / IMAGE_SIZE_PX
    zoom = round(math.log2(mpp0 / desired_mpp))
    return max(_MIN_ZOOM, min(_HARD_MAX_ZOOM, zoom, max_zoom))


def frame_for_roof(boundary: dict, *, max_zoom: int = 19) -> tuple[float, float, int]:
    """(centre lat, centre lng, zoom) of the tile to request for `boundary`."""
    geom = shape(boundary)
    minx, miny, maxx, maxy = geom.bounds
    lat, lng = (miny + maxy) / 2, (minx + maxx) / 2
    span_lat_m = (maxy - miny) * 111_320
    span_lng_m = (maxx - minx) * 111_320 * math.cos(math.radians(lat))
    desired = max(span_lat_m, span_lng_m, 15.0) * 1.6
    return lat, lng, pick_zoom(lat, desired, max_zoom=max_zoom)


def _download_tile(lat: float, lng: float, zoom: int, api_key: str) -> Image.Image | None:
    try:
        response = httpx.get(
            STATIC_MAP_URL,
            params={
                "center": f"{lat},{lng}",
                "zoom": zoom,
                "size": f"{IMAGE_SIZE_PX}x{IMAGE_SIZE_PX}",
                "maptype": "satellite",
                "key": api_key,
            },
            timeout=_TIMEOUT_S,
        )
        content_type = response.headers.get("content-type", "")
        if response.status_code != 200 or not content_type.startswith("image/"):
            logger.warning(
                "Static Maps returned %s (%s) - is 'Maps Static API' enabled for the key?",
                response.status_code,
                content_type,
            )
            return None
        return Image.open(BytesIO(response.content)).convert("RGB")
    except Exception as exc:  # noqa: BLE001 - absence is data, not an exception
        logger.warning("Static Maps request failed: %s", exc)
        return None


def fetch_roof_frame(
    boundary: dict, api_key: str, *, max_zoom: int = 19, crop_margin: float = 0.3
) -> CroppedImagery | None:
    """The satellite view of `boundary` that the obstacle models were trained
    on, or None when it cannot be had. See the module docstring."""
    if not api_key or not boundary:
        return None
    try:
        lat, lng, zoom = frame_for_roof(boundary, max_zoom=max_zoom)
    except Exception:  # a malformed boundary just means no frame
        logger.warning("Satellite frame: unusable roof boundary", exc_info=True)
        return None

    tile = _download_tile(lat, lng, zoom, api_key)
    if tile is None:
        return None

    res = _MPP_ZOOM0 / (2**zoom)  # Web-Mercator metres per tile pixel
    cx, cy = _TO_MERCATOR.transform(lng, lat)
    half = IMAGE_SIZE_PX / 2

    # The roof outline in tile pixels.
    roof_m = shapely_transform(_TO_MERCATOR.transform, shape(boundary))
    minx, miny, maxx, maxy = roof_m.bounds
    px0, py1 = half + (minx - cx) / res, half - (miny - cy) / res
    px1, py0 = half + (maxx - cx) / res, half - (maxy - cy) / res
    mx, my = (px1 - px0) * crop_margin, (py1 - py0) * crop_margin
    x0, y0 = max(0, int(px0 - mx)), max(0, int(py0 - my))
    x1, y1 = min(IMAGE_SIZE_PX, math.ceil(px1 + mx)), min(IMAGE_SIZE_PX, math.ceil(py1 + my))

    scale = 1.0
    if crop_margin > 0 and x1 - x0 >= 32 and y1 - y0 >= 32:
        wanted = min(_MAX_ENLARGE, IMAGE_SIZE_PX / max(x1 - x0, y1 - y0))
        if wanted > _MIN_ENLARGE:
            scale = wanted
    if scale == 1.0:
        x0 = y0 = 0
        view = tile
    else:
        view = tile.crop((x0, y0, x1, y1))
        view = view.resize(
            (max(1, round(view.width * scale)), max(1, round(view.height * scale))),
            Image.Resampling.LANCZOS,
        )

    out = BytesIO()
    view.save(out, format="PNG")
    # view pixel (c, r) -> tile pixel (c/scale + x0, r/scale + y0) -> EPSG:3857.
    transform = Affine(
        res / scale, 0.0, cx + (x0 - half) * res,
        0.0, -res / scale, cy - (y0 - half) * res,
    )
    return CroppedImagery(
        png_bytes=out.getvalue(),
        transform=transform,
        crs=CRS.from_epsg(3857),
        width=view.width,
        height=view.height,
    )
