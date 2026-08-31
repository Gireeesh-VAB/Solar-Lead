"""GEO-05 (IMPORTED) and GEO-06 (FIELD_MEASURED) — Person 1.

The CRS tests carry the weight here: a shapefile that lost its .prj is
the classic route to a silently wrong area, and §17 says a wrong area
must never look like a right one.
"""

import json

import pytest
from pyproj import Transformer
from shapely.geometry import box as shapely_box
from shapely.geometry import mapping
from shapely.ops import transform

from solarfit.providers import base, imported
from solarfit.providers.validation import GeometryRejected
from solarfit.repositories import sites as repo

LON, LAT = 78.4867, 17.3850
UTM44N = 32644


def _poly_4326(size: float = 0.0005) -> dict:
    return mapping(shapely_box(LON, LAT, LON + size, LAT + size))


def _poly_utm() -> dict:
    """The same roof, but in projected metres — coordinates far outside
    the degree range, exactly like a shapefile exported from QGIS."""
    to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:{UTM44N}", always_xy=True).transform
    return mapping(transform(to_utm, shapely_box(LON, LAT, LON + 0.0005, LAT + 0.0005)))


def _bounds(geojson: dict) -> tuple[float, float, float, float]:
    from shapely.geometry import shape

    return shape(geojson).bounds


def _feature_collection(*geoms: dict, crs: dict | None = None, props: dict | None = None) -> bytes:
    doc = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": g, "properties": props or {"name": f"Roof {i}"}}
            for i, g in enumerate(geoms, start=1)
        ],
    }
    if crs:
        doc["crs"] = crs
    return json.dumps(doc).encode("utf-8")


# --------------------------------------------------------------------- #
# GEO-05 — CRS detection
# --------------------------------------------------------------------- #


def test_degree_coordinates_are_accepted_as_4326():
    features = imported.parse_geojson(_feature_collection(_poly_4326()))
    assert len(features) == 1
    assert features[0].source_crs.endswith("4326")


def test_projected_coordinates_without_a_crs_are_rejected_not_guessed():
    """The whole point of GEO-05's CRS handling. UTM metres look like
    nothing at all if read as degrees, and the resulting area would be
    wrong by orders of magnitude — so refuse rather than assume."""
    with pytest.raises(GeometryRejected, match="cannot determine the coordinate system"):
        imported.parse_geojson(_feature_collection(_poly_utm()))


def test_projected_coordinates_are_accepted_with_a_declared_crs():
    features = imported.parse_geojson(
        _feature_collection(_poly_utm()), declared_crs=f"EPSG:{UTM44N}"
    )
    assert len(features) == 1
    # Reprojected back into degrees, landing where it started. Compare
    # bounds rather than a named vertex — the ring's starting corner is
    # not guaranteed to survive a projection round trip.
    assert _bounds(features[0].boundary) == pytest.approx(
        (LON, LAT, LON + 0.0005, LAT + 0.0005), abs=1e-6
    )


def test_legacy_geojson_crs_member_is_honoured():
    doc = _feature_collection(
        _poly_utm(),
        crs={"type": "name", "properties": {"name": f"urn:ogc:def:crs:EPSG::{UTM44N}"}},
    )
    features = imported.parse_geojson(doc)
    assert _bounds(features[0].boundary)[0] == pytest.approx(LON, abs=1e-6)


def test_declared_crs_beats_the_file_crs_member():
    """The caller knows what they exported; a stale crs member does not."""
    doc = _feature_collection(
        _poly_utm(), crs={"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::4326"}}
    )
    features = imported.parse_geojson(doc, declared_crs=f"EPSG:{UTM44N}")
    assert _bounds(features[0].boundary)[0] == pytest.approx(LON, abs=1e-6)


def test_unrecognised_declared_crs_is_rejected():
    with pytest.raises(GeometryRejected, match="unrecognised source_crs"):
        imported.parse_geojson(_feature_collection(_poly_4326()), declared_crs="EPSG:not-a-crs")


