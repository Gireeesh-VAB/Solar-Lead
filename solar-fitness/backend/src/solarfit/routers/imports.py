"""Owner: Person 1 (Site & Geometry).

Implements API-07 (bulk import) and SITE-07 (duplicate detection) of
Solar_Fitness_Engine_Development_Document_v1.1, plus API-08/09
(export, webhook) since they're a direct extension of this person's own
IMPORTED provider work.

Partial success is the contract (API-07)
----------------------------------------
A 500-row import with 5 bad rows stores 495 and reports 5 with reasons.
It does NOT roll the whole thing back, and it does NOT silently skip.
Each row is committed in its own savepoint so one bad geometry cannot
poison its neighbours, and every rejection carries the row number and
the validator's own message.

Duplicate detection (SITE-07)
-----------------------------
"Is there already a site near this point" is a spatial lookup, not a
name match — two operators will spell the same address three ways. The
GiST index on sites.centroid from migration 0002 is what makes this a
lookup rather than a table scan.

Depends on:
  - solarfit.providers.imported (this person's own provider)
  - solarfit.repositories.sites (this person's own repository)
"""

from __future__ import annotations

import csv
import io
import json
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from shapely.geometry import mapping, shape
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from solarfit.auth import current_org
from solarfit.db import get_session
from solarfit.engine.area import compute_usable_area_m2
from solarfit.providers import imported, validation
from solarfit.providers.validation import GeometryRejected
from solarfit.repositories import sites as repo

router = APIRouter(prefix="/v1/imports", tags=["imports"])

# SITE-07 — two sites whose centroids are closer than this are treated as
# candidate duplicates. ~15 m is tighter than a building and looser than
# GPS jitter on a phone-captured point.
DUPLICATE_RADIUS_M = 15.0


# --------------------------------------------------------------------- #
# schemas
# --------------------------------------------------------------------- #


class RowError(BaseModel):
    row: int
    reason: str
    name: str | None = None


class DuplicateHit(BaseModel):
    row: int
    name: str | None = None
    existing_site_id: str
    distance_m: float


class ImportReport(BaseModel):
    """API-07. Every row is accounted for: imported + skipped + failed
    always equals total. A row that vanishes silently is a bug."""

    total_rows: int
    imported: int
    skipped_duplicates: int
    failed: int
    site_ids: list[str]
    duplicates: list[DuplicateHit]
    errors: list[RowError]


# --------------------------------------------------------------------- #
# SITE-07 duplicate detection
# --------------------------------------------------------------------- #


def find_nearby_site(
    session: Session,
    centroid: dict,
    owner_org: str,
    *,
    radius_m: float = DUPLICATE_RADIUS_M,
) -> tuple[str, float] | None:
    """SITE-07. Nearest existing site within `radius_m`, or None.

    Scoped to owner_org: another tenant having a site on the same roof is
    not this tenant's duplicate, and surfacing it would leak their data.
    """
    # ST_GeogFromText rather than a bare EWKT string: psycopg binds a
    # plain string as VARCHAR, and ST_DWithin has no varchar overload.
    point = func.ST_GeogFromText(f"SRID=4326;{shape(centroid).wkt}")
    distance = func.ST_Distance(repo.SiteRow.centroid, point)
    stmt = (
        select(repo.SiteRow.id, distance.label("d"))
        .where(repo.SiteRow.owner_org == owner_org)
        .where(func.ST_DWithin(repo.SiteRow.centroid, point, radius_m))
        .order_by("d")
        .limit(1)
    )
    hit = session.execute(stmt).first()
    return (str(hit[0]), float(hit[1])) if hit else None


# --------------------------------------------------------------------- #
# row extraction
# --------------------------------------------------------------------- #


def _rows_from_csv(payload: bytes) -> list[dict[str, Any]]:
    """CSV with a `boundary` column holding GeoJSON, or `lat`/`lng`.

    A CSV of addresses with no geometry is a geocoding job, not an
    import — that path goes through the Solar API provider instead.
    """
    text = payload.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict[str, Any]] = []

    for raw in reader:
        row: dict[str, Any] = {k.strip(): (v or "").strip() for k, v in raw.items() if k}
        if row.get("boundary"):
            try:
                row["boundary"] = json.loads(row["boundary"])
            except json.JSONDecodeError as exc:
                row["_error"] = f"boundary column is not valid GeoJSON: {exc}"
        elif row.get("lat") and row.get("lng"):
            try:
                row["centroid"] = {
                    "type": "Point",
                    "coordinates": [float(row["lng"]), float(row["lat"])],
                }
            except ValueError as exc:
                row["_error"] = f"lat/lng are not numbers: {exc}"
        else:
            row["_error"] = "row has neither a boundary column nor lat/lng"
        rows.append(row)

    return rows


def _rows_from_geometry_file(
    payload: bytes, filename: str | None, declared_crs: str | None
) -> list[dict[str, Any]]:
    features = imported.parse_upload(payload, filename=filename, declared_crs=declared_crs)
    return [
        {
            "boundary": f.boundary,
            "name": (f.properties.get("name") or f.properties.get("NAME")),
            "site_type": f.properties.get("site_type"),
            "jurisdiction": f.properties.get("jurisdiction"),
            **{k: v for k, v in f.properties.items() if k not in {"name", "NAME"}},
        }
        for f in features
    ]


# --------------------------------------------------------------------- #
# API-07 — bulk import
# --------------------------------------------------------------------- #


