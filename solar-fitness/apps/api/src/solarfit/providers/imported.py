"""Owner: Person 1 (Site & Geometry).

Implements GEO-05 (IMPORTED) of
Solar_Fitness_Engine_Development_Document_v1.1: GeoJSON/shapefile
upload with CRS detection and validation. Backs routers/imports.py's
bulk-import endpoint (API-07).

CRS detection, in order of trust
--------------------------------
1. An explicit `source_crs` passed by the caller — they know what they
   exported.
2. A GeoJSON `crs` member (pre-RFC-7946 files still carry one).
3. Coordinate-range inference: values inside +/-180 / +/-90 are almost
   certainly degrees, i.e. already EPSG:4326.

If none of those apply the file is REJECTED, not guessed at. A shapefile
whose .prj sidecar went missing is the classic source of a silently
wrong area — the numbers look plausible and nobody notices until a
customer disputes them. §17 is explicit that a wrong area must never
look like a right one, so an unknown CRS is an error, never a default.

Depends on: solarfit.providers.base (same track),
solarfit.providers.validation (same track).
"""

from __future__ import annotations

import json
import zipfile
from io import BytesIO
from typing import Any, ClassVar

from pyproj import CRS, Transformer
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shapely_transform

from solarfit.domain.site import Site
from solarfit.providers import base, validation
from solarfit.providers.validation import GeometryRejected

__all__ = [
    "ImportedFeature",
    "ImportedProvider",
    "detect_crs",
    "parse_geojson",
    "parse_shapefile_zip",
    "parse_upload",
    "resolve_imported",
]

WGS84 = "EPSG:4326"

# Coordinates outside this are definitely not degrees.
_LON_RANGE = (-180.0, 180.0)
_LAT_RANGE = (-90.0, 90.0)


class ImportedFeature:
    """One geometry lifted out of an upload, already in EPSG:4326."""

    __slots__ = ("boundary", "properties", "source_crs")

    def __init__(self, boundary: dict, properties: dict, source_crs: str):
        self.boundary = boundary
        self.properties = properties
        self.source_crs = source_crs

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"ImportedFeature(source_crs={self.source_crs!r}, props={len(self.properties)})"


class ImportedProvider:
    """GEO-05. Boundary lifted from an uploaded GeoJSON or shapefile."""

    id = "imported"
    applies_to: ClassVar[list[str]] = []  # every rooftop type

    def resolve(self, site: Site, params: dict) -> dict:
        return resolve_imported(site, params.get("upload", b""), params)


# --------------------------------------------------------------------- #
# CRS detection
# --------------------------------------------------------------------- #


def _looks_like_degrees(geom: BaseGeometry) -> bool:
    minx, miny, maxx, maxy = geom.bounds
    return (
        _LON_RANGE[0] <= minx <= _LON_RANGE[1]
        and _LON_RANGE[0] <= maxx <= _LON_RANGE[1]
        and _LAT_RANGE[0] <= miny <= _LAT_RANGE[1]
        and _LAT_RANGE[0] <= maxy <= _LAT_RANGE[1]
    )


def detect_crs(
    geom: BaseGeometry,
    *,
    declared: str | None = None,
    geojson_crs: dict | None = None,
) -> str:
    """GEO-05. Determine the CRS of an uploaded geometry, or raise.

    Never falls back to "probably 4326" for coordinates that are out of
    degree range — those are projected metres, and treating them as
    degrees produces an area wrong by many orders of magnitude.
    """
    if declared:
        try:
            return CRS.from_user_input(declared).to_string()
        except Exception as exc:
            raise GeometryRejected(f"unrecognised source_crs {declared!r}: {exc}") from exc

    if geojson_crs:
        # Legacy GeoJSON crs member: {"type": "name",
        #   "properties": {"name": "urn:ogc:def:crs:EPSG::32644"}}
        name = (geojson_crs.get("properties") or {}).get("name")
        if name:
            try:
                return CRS.from_user_input(name).to_string()
            except Exception as exc:
                raise GeometryRejected(f"unrecognised CRS in file: {name!r} ({exc})") from exc

    if _looks_like_degrees(geom):
        # RFC 7946 says a GeoJSON file with no crs member IS 4326, and the
        # coordinate range agrees. Safe.
        return WGS84

    raise GeometryRejected(
        "cannot determine the coordinate system of this upload — coordinates are "
        "outside the valid degree range, and no .prj / crs member / source_crs was "
        "supplied. Re-export with a .prj file or pass source_crs explicitly; "
        "guessing here would produce a silently wrong area."
    )


def _to_wgs84(geom: BaseGeometry, source_crs: str) -> BaseGeometry:
    if CRS.from_user_input(source_crs).to_epsg() == 4326:
        return geom
    to_wgs = Transformer.from_crs(source_crs, WGS84, always_xy=True).transform
    return shapely_transform(to_wgs, geom)


# --------------------------------------------------------------------- #
# parsers
# --------------------------------------------------------------------- #


def _features_from_geojson(doc: dict) -> list[tuple[dict, dict]]:
    """Return (geometry, properties) pairs for anything GeoJSON-shaped."""
    kind = doc.get("type")

    if kind == "FeatureCollection":
        return [
            (f.get("geometry"), f.get("properties") or {})
            for f in doc.get("features", [])
            if f.get("geometry")
        ]
    if kind == "Feature":
        return [(doc.get("geometry"), doc.get("properties") or {})] if doc.get("geometry") else []
    if kind in {"Polygon", "MultiPolygon", "GeometryCollection"}:
        return [(doc, {})]

    raise GeometryRejected(f"unsupported GeoJSON type {kind!r}")