# --------------------------------------------------------------------- #
# GEO-05 — parsing
# --------------------------------------------------------------------- #


def test_multiple_features_become_multiple_roofs():
    doc = _feature_collection(_poly_4326(), _poly_4326(size=0.0004), _poly_4326(size=0.0003))
    assert len(imported.parse_geojson(doc)) == 3


def test_multipolygon_is_exploded_into_separate_roofs():
    multi = {
        "type": "MultiPolygon",
        "coordinates": [_poly_4326()["coordinates"], _poly_4326(size=0.0004)["coordinates"]],
    }
    assert len(imported.parse_geojson(_feature_collection(multi))) == 2


def test_bare_polygon_document_is_accepted():
    assert len(imported.parse_geojson(json.dumps(_poly_4326()).encode())) == 1


def test_properties_are_carried_through():
    doc = _feature_collection(_poly_4326(), props={"name": "Warehouse A", "jurisdiction": "IN-AP"})
    feature = imported.parse_geojson(doc)[0]
    assert feature.properties["name"] == "Warehouse A"
    assert feature.properties["jurisdiction"] == "IN-AP"


def test_invalid_json_is_rejected():
    with pytest.raises(GeometryRejected, match="not valid"):
        imported.parse_geojson(b"{not json")


def test_file_with_no_polygons_is_rejected():
    empty = json.dumps({"type": "FeatureCollection", "features": []}).encode()
    with pytest.raises(GeometryRejected, match="no polygon features"):
        imported.parse_geojson(empty)


def test_zip_without_a_shp_is_rejected():
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("readme.txt", "not a shapefile")
    with pytest.raises(GeometryRejected, match="no .shp file"):
        imported.parse_shapefile_zip(buf.getvalue())


# --------------------------------------------------------------------- #
# GEO-01 — the provider is registered and ranked
# --------------------------------------------------------------------- #


def test_imported_provider_is_registered():
    assert "imported" in [p.id for p in base.registered_providers()]


def test_precedence_ordering_matches_geo_06():
    """GEO-06: FIELD_MEASURED supersedes any remote geometry."""
    assert base.outranks("field_measured", "solar_api")
    assert base.outranks("field_measured", "manual_polygon")
    assert base.outranks("field_measured", "imported")
    assert base.outranks("manual_polygon", "solar_api")
    assert not base.outranks("solar_api", "field_measured")
    # A site with no geometry can always be filled.
    assert base.outranks("solar_api", None)


# --------------------------------------------------------------------- #
# GEO-06 — field measurement
# --------------------------------------------------------------------- #


def test_field_measurement_supersedes_and_versions(db_session):
    site = repo.create(
        db_session,
        site_type="ROOFTOP_CI",
        name="Surveyed roof",
        owner_org="org-survey",
        jurisdiction="IN-TG",
        centroid={"type": "Point", "coordinates": [LON, LAT]},
        boundary=_poly_4326(),
        geometry_source="solar_api",
        geometry_confidence=0.60,
        actor="importer",
    )

    updated = repo.record_field_measurement(
        db_session, site.id, boundary=_poly_4326(size=0.0006), actor="surveyor-9"
    )

    assert updated.geometry_source == "field_measured"
    # Ground truth outranks a remote guess, so confidence rises.
    assert updated.geometry_confidence > 0.60

    history = repo.versions(db_session, site.id)
    assert [v.source for v in history] == ["solar_api", "field_measured"]
    assert history[-1].actor == "surveyor-9"
    assert history[-1].note == "on-site measurement"


def test_field_measurement_on_unknown_site_raises(db_session):
    with pytest.raises(LookupError):
        repo.record_field_measurement(
            db_session,
            "00000000-0000-0000-0000-000000000000",
            boundary=_poly_4326(),
            actor="surveyor-9",
        )
