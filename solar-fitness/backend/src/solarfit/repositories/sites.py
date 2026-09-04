"""Owner: Person 1 (Site & Geometry).

Implements SITE-05 (version boundary changes rather than overwriting;
retain full history with actor and timestamp) of
Solar_Fitness_Engine_Development_Document_v1.2, plus general
sites/site_versions CRUD.

Storage decisions worth knowing about
-------------------------------------
* Geometry columns are ``geography``, not ``geometry``. ``ST_Area`` on a
  geography column returns square metres natively, so §17's planar-4326
  bug cannot be reintroduced later by a careless raw query — the safety
  net is in the schema, not only in engine/area.py.
* ``sites`` carries the CURRENT geometry, ``site_versions`` carries every
  state including the current one. Reads stay single-table; history is
  append-only and never mutated.
* Restoring a superseded version (Person 3's OBS-06 admin-reject path)
  writes a NEW version equal to the old one. Nothing is ever deleted, so
  the audit trail shows the apply and the reversal as two events.

Interface note for Person 3
---------------------------
``new_geometry_version()`` supersedes the Day-0 stub's
``new_boundary_version(site_id, boundary, actor)``. Two things forced the
change: OBS-04 mutates EXCLUSIONS rather than the boundary, and the plan
has Person 3 calling it with ``source="obstacle_detection"`` — a
parameter the stub signature had no room for. A thin
``new_boundary_version()`` shim is kept below so nothing already written
against the old name breaks.

Merge addition (karthik + sameeksha, flagged for Person 1's review)
---------------------------------------------------------------------
``SiteVersionRow.applied_obstacle_ids`` / ``applied_obstacle_polygons``
are two new nullable JSONB columns, additive only — nothing above this
note is touched by them. OBS-06's admin-reject needs to identify and
reverse exactly ONE obstacle out of a version that may have auto-applied
several at once; the existing columns record the resulting geometry but
not which obstacle(s) produced it. ``new_geometry_version()`` gained two
matching optional kwargs threading them through to ``_append_version()``.
See ``engine/obstacles.py``'s ``apply_or_flag()``/``reject_applied_obstacle()``
for the only callers.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from geoalchemy2 import Geography
from geoalchemy2.shape import to_shape
from shapely import wkt as shapely_wkt
from shapely.geometry import mapping, shape
from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from solarfit.db import Base
from solarfit.domain.site import ShadingEstimate, Site, UsnCapture
from solarfit.providers import validation

__all__ = [
    "CompositeSiteRow",
    "SiteRow",
    "SiteVersionRow",
    "applied_obstacle_ids",
    "create",
    "create_composite_site",
    "get",
    "get_composite_site",
    "list_composite_sites",
    "list_sites",
    "new_boundary_version",
    "new_geometry_version",
    "record_field_measurement",
    "restore_version",
    "update_usn",
    "versions",
]

SRID = 4326


def _now() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------- #
# ORM models
# --------------------------------------------------------------------- #


class SiteRow(Base):
    """SITE-01. Current state of a site."""

    __tablename__ = "sites"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    site_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_org: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    jurisdiction: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    centroid: Mapped[Any] = mapped_column(
        Geography("POINT", srid=SRID, spatial_index=True), nullable=False
    )
    boundary: Mapped[Any | None] = mapped_column(
        Geography("POLYGON", srid=SRID, spatial_index=True), nullable=True
    )
    exclusions: Mapped[Any | None] = mapped_column(
        Geography("MULTIPOLYGON", srid=SRID, spatial_index=False), nullable=True
    )

    geometry_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    imagery_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    imagery_quality: Mapped[str | None] = mapped_column(String(32), nullable=True)
    geometry_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # SHADE-01 — extracted from the same Building Insights response as the
    # boundary. JSONB rather than columns because ShadingEstimate is a
    # frozen contract Person 1 does not own the evolution of alone.
    shading: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # karthik addition — the frontend's Site type needs these and nothing
    # backend-side stored them before (POST /sites accepted `address` as
    # geocoding *input* but never persisted it). Deliberately NOT added to
    # the frozen domain/site.py Site contract every other person codes
    # against — routers/app_sites.py reads these straight off this row,
    # the same way it already has to for updated_at below.
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    district: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

    # USN-01..06 (karthik + omkar, independently added and reconciled on
    # merge — both sides landed the identical columns) — the three
    # capture paths (manual/bill OCR/payment-proof OCR) all converge on
    # this one usn + usn_source pair. Scoped at the schema-validation
    # layer (SITE-02, domain/schemas.py) to BILLING_LINKED_SITE_TYPES
    # only; this column exists on every row regardless of site_type,
    # same as address/district/state above. The confirmed value only,
    # not the USN-06 evidence trail (see repositories/usn_uploads.py for
    # that).
    usn: Mapped[str | None] = mapped_column(String(64), nullable=True)
    usn_source: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # CON-05 input. The customer's own lowest/highest monthly bill, stored
    # as entered rather than as derived kWh: the tariff that converts it is
    # a config-pack placeholder that will change, and re-deriving from the
    # original keeps old checks correct when it does.
    monthly_bill_low_inr: Mapped[float | None] = mapped_column(Float, nullable=True)
    monthly_bill_high_inr: Mapped[float | None] = mapped_column(Float, nullable=True)

    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    history: Mapped[list[SiteVersionRow]] = relationship(
        back_populates="site", order_by="SiteVersionRow.version_no", cascade="all, delete-orphan"
    )


class SiteVersionRow(Base):
    """SITE-05. Append-only geometry history. Rows are never updated or
    deleted — superseding one writes the next version."""

    __tablename__ = "site_versions"
    __table_args__ = (UniqueConstraint("site_id", "version_no", name="uq_site_versions_site_no"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)

    boundary: Mapped[Any | None] = mapped_column(
        Geography("POLYGON", srid=SRID, spatial_index=False), nullable=True
    )
    exclusions: Mapped[Any | None] = mapped_column(
        Geography("MULTIPOLYGON", srid=SRID, spatial_index=False), nullable=True
    )

    geometry_source: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # SITE-04 — every boundary carries the imagery it was traced from,
    # not just the current one on SiteRow. Previously only geometry_source
    # was captured per version, so a site's history lost imagery_date/
    # imagery_quality/geometry_confidence context the moment a second
    # version was written.
    imagery_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    imagery_quality: Mapped[str | None] = mapped_column(String(32), nullable=True)
    geometry_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Who and why. `source` is free-form so Person 3 can pass
    # "obstacle_detection" without a schema change, and an admin reversal
    # can pass "obstacle_rejected" (OBS-06).
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # OBS-04/06 (Person 3 addition, merge-flagged above): only populated
    # when source == "obstacle_detection". applied_obstacle_polygons maps
    # obstacle id -> the GeoJSON polygon that was unioned into exclusions
    # at this version, so a later reject can subtract exactly one
    # obstacle's contribution rather than the whole version's batch.
    applied_obstacle_ids: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    applied_obstacle_polygons: Mapped[dict[str, dict] | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    site: Mapped[SiteRow] = relationship(back_populates="history")


# --------------------------------------------------------------------- #
# GeoJSON <-> PostGIS
# --------------------------------------------------------------------- #


def _to_wkt(geojson: dict | None) -> str | None:
    """GeoJSON dict -> EWKT for a geography column."""
    if not geojson:
        return None
    return f"SRID={SRID};{shape(geojson).wkt}"


def _to_geojson(column_value: Any) -> dict | None:
    """PostGIS geography -> GeoJSON dict.

    Accepts either what the database returns (a WKB/WKT element) or the
    EWKT string still sitting on a freshly-flushed, not-yet-refreshed
    instance. Both occur in normal use, and callers should not have to
    care which side of a refresh they are on.
    """
    if column_value is None:
        return None
    if isinstance(column_value, str):
        wkt = column_value.split(";", 1)[1] if column_value.startswith("SRID=") else column_value
        return mapping(shapely_wkt.loads(wkt))
    return mapping(to_shape(column_value))


def _to_domain(row: SiteRow) -> Site:
    """SiteRow -> the frozen Site contract every other person codes against."""
    return Site(
        id=str(row.id),
        site_type=row.site_type,  # type: ignore[arg-type]
        name=row.name,
        owner_org=row.owner_org,
        jurisdiction=row.jurisdiction,
        centroid=_to_geojson(row.centroid) or {},
        boundary=_to_geojson(row.boundary),
        exclusions=_to_geojson(row.exclusions),
        geometry_source=row.geometry_source,  # type: ignore[arg-type]
        imagery_date=row.imagery_date,
        imagery_quality=row.imagery_quality,
        geometry_confidence=row.geometry_confidence,
        shading=ShadingEstimate(**row.shading) if row.shading else None,
        usn=UsnCapture(usn=row.usn, usn_source=row.usn_source) if row.usn is not None else None,  # type: ignore[arg-type]
        created_at=row.created_at,
    )


# --------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------- #


def create(
    session: Session,
    *,
    site_type: str,
    name: str,
    owner_org: str,
    jurisdiction: str,
    centroid: dict,
    boundary: dict | None = None,
    exclusions: dict | None = None,
    geometry_source: str | None = None,
    imagery_date: datetime | None = None,
    imagery_quality: str | None = None,
    geometry_confidence: float | None = None,
    shading: ShadingEstimate | dict | None = None,
    address: str | None = None,
    district: str | None = None,
    state: str | None = None,
    tags: list[str] | None = None,
    usn: str | None = None,
    usn_source: str | None = None,
    monthly_bill_low_inr: float | None = None,
    monthly_bill_high_inr: float | None = None,
    actor: str = "system",
) -> Site:
    """SITE-01. Create a site.

    When a boundary is supplied at creation it becomes version 1 —
    SITE-05's history starts at the first geometry, not at the first
    change, so there is never a current boundary with no history row.

    address/district/state/tags (karthik addition) are optional and
    frontend-facing only — existing callers that don't pass them are
    unaffected. usn/usn_source (USN-01..04) are likewise optional —
    SITE-02's JSON Schema is what actually enforces they're only ever
    supplied for BILLING_LINKED_SITE_TYPES; this function just stores
    whatever it's given.
    """
    if isinstance(shading, ShadingEstimate):
        shading = shading.model_dump()

    row = SiteRow(
        site_type=site_type,
        name=name,
        owner_org=owner_org,
        jurisdiction=jurisdiction,
        centroid=_to_wkt(centroid),
        boundary=_to_wkt(boundary),
        exclusions=_to_wkt(exclusions),
        geometry_source=geometry_source,
        imagery_date=imagery_date,
        imagery_quality=imagery_quality,
        geometry_confidence=geometry_confidence,
        shading=shading,
        address=address,
        district=district,
        state=state,
        tags=tags,
        usn=usn,
        usn_source=usn_source,
        monthly_bill_low_inr=monthly_bill_low_inr,
        monthly_bill_high_inr=monthly_bill_high_inr,
        current_version=0,
    )
    session.add(row)
    session.flush()

    if boundary or exclusions:
        _append_version(
            session,
            row,
            boundary=boundary,
            exclusions=exclusions,
            geometry_source=geometry_source,
            imagery_date=imagery_date,
            imagery_quality=imagery_quality,
            geometry_confidence=geometry_confidence,
            actor=actor,
            source=geometry_source or "create",
            note="initial geometry",
        )

    session.flush()
    # Read the geometry back as PostGIS actually stored it, rather than
    # echoing the EWKT we sent — a genuine round-trip, and it surfaces
    # any SRID or type coercion the database applied.
    session.refresh(row)
    return _to_domain(row)


def get(session: Session, site_id: str | uuid.UUID) -> Site | None:
    row = session.get(SiteRow, uuid.UUID(str(site_id)))
    return _to_domain(row) if row else None


def applied_obstacles(session: Session, site_id: str | uuid.UUID) -> list[tuple[str, dict]]:
    """OBS-04. Every obstacle union'd into this site's exclusions, as
    (obstacle_id, GeoJSON polygon) pairs.

    Walks the version history rather than one row: obstacles are applied
    across successive versions, and applied_obstacle_polygons on each
    version records only what THAT version contributed. Later versions win
    on id, so an obstacle re-applied after a rejection reports its current
    polygon.

    Empty is the honest answer for a site whose obstacles have never been
    detected — which is every site until the vision pipeline has an
    OPENAI_API_KEY to run with.
    """
    try:
        key = uuid.UUID(str(site_id))
    except (ValueError, AttributeError, TypeError):
        return []

    versions = (
        session.query(SiteVersionRow)
        .filter(SiteVersionRow.site_id == key)
        .order_by(SiteVersionRow.version_no.asc())
        .all()
    )
    by_id: dict[str, dict] = {}
    for version in versions:
        for obstacle_id, polygon in (version.applied_obstacle_polygons or {}).items():
            if polygon:
                by_id[obstacle_id] = polygon
    return list(by_id.items())


def get_bill_range(session: Session, site_id: str | uuid.UUID) -> tuple[float | None, float | None]:
    """The customer's (lowest, highest) monthly bill, or (None, None).

    Returned separately rather than added to the domain Site: that
    contract is frozen Day 0 and every other person codes against it.
    Only the capacity path needs this, so only the capacity path asks.

    An id that isn't a UUID reports "no bill" rather than raising. The
    caller is mid-lookup and has its own not-found path a line later;
    letting a malformed id explode here turned that clean 404 into a 500.
    """
    try:
        key = uuid.UUID(str(site_id))
    except (ValueError, AttributeError, TypeError):
        return None, None

    row = session.get(SiteRow, key)
    if row is None:
        return None, None
    return row.monthly_bill_low_inr, row.monthly_bill_high_inr


def update_usn(session: Session, site_id: str | uuid.UUID, *, usn: str, usn_source: str) -> Site:
    """USN-01..04. Persists a captured usn/usn_source onto an existing
    site — the write-side counterpart create()'s own usn/usn_source
    kwargs cover at creation time. Called by whichever capture path has
    already validated the value (manual entry, or USN-02/03's
    providers.usn_ocr.confirm_and_finalize()) — this is a pure
    persistence step, no format or site-type validation of its own,
    same division of responsibility as create(): SITE-02's JSON Schema
    (domain/schemas.py), enforced at the router layer, is what actually
    restricts usn/usn_source to BILLING_LINKED_SITE_TYPES.

    Raises LookupError for an unknown site — never a silent no-op,
    matching new_geometry_version()'s own discipline.
    """
    row = session.get(SiteRow, uuid.UUID(str(site_id)))
    if row is None:
        raise LookupError(f"site {site_id} not found")
    row.usn = usn
    row.usn_source = usn_source
    row.updated_at = _now()
    session.flush()
    return _to_domain(row)


def list_sites(
    session: Session, *, owner_org: str | None = None, limit: int = 50, offset: int = 0
) -> list[Site]:
    """Tenant-scoped listing. `owner_org` is the tenant boundary — callers
    that omit it are asking for a cross-tenant read and must have already
    established the right to one."""
    stmt = select(SiteRow).order_by(SiteRow.created_at.desc()).limit(limit).offset(offset)
    if owner_org is not None:
        stmt = stmt.where(SiteRow.owner_org == owner_org)
    return [_to_domain(row) for row in session.scalars(stmt)]


# --------------------------------------------------------------------- #
# SITE-05 versioning
# --------------------------------------------------------------------- #


def _append_version(
    session: Session,
    row: SiteRow,
    *,
    boundary: dict | None,
    exclusions: dict | None,
    geometry_source: str | None,
    actor: str,
    source: str,
    note: str | None = None,
    imagery_date: datetime | None = None,
    imagery_quality: str | None = None,
    geometry_confidence: float | None = None,
    applied_obstacle_ids: list[str] | None = None,
    applied_obstacle_polygons: dict[str, dict] | None = None,
) -> SiteVersionRow:
    version = SiteVersionRow(
        site_id=row.id,
        version_no=row.current_version + 1,
        boundary=_to_wkt(boundary),
        exclusions=_to_wkt(exclusions),
        geometry_source=geometry_source,
        imagery_date=imagery_date,
        imagery_quality=imagery_quality,
        geometry_confidence=geometry_confidence,
        actor=actor,
        source=source,
        note=note,
        applied_obstacle_ids=applied_obstacle_ids,
        applied_obstacle_polygons=applied_obstacle_polygons,
    )
    session.add(version)
    row.current_version = version.version_no
    row.updated_at = _now()
    session.flush()
    return version


def new_geometry_version(
    session: Session,
    site_id: str | uuid.UUID,
    *,
    boundary: dict | None = None,
    exclusions: dict | None = None,
    actor: str,
    source: str,
    geometry_source: str | None = None,
    note: str | None = None,
    imagery_date: datetime | None = None,
    imagery_quality: str | None = None,
    geometry_confidence: float | None = None,
    applied_obstacle_ids: list[str] | None = None,
    applied_obstacle_polygons: dict[str, dict] | None = None,
) -> Site:
    """SITE-05. Record a geometry change as a new version, never an overwrite.

    Pass only what changed: omitting ``boundary`` keeps the current
    boundary, omitting ``exclusions`` keeps the current exclusions. Every
    version row stores the FULL resulting geometry, not a delta, so any
    historical state can be read back without replaying the chain.

    ``source`` is the audit reason — ``"obstacle_detection"`` for Person
    3's OBS-04 auto-apply, ``"obstacle_rejected"`` for the OBS-06
    reversal, ``"manual_edit"`` for an operator correction.

    ``imagery_date``/``imagery_quality``/``geometry_confidence`` (SITE-04):
    like ``geometry_source``, default to the site's current values when
    omitted — an exclusions-only change (OBS-04/06) doesn't re-trace the
    boundary from new imagery, so the imagery context that produced the
    boundary is unchanged and should carry forward rather than going
    missing from this version.

    ``applied_obstacle_ids``/``applied_obstacle_polygons`` (Person 3
    addition): only meaningful when source == "obstacle_detection" —
    records exactly which obstacle(s) this version's exclusions change
    came from, and each one's own polygon, so a later
    ``source="obstacle_rejected"`` version can subtract precisely one of
    them rather than reverting the whole batch.
    """
    row = session.get(SiteRow, uuid.UUID(str(site_id)))
    if row is None:
        raise LookupError(f"site {site_id} not found")

    if boundary is None and exclusions is None:
        raise ValueError("new_geometry_version requires a boundary or exclusions to change")

    next_boundary = boundary if boundary is not None else _to_geojson(row.boundary)
    next_exclusions = exclusions if exclusions is not None else _to_geojson(row.exclusions)

    row.boundary = _to_wkt(next_boundary)
    row.exclusions = _to_wkt(next_exclusions)
    if geometry_source is not None:
        row.geometry_source = geometry_source
    if imagery_date is not None:
        row.imagery_date = imagery_date
    if imagery_quality is not None:
        row.imagery_quality = imagery_quality
    if geometry_confidence is not None:
        row.geometry_confidence = geometry_confidence

    _append_version(
        session,
        row,
        boundary=next_boundary,
        exclusions=next_exclusions,
        geometry_source=geometry_source or row.geometry_source,
        imagery_date=imagery_date or row.imagery_date,
        imagery_quality=imagery_quality or row.imagery_quality,
        geometry_confidence=geometry_confidence
        if geometry_confidence is not None
        else row.geometry_confidence,
        actor=actor,
        source=source,
        note=note,
        applied_obstacle_ids=applied_obstacle_ids,
        applied_obstacle_polygons=applied_obstacle_polygons,
    )
    return _to_domain(row)


def new_boundary_version(
    session: Session,
    site_id: str | uuid.UUID,
    boundary: dict,
    actor: str,
    *,
    source: str = "manual_edit",
) -> Site:
    """Compatibility shim over the Day-0 stub signature. Prefer
    new_geometry_version(), which can also change exclusions."""
    return new_geometry_version(session, site_id, boundary=boundary, actor=actor, source=source)


def record_field_measurement(
    session: Session,
    site_id: str | uuid.UUID,
    *,
    boundary: dict | None = None,
    exclusions: dict | None = None,
    actor: str,
    note: str | None = None,
) -> Site:
    """GEO-06 (FIELD_MEASURED). A surveyor's on-site measurement.

    Implemented here rather than as a provider module because it is not a
    *resolution* step — nothing is fetched or derived. It arrives as an
    edit to a site that already exists, so it is exactly a SITE-05
    version with the highest-precedence source, and providers/base.py's
    own docstring suggests this home for it.

    Unconditional by design: GEO-06 says field measurement supersedes any
    remote geometry, and base.PRECEDENCE ranks it above every other
    source, so there is no case where an existing boundary outranks it.
    Confidence is set to the field-measured ceiling for the same reason —
    a human stood on the roof.
    """
    row = session.get(SiteRow, uuid.UUID(str(site_id)))
    if row is None:
        raise LookupError(f"site {site_id} not found")

    new_geometry_version(
        session,
        site_id,
        boundary=boundary,
        exclusions=exclusions,
        actor=actor,
        source="field_measured",
        geometry_source="field_measured",
        note=note or "on-site measurement",
    )

    row.geometry_confidence = validation.geometry_confidence(
        source="field_measured", boundary=boundary or _to_geojson(row.boundary)
    )
    row.imagery_date = None  # a tape measure does not go stale with imagery
    session.flush()
    return _to_domain(session.get(SiteRow, uuid.UUID(str(site_id))))


def versions(session: Session, site_id: str | uuid.UUID) -> list[SiteVersionRow]:
    """Full history, oldest first. Append-only — nothing here is ever
    updated or deleted."""
    stmt = (
        select(SiteVersionRow)
        .where(SiteVersionRow.site_id == uuid.UUID(str(site_id)))
        .order_by(SiteVersionRow.version_no)
    )
    return list(session.scalars(stmt))


def applied_obstacle_ids(session: Session, site_id: str | uuid.UUID) -> set[str]:
    """OBS-04 idempotency: every obstacle id ever auto-applied to this
    site, across its whole SITE-05 history. The same cached vision
    detection (site_analysis_cache.vision_refinement) can be replayed on
    every assessment call for this site, or reused by a different site
    at the same rounded lat/long (CACHE-01/03) — an obstacle already
    reflected in this site's exclusions must never be unioned in again,
    which is exactly what a naive re-apply would otherwise do on every
    single POST /v1/assessments/{id}."""
    ids: set[str] = set()
    for v in versions(session, site_id):
        if v.applied_obstacle_ids:
            ids.update(v.applied_obstacle_ids)
    return ids


def restore_version(
    session: Session,
    site_id: str | uuid.UUID,
    version_no: int,
    *,
    actor: str,
    source: str = "restore",
    note: str | None = None,
) -> Site:
    """OBS-06. Return a site to an earlier geometry by writing a NEW
    version equal to it.

    Deliberately not a delete or a pointer rewind: the audit trail must
    show that version N happened and was then reversed, not that it never
    existed.
    """
    row = session.get(SiteRow, uuid.UUID(str(site_id)))
    if row is None:
        raise LookupError(f"site {site_id} not found")

    stmt = select(SiteVersionRow).where(
        SiteVersionRow.site_id == row.id, SiteVersionRow.version_no == version_no
    )
    target = session.scalars(stmt).one_or_none()
    if target is None:
        raise LookupError(f"site {site_id} has no version {version_no}")

    boundary = _to_geojson(target.boundary)
    exclusions = _to_geojson(target.exclusions)

    row.boundary = _to_wkt(boundary)
    row.exclusions = _to_wkt(exclusions)
    row.geometry_source = target.geometry_source

    _append_version(
        session,
        row,
        boundary=boundary,
        exclusions=exclusions,
        geometry_source=target.geometry_source,
        actor=actor,
        source=source,
        note=note or f"restored from version {version_no}",
    )
    return _to_domain(row)


# --------------------------------------------------------------------- #
# SITE-06 composite sites (karthik addition — feeder/DT aggregation)
# --------------------------------------------------------------------- #


class CompositeSiteRow(Base):
    """SITE-06. A named group of existing sites (a feeder or distribution
    transformer's membership), for the frontend's aggregate reporting.
    member_site_ids is plain JSONB rather than a join table — membership
    here is small and read far more often than it changes."""

    __tablename__ = "composite_sites"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    feeder_or_dt: Mapped[str] = mapped_column(String(255), nullable=False)
    member_site_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


def create_composite_site(
    session: Session,
    *,
    name: str,
    feeder_or_dt: str,
    member_site_ids: list[str],
    owner_org: str,
) -> CompositeSiteRow:
    """Validates every member id resolves to a real site owned by the
    same tenant before inserting — a composite site quietly grouping
    someone else's roofs (or nothing at all) would be a silent data bug,
    not a feature."""
    if not member_site_ids:
        raise ValueError("a composite site needs at least one member site")

    for site_id in member_site_ids:
        member = get(session, site_id)
        if member is None or member.owner_org != owner_org:
            raise LookupError(f"site {site_id} not found")

    row = CompositeSiteRow(name=name, feeder_or_dt=feeder_or_dt, member_site_ids=member_site_ids)
    session.add(row)
    session.flush()
    return row


def get_composite_site(session: Session, composite_id: str | uuid.UUID) -> CompositeSiteRow | None:
    return session.get(CompositeSiteRow, uuid.UUID(str(composite_id)))


def list_composite_sites(session: Session, *, owner_org: str) -> list[CompositeSiteRow]:
    """No owner_org column on composite_sites itself — scoped instead by
    "every member site belongs to this tenant", read off the first member
    (create_composite_site() already guarantees every member shares one
    owner_org, so checking the first is checking them all)."""
    stmt = select(CompositeSiteRow).order_by(CompositeSiteRow.created_at.desc())
    result = []
    for row in session.scalars(stmt):
        if row.member_site_ids:
            first_member = get(session, row.member_site_ids[0])
            if first_member is not None and first_member.owner_org == owner_org:
                result.append(row)
    return result