def _explode_polygons(geom: BaseGeometry) -> list[BaseGeometry]:
    """A MultiPolygon import means several roofs, one per polygon."""
    if geom.geom_type == "Polygon":
        return [geom]
    if geom.geom_type in {"MultiPolygon", "GeometryCollection"}:
        return [g for g in geom.geoms if g.geom_type == "Polygon"]
    raise GeometryRejected(f"expected a Polygon, got {geom.geom_type}")


def parse_geojson(payload: bytes | str | dict, *, declared_crs: str | None = None) -> list[ImportedFeature]:
    """GEO-05. Parse GeoJSON into 4326 features."""
    if isinstance(payload, (bytes, bytearray)):
        try:
            doc = json.loads(payload.decode("utf-8"))
        except Exception as exc:
            raise GeometryRejected(f"upload is not valid UTF-8 JSON: {exc}") from exc
    elif isinstance(payload, str):
        try:
            doc = json.loads(payload)
        except Exception as exc:
            raise GeometryRejected(f"upload is not valid JSON: {exc}") from exc
    else:
        doc = payload

    if not isinstance(doc, dict):
        raise GeometryRejected("GeoJSON root must be an object")

    file_crs = doc.get("crs")
    out: list[ImportedFeature] = []

    for raw_geom, props in _features_from_geojson(doc):
        try:
            geom = shape(raw_geom)
        except Exception as exc:
            raise GeometryRejected(f"feature geometry is not parseable: {exc}") from exc

        crs = detect_crs(geom, declared=declared_crs, geojson_crs=file_crs)
        geom_4326 = _to_wgs84(geom, crs)

        for polygon in _explode_polygons(geom_4326):
            out.append(ImportedFeature(mapping(polygon), dict(props), crs))

    if not out:
        raise GeometryRejected("upload contained no polygon features")
    return out


def parse_shapefile_zip(payload: bytes, *, declared_crs: str | None = None) -> list[ImportedFeature]:
    """GEO-05. Parse a zipped shapefile into 4326 features.

    A shapefile is a set of sibling files; the CRS lives in the .prj. A
    zip with no .prj and no declared CRS is rejected rather than assumed
    — see the module docstring.
    """
    try:
        archive = zipfile.ZipFile(BytesIO(payload))
    except Exception as exc:
        raise GeometryRejected(f"upload is not a readable zip archive: {exc}") from exc

    names = archive.namelist()
    shp = next((n for n in names if n.lower().endswith(".shp")), None)
    if shp is None:
        raise GeometryRejected("zip contains no .shp file")

    prj = next((n for n in names if n.lower().endswith(".prj")), None)
    file_crs: str | None = declared_crs
    if file_crs is None and prj is not None:
        try:
            file_crs = CRS.from_wkt(archive.read(prj).decode("utf-8", "ignore")).to_string()
        except Exception as exc:
            raise GeometryRejected(f".prj file is present but unreadable: {exc}") from exc

    try:
        import fiona
    except ImportError as exc:  # pragma: no cover - depends on install
        raise GeometryRejected(
            "shapefile import needs the `fiona` package, which is not installed. "
            "Convert the shapefile to GeoJSON, or add fiona to the project."
        ) from exc

    out: list[ImportedFeature] = []
    with fiona.open(f"zip://{shp}", vfs=None, driver="ESRI Shapefile") as src:  # type: ignore[call-arg]
        for record in src:
            geom = shape(record["geometry"])
            crs = detect_crs(geom, declared=file_crs)
            geom_4326 = _to_wgs84(geom, crs)
            for polygon in _explode_polygons(geom_4326):
                out.append(ImportedFeature(mapping(polygon), dict(record.get("properties") or {}), crs))

    if not out:
        raise GeometryRejected("shapefile contained no polygon features")
    return out


def parse_upload(
    payload: bytes, *, filename: str | None = None, declared_crs: str | None = None
) -> list[ImportedFeature]:
    """Dispatch on file type. Zip -> shapefile, anything else -> GeoJSON."""
    if payload[:2] == b"PK" or (filename or "").lower().endswith(".zip"):
        return parse_shapefile_zip(payload, declared_crs=declared_crs)
    return parse_geojson(payload, declared_crs=declared_crs)


# --------------------------------------------------------------------- #
# provider entry point
# --------------------------------------------------------------------- #


def resolve_imported(site: Site, upload: bytes, params: dict[str, Any]) -> dict:
    """GEO-05. Resolve a single site's boundary from an upload.

    The upload may contain several polygons (bulk import goes through
    routers/imports.py instead); for a single site the caller either
    supplies a one-feature file or selects an index via
    `params["feature_index"]`.
    """
    if not upload:
        raise GeometryRejected("imported provider requires an upload")

    features = parse_upload(
        upload,
        filename=params.get("filename"),
        declared_crs=params.get("source_crs"),
    )

    index = int(params.get("feature_index", 0))
    if index >= len(features):
        raise GeometryRejected(
            f"upload has {len(features)} feature(s); feature_index {index} is out of range"
        )

    feature = features[index]
    # Same GEO-07 gate every other provider passes through.
    geom = validation.validate_boundary(feature.boundary, centroid=site.centroid)
    return mapping(geom)


base.register(ImportedProvider())
