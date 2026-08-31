"""API-07 bulk import, SITE-07 duplicate detection, API-08 export — Person 1.

The load-bearing behaviour here is partial success: a file with bad rows
imports the good ones and reports the rest. A test suite that only feeds
clean files would miss the entire point of the endpoint.
"""

import csv
import io
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import box as shapely_box
from shapely.geometry import mapping

from solarfit.db import get_session
from solarfit.main import app

LON, LAT = 78.4867, 17.3850


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def org():
    """A fresh tenant per test — `sites` is shared with everything else in
    this database, so a fixed org would make these tests order-dependent."""
    return {"X-Owner-Org": f"org-{uuid4().hex[:8]}"}


def _poly(dlon: float = 0.0, dlat: float = 0.0, size: float = 0.0005) -> dict:
    return mapping(shapely_box(LON + dlon, LAT + dlat, LON + dlon + size, LAT + dlat + size))


def _geojson_bytes(*geoms: dict) -> bytes:
    return json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": g, "properties": {"name": f"Roof {i}"}}
                for i, g in enumerate(geoms, start=1)
            ],
        }
    ).encode()


def _csv_bytes(rows: list[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["name", "boundary"])
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return buf.getvalue().encode()


def _post(client, headers, payload: bytes, filename: str, **form):
    return client.post(
        "/v1/imports",
        headers=headers,
        files={"file": (filename, payload, "application/octet-stream")},
        data=form or None,
    )


# --------------------------------------------------------------------- #
# API-07 — happy path
# --------------------------------------------------------------------- #


def test_geojson_import_creates_sites(client, org):
    r = _post(client, org, _geojson_bytes(_poly(), _poly(dlon=0.01), _poly(dlon=0.02)), "roofs.geojson")
    assert r.status_code == 207, r.text

    body = r.json()
    assert body["total_rows"] == 3
    assert body["imported"] == 3
    assert body["failed"] == 0
    assert len(body["site_ids"]) == 3

    listed = client.get("/sites", headers=org).json()
    assert len(listed) == 3
    assert all(s["usable_area_m2"] > 0 for s in listed)


def test_csv_import_with_boundary_column(client, org):
    rows = [{"name": "Roof A", "boundary": json.dumps(_poly())},
            {"name": "Roof B", "boundary": json.dumps(_poly(dlon=0.01))}]
    r = _post(client, org, _csv_bytes(rows), "roofs.csv")
    assert r.json()["imported"] == 2


# --------------------------------------------------------------------- #
# API-07 — partial success is the contract
# --------------------------------------------------------------------- #


def test_bad_rows_do_not_stop_good_rows(client, org):
    """The whole reason this endpoint returns 207."""
    bowtie = {
        "type": "Polygon",
        "coordinates": [[[LON, LAT], [LON + 5e-4, LAT + 5e-4], [LON + 5e-4, LAT],
                         [LON, LAT + 5e-4], [LON, LAT]]],
    }
    payload = _geojson_bytes(_poly(), bowtie, _poly(dlon=0.02))

    body = _post(client, org, payload, "mixed.geojson").json()

    assert body["total_rows"] == 3
    assert body["imported"] == 2
    assert body["failed"] == 1
    assert body["errors"][0]["row"] == 2
    assert "self-intersecting" in body["errors"][0]["reason"]


def test_every_row_is_accounted_for(client, org):
    """imported + skipped + failed must equal total. A row that quietly
    disappears is the failure mode this assertion exists to catch."""
    huge = mapping(shapely_box(LON, LAT, LON + 0.5, LAT + 0.5))  # implausible
    body = _post(client, org, _geojson_bytes(_poly(), huge, _poly(dlon=0.02)), "x.geojson").json()

    assert body["imported"] + body["skipped_duplicates"] + body["failed"] == body["total_rows"]


def test_errors_carry_the_row_number_and_reason(client, org):
    rows = [{"name": "Good", "boundary": json.dumps(_poly())},
            {"name": "Bad", "boundary": "{not json"}]
    body = _post(client, org, _csv_bytes(rows), "x.csv").json()

    assert body["imported"] == 1
    assert body["failed"] == 1
    assert body["errors"][0]["row"] == 2
    assert body["errors"][0]["name"] == "Bad"


def test_whole_file_failure_is_422_not_207(client, org):
    """No per-row results exist when the file itself is unreadable."""
    r = _post(client, org, b"{not json at all", "broken.geojson")
    assert r.status_code == 422


def test_empty_upload_is_rejected(client, org):
    assert _post(client, org, b"", "empty.geojson").status_code == 422


# --------------------------------------------------------------------- #
# SITE-07 — duplicate detection
# --------------------------------------------------------------------- #


def test_reimporting_the_same_roof_is_detected_as_a_duplicate(client, org):
    first = _post(client, org, _geojson_bytes(_poly()), "a.geojson").json()
    assert first["imported"] == 1

    second = _post(client, org, _geojson_bytes(_poly()), "a.geojson").json()
    assert second["imported"] == 0
    assert second["skipped_duplicates"] == 1
    assert second["duplicates"][0]["existing_site_id"] == first["site_ids"][0]
    assert second["duplicates"][0]["distance_m"] < 15.0


def test_duplicates_can_be_imported_deliberately(client, org):
    _post(client, org, _geojson_bytes(_poly()), "a.geojson")
    body = _post(client, org, _geojson_bytes(_poly()), "a.geojson", on_duplicate="import").json()

    assert body["imported"] == 1
    assert body["skipped_duplicates"] == 0
    # Still reported, so the operator knows what they did.
    assert len(body["duplicates"]) == 1


def test_a_roof_far_away_is_not_a_duplicate(client, org):
    _post(client, org, _geojson_bytes(_poly()), "a.geojson")
    body = _post(client, org, _geojson_bytes(_poly(dlon=0.05)), "b.geojson").json()
    assert body["imported"] == 1
    assert body["skipped_duplicates"] == 0


def test_another_tenants_site_is_not_my_duplicate(client, org):
    """Scoping matters twice here: a false duplicate would block a
    legitimate import, and surfacing the other tenant's site id would
    leak their data."""
    other = {"X-Owner-Org": f"org-{uuid4().hex[:8]}"}
    _post(client, other, _geojson_bytes(_poly()), "a.geojson")

    body = _post(client, org, _geojson_bytes(_poly()), "a.geojson").json()
    assert body["imported"] == 1
    assert body["skipped_duplicates"] == 0


# --------------------------------------------------------------------- #
# GEO-05 — CRS handling through the endpoint
# --------------------------------------------------------------------- #


def test_projected_file_without_a_crs_is_rejected_at_the_endpoint(client, org):
    from pyproj import Transformer
    from shapely.ops import transform

    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32644", always_xy=True).transform
    utm_poly = mapping(transform(to_utm, shapely_box(LON, LAT, LON + 0.0005, LAT + 0.0005)))

    r = _post(client, org, _geojson_bytes(utm_poly), "utm.geojson")
    assert r.status_code == 422
    assert "coordinate system" in r.json()["detail"]


def test_projected_file_imports_with_source_crs(client, org):
    from pyproj import Transformer
    from shapely.ops import transform

    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32644", always_xy=True).transform
    utm_poly = mapping(transform(to_utm, shapely_box(LON, LAT, LON + 0.0005, LAT + 0.0005)))

    body = _post(client, org, _geojson_bytes(utm_poly), "utm.geojson", source_crs="EPSG:32644").json()
    assert body["imported"] == 1


# --------------------------------------------------------------------- #
# tenancy + API-08 export
# --------------------------------------------------------------------- #


def test_import_requires_a_tenant(client):
    r = client.post(
        "/v1/imports", files={"file": ("a.geojson", _geojson_bytes(_poly()), "application/json")}
    )
    assert r.status_code == 401


def test_csv_export_contains_the_computed_area(client, org):
    _post(client, org, _geojson_bytes(_poly()), "a.geojson")

    r = client.get("/v1/imports/export", params={"format": "csv"}, headers=org)
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]

    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert len(rows) == 1
    assert float(rows[0]["usable_area_m2"]) > 0
    assert rows[0]["geometry_source"] == "imported"


def test_geojson_export_is_a_feature_collection(client, org):
    _post(client, org, _geojson_bytes(_poly(), _poly(dlon=0.02)), "a.geojson")

    body = client.get("/v1/imports/export", params={"format": "geojson"}, headers=org).json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == 2
    assert body["features"][0]["properties"]["usable_area_m2"] > 0


def test_export_is_tenant_scoped(client, org):
    other = {"X-Owner-Org": f"org-{uuid4().hex[:8]}"}
    _post(client, org, _geojson_bytes(_poly()), "a.geojson")

    body = client.get("/v1/imports/export", params={"format": "geojson"}, headers=other).json()
    assert body["features"] == []