@router.post("", response_model=ImportReport, status_code=status.HTTP_207_MULTI_STATUS)
async def bulk_import(
    session: Annotated[Session, Depends(get_session)],
    owner_org: Annotated[str, Depends(current_org)],
    file: Annotated[UploadFile, File(description="CSV, GeoJSON, or zipped shapefile")],
    site_type: Annotated[str, Form()] = "ROOFTOP_RESIDENTIAL",
    jurisdiction: Annotated[str, Form()] = "IN-TG",
    source_crs: Annotated[str | None, Form()] = None,
    on_duplicate: Annotated[Literal["skip", "import"], Form()] = "skip",
) -> ImportReport:
    """API-07 + SITE-07. Import many sites, reporting every row.

    Returns 207 Multi-Status because partial success is the normal
    outcome, not an exception — a 200 would imply everything landed.
    """
    payload = await file.read()
    if not payload:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "uploaded file is empty")

    name = file.filename or ""
    try:
        if name.lower().endswith(".csv"):
            rows = _rows_from_csv(payload)
        else:
            rows = _rows_from_geometry_file(payload, name, source_crs)
    except GeometryRejected as exc:
        # A whole-file failure (unknown CRS, no polygons) is a 422 — there
        # are no per-row results to report.
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    report = ImportReport(
        total_rows=len(rows),
        imported=0,
        skipped_duplicates=0,
        failed=0,
        site_ids=[],
        duplicates=[],
        errors=[],
    )

    for index, row in enumerate(rows, start=1):
        row_name = row.get("name") or f"Imported site {index}"
        try:
            if row.get("_error"):
                raise GeometryRejected(row["_error"])

            boundary = row.get("boundary")
            centroid = row.get("centroid")
            if boundary is None and centroid is None:
                raise GeometryRejected("row has no geometry")

            if boundary is not None:
                if centroid is None:
                    centroid = validation.centroid_of(boundary)
                geom = validation.validate_boundary(boundary, centroid=centroid)
                boundary = mapping(geom)

            duplicate = find_nearby_site(session, centroid, owner_org)
            if duplicate and on_duplicate == "skip":
                report.skipped_duplicates += 1
                report.duplicates.append(
                    DuplicateHit(
                        row=index,
                        name=row_name,
                        existing_site_id=duplicate[0],
                        distance_m=round(duplicate[1], 2),
                    )
                )
                continue

            confidence = (
                validation.geometry_confidence(source="imported", boundary=boundary)
                if boundary
                else None
            )

            # Savepoint per row: one bad geometry must not poison the rows
            # around it, and the caller still gets a usable partial result.
            with session.begin_nested():
                site = repo.create(
                    session,
                    site_type=row.get("site_type") or site_type,
                    name=row_name,
                    owner_org=owner_org,
                    jurisdiction=row.get("jurisdiction") or jurisdiction,
                    centroid=centroid,
                    boundary=boundary,
                    geometry_source="imported" if boundary else None,
                    geometry_confidence=confidence,
                    actor=owner_org,
                )
            report.imported += 1
            report.site_ids.append(site.id)

            if duplicate:
                report.duplicates.append(
                    DuplicateHit(
                        row=index,
                        name=row_name,
                        existing_site_id=duplicate[0],
                        distance_m=round(duplicate[1], 2),
                    )
                )

        except (GeometryRejected, ValueError, KeyError) as exc:
            report.failed += 1
            report.errors.append(RowError(row=index, reason=str(exc), name=row_name))

    return report


# --------------------------------------------------------------------- #
# API-08 — export
# --------------------------------------------------------------------- #


@router.get("/export")
def export_sites(
    session: Annotated[Session, Depends(get_session)],
    owner_org: Annotated[str, Depends(current_org)],
    fmt: Annotated[Literal["csv", "geojson"], Query(alias="format")] = "csv",
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
) -> StreamingResponse:
    """API-08. Export this tenant's sites as CSV or GeoJSON.

    PDF is deliberately not here: a PDF export is a rendered report of an
    *assessment*, which is Person 4's response shape, not a dump of the
    site table. Adding a third format that means something different from
    the other two would be a worse API, so it belongs with §9.8's
    assessment endpoints.
    """
    rows = repo.list_sites(session, owner_org=owner_org, limit=limit)

    if fmt == "geojson":
        features = [
            {
                "type": "Feature",
                "geometry": s.boundary or s.centroid,
                "properties": {
                    "id": s.id,
                    "name": s.name,
                    "site_type": s.site_type,
                    "jurisdiction": s.jurisdiction,
                    "geometry_source": s.geometry_source,
                    "geometry_confidence": s.geometry_confidence,
                    "usable_area_m2": round(compute_usable_area_m2(s), 2) if s.boundary else None,
                },
            }
            for s in rows
        ]
        body = json.dumps({"type": "FeatureCollection", "features": features}, indent=2)
        return StreamingResponse(
            io.StringIO(body),
            media_type="application/geo+json",
            headers={"Content-Disposition": 'attachment; filename="sites.geojson"'},
        )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "id",
            "name",
            "site_type",
            "jurisdiction",
            "geometry_source",
            "geometry_confidence",
            "usable_area_m2",
            "created_at",
        ]
    )
    for s in rows:
        writer.writerow(
            [
                s.id,
                s.name,
                s.site_type,
                s.jurisdiction,
                s.geometry_source or "",
                s.geometry_confidence if s.geometry_confidence is not None else "",
                round(compute_usable_area_m2(s), 2) if s.boundary else "",
                s.created_at.isoformat(),
            ]
        )
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="sites.csv"'},
    )
