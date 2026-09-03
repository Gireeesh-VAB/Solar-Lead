"""Owner: Person 3 (AI Pipeline & Cache).

Implements §9.14 Result Cache (CACHE-01..05) of
Solar_Fitness_Engine_Development_Document_v1.2 and the
get_or_create_analysis() lookup-or-compute pattern from §12.1.

  CACHE-01  Key on lat/long rounded via
            solarfit.packs.config_pack.get_cache_precision() — not on
            site id, tenant id, or a provider-specific building id.
  CACHE-02  Look up the cache before invoking any GEO/VIS/weather/VIZ/ML
            step; on a hit, zero external calls.
  CACHE-03  One table, one key scheme, independent of site type.
  CACHE-04  Reuse is unconditional by default — no automatic expiry —
            but an explicit admin "force refresh" path must exist.
  CACHE-05  Every cache hit recorded as such (reused_from_analysis_id +
            timestamps) — never indistinguishable from a fresh run.

Day 1 status: the cache layer itself (this file's ORM model + CRUD +
the hit/miss orchestration shape) is real. Day 2 status: the VIS leg
of the miss path is also real (fetch_rgb_imagery / crop_to_boundary /
refine_with_vision_model in providers/vision.py). Geometry resolution,
weather, panorama, and ML scoring are still NotImplementedError stubs
owned by Person 1/2/4 elsewhere; they get filled in over the next
several days. Tests here mock those calls to prove the cache/orchestration
logic is correct independent of whether every stage exists yet.

OBS-09 note: the `vision_refinement` jsonb column must persist the FULL
obstacle list (every detection, applied or not), not just the ones
OBS-04 auto-applied — that raw record is what CAL-style accuracy
reporting compares against once field-survey ground truth exists.
Don't slim it down to "applied obstacles only."

CACHE-01 rounding-collision risk (Day 6, documented not fixed — this
is the spec's own explicit tradeoff, a "Must" requirement written
exactly this way, not a bug introduced here): the default cache
precision (5 decimal places, ~1.1m at the equator) means two genuinely
different rooftops close enough together — adjacent rowhouses, or
different units of the same complex — could round into the same
(lat_rounded, lng_rounded) bucket and silently share one analysis. The
two real alternatives, neither picked here since it's a product/team
call: tighten `cache_precision` (reduces collision risk, but also
reduces the deliberate "same building, slightly different click" reuse
CACHE-01 exists for), or add a shape/centroid sanity check on a hit
before trusting it (a real fix, but touches site-identity logic that's
arguably Person 1's territory, not this cache layer's).

Depends on: solarfit.domain.assessment.AnalysisResult (frozen, Day 0),
solarfit.packs.config_pack.get_cache_precision (frozen loader, Day 0),
solarfit.db.session_scope (session factory, real since Day 1; renamed after the karthik+sameeksha db.py merge).
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from geoalchemy2 import Geometry
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import mapping as shapely_mapping
from shapely.geometry import shape as shapely_shape
from sqlalchemy import DateTime, Numeric, String, UniqueConstraint, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from solarfit.db import Base, session_scope
from solarfit.domain.assessment import AnalysisResult, MLScore, PanoramaResult, VisionRefinement

logger = logging.getLogger(__name__)
from solarfit.domain.site import Site
from solarfit.packs.config_pack import get_cache_precision

# Deliberately NOT "unknown" — an unmistakable poison marker instead, so if
# a future change ever reads a field off one of the synthetic Site objects
# built inside get_or_create_analysis() (below), the garbage value is
# obvious in logs/output rather than silently plausible.
_SYNTHETIC_PLACEHOLDER = "SYNTHETIC_CACHE_SITE_NOT_REAL_DATA"


class SiteAnalysisCache(Base):
    """CACHE-01. Shared across every tenant/site — never scoped by
    site_id or tenant_id, per CACHE-01/CACHE-03. See §14 for the DDL
    this mirrors."""

    __tablename__ = "site_analysis_cache"
    __table_args__ = (UniqueConstraint("lat_rounded", "lng_rounded", name="uq_cache_latlng"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    lat_rounded: Mapped[float] = mapped_column(Numeric, nullable=False, index=True)
    lng_rounded: Mapped[float] = mapped_column(Numeric, nullable=False, index=True)
    boundary = mapped_column(Geometry("POLYGON", srid=4326), nullable=True)
    vision_refinement: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    weather_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    panorama_url: Mapped[str | None] = mapped_column(String, nullable=True)
    ml_suitability_score: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    ml_model_version: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_reused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def round_latlng(lat: float, lng: float, precision: int | None = None) -> tuple[float, float]:
    """CACHE-01. precision defaults to the config-pack value if not given."""
    p = precision if precision is not None else get_cache_precision()
    return round(lat, p), round(lng, p)


def _row_to_result(
    row: SiteAnalysisCache, *, cache_hit: bool, reused_from_analysis_id: str | None
) -> AnalysisResult:
    """Maps a DB row to the frozen AnalysisResult contract. Fields the
    cache table doesn't own (usable_area_m2, capacity, engine_version,
    constraint_pack_version) are left None here — they're computed
    fresh on every request by whoever assembles the final API response
    (Person 4), never cached, so a config-pack coefficient change picks
    up immediately without needing to invalidate anything."""
    boundary_geojson = shapely_mapping(to_shape(row.boundary)) if row.boundary is not None else None
    vision_refinement = VisionRefinement(**row.vision_refinement) if row.vision_refinement else None
    panorama = PanoramaResult(url=row.panorama_url) if row.panorama_url else None
    ml_score = (
        MLScore(score=float(row.ml_suitability_score), model_version=row.ml_model_version)
        if row.ml_suitability_score is not None
        else None
    )
    return AnalysisResult(
        boundary=boundary_geojson or {},
        vision_refinement=vision_refinement,
        panorama=panorama,
        ml_score=ml_score,
        cache_hit=cache_hit,
        reused_from_analysis_id=reused_from_analysis_id,
    )


def find_by_key(lat_rounded: float, lng_rounded: float) -> AnalysisResult | None:
    """CACHE-01. Returns None on a miss — callers decide what to do next."""
    with session_scope() as session:
        row = session.execute(
            select(SiteAnalysisCache).where(
                SiteAnalysisCache.lat_rounded == lat_rounded,
                SiteAnalysisCache.lng_rounded == lng_rounded,
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return _row_to_result(row, cache_hit=True, reused_from_analysis_id=str(row.id))


def create(
    lat_rounded: float,
    lng_rounded: float,
    boundary: dict,
    vision_refinement: dict | None = None,
    weather_snapshot: dict | None = None,
    panorama_url: str | None = None,
    ml_suitability_score: float | None = None,
    ml_model_version: str | None = None,
) -> AnalysisResult:
    """CACHE-02/03. Called once, on a cache miss, after the full
    pipeline has run — never called speculatively."""
    row_id = uuid.uuid4()
    boundary_shape = from_shape(shapely_shape(boundary), srid=4326)
    with session_scope() as session:
        session.add(
            SiteAnalysisCache(
                id=row_id,
                lat_rounded=lat_rounded,
                lng_rounded=lng_rounded,
                boundary=boundary_shape,
                vision_refinement=vision_refinement,
                weather_snapshot=weather_snapshot,
                panorama_url=panorama_url,
                ml_suitability_score=ml_suitability_score,
                ml_model_version=ml_model_version,
                created_at=datetime.now(UTC),
            )
        )

    return AnalysisResult(
        boundary=boundary,
        vision_refinement=VisionRefinement(**vision_refinement) if vision_refinement else None,
        panorama=PanoramaResult(url=panorama_url) if panorama_url else None,
        ml_score=(
            MLScore(score=ml_suitability_score, model_version=ml_model_version)
            if ml_suitability_score is not None
            else None
        ),
        cache_hit=False,
        reused_from_analysis_id=None,
    )


def mark_reused(analysis_id: str) -> None:
    """CACHE-05. Stamps last_reused_at — called on every cache hit so a
    reused row is never indistinguishable from a fresh one."""
    with session_scope() as session:
        row = session.execute(
            select(SiteAnalysisCache).where(SiteAnalysisCache.id == uuid.UUID(analysis_id))
        ).scalar_one()
        row.last_reused_at = datetime.now(UTC)


def force_refresh(lat: float, lng: float, params: dict | None = None) -> None:
    """CACHE-04. Deletes the existing cache row for this location so the
    next get_or_create_analysis() call is guaranteed a miss. Never
    called automatically — admin-triggered only."""
    lat_r, lng_r = round_latlng(lat, lng)
    with session_scope() as session:
        row = session.execute(
            select(SiteAnalysisCache).where(
                SiteAnalysisCache.lat_rounded == lat_r,
                SiteAnalysisCache.lng_rounded == lng_r,
            )
        ).scalar_one_or_none()
        if row is not None:
            session.delete(row)


def _await_task(async_result, timeout_s: float, *, label: str, fallback: dict) -> dict:
    """Wait for a dispatched Celery task, degrading instead of exploding.

    Both VIS-04 and VIZ-03 promise that a failure in these steps never
    blocks the pipeline, and both engines honour that internally — they
    return an explicit "insufficient_data"/"not_generated" rather than
    raising. But the WAIT happens out here, and a
    celery.exceptions.TimeoutError raised by .get() bypasses those
    contracts entirely: a slow DSM download was enough to take down a
    customer's verdict and capacity along with it. Three real checks died
    that way before this existed.

    Anything that goes wrong on the way to an answer — the task timing
    out, the worker being down, the broker unreachable — is the same
    outcome from the caller's side: no refinement, no panorama, and an
    assessment that still completes on the data it does have.
    """
    try:
        return async_result.get(timeout=timeout_s)
    except Exception:
        logger.warning(
            "%s task did not complete within %.0fs — continuing without it",
            label,
            timeout_s,
            exc_info=True,
        )
        return fallback


def get_or_create_analysis(
    lat: float, lng: float, site_type: str, params: dict[str, Any] | None = None
) -> AnalysisResult:
    """CACHE-02/03. See §12.1 for the reference shape this mirrors.

    VIS-05/VIZ-05: vision refinement and panorama generation run through
    the real Celery worker (refine_vision_task/generate_panorama_task),
    dispatched via .delay().get(timeout=...) rather than called inline —
    this endpoint's own contract stays synchronous (the caller still gets
    a full result back), but execution actually goes through the
    worker/queue infrastructure those tasks exist for.

    Obstacle detection's raw output (OBS-01/02) rides along inside
    refine_vision_task's structured-output call, same as before — but
    OBS-03 validation and OBS-04/05's threshold split/auto-apply are
    deliberately NOT done here any more (see history for the removed
    synthetic-Site version of this). This cache is site-independent by
    design (CACHE-01/03 — keyed on rounded lat/long, shared across every
    tenant/site), while auto-applying an obstacle is inherently
    site-specific (it writes one SITE-05 version onto one real site's
    exclusions). Handing engine.obstacles.apply_or_flag() a fake,
    non-persisted site id here silently broke OBS-04 — every write threw
    (invalid UUID) and was swallowed by that function's own
    "degrade to advisory on DB failure" handling, so auto-apply never
    actually fired. Obstacle classification/persistence now happens in
    routers/assessments.py::orchestrate_assessment(), which has the real
    site and dispatches apply_obstacles_task with its real id.
    """
    params = params or {}
    lat_r, lng_r = round_latlng(lat, lng, precision=params.get("cache_precision"))

    cached = find_by_key(lat_r, lng_r)
    if cached is not None:
        mark_reused(cached.reused_from_analysis_id)
        return cached

    from solarfit.engine.ml_score import score_with_ml_model
    from solarfit.packs.config_pack import get_async_task_timeout_s, get_panorama_enabled
    from solarfit.providers.solar_api import resolve_via_solar_api
    from solarfit.providers.weather import fetch_weather
    from solarfit.workers.celery_app import generate_panorama_task, refine_vision_task

    timeout_s = get_async_task_timeout_s()

    # resolve_via_solar_api() only ever reads site.centroid on this code
    # path (no params["address"] is ever passed here) — this cache is
    # site-independent (CACHE-01/03), so there is no real Site yet to
    # hand it. A caller-supplied params["site"] is honoured when present
    # (e.g. a future caller that already has a real Site), otherwise a
    # minimal synthetic one is built from (lat, lng) alone — an
    # unmistakable poison marker for its identity fields, never "unknown",
    # so any future code that starts reading them off this object fails
    # loudly rather than quietly trusting fake data. resolve_via_solar_api
    # only ever reads .centroid here, so the poisoned fields are inert.
    geo_lookup_site = params.get("site") or Site(
        id=f"cache:{lat_r}:{lng_r}",
        site_type=site_type,
        name=_SYNTHETIC_PLACEHOLDER,
        owner_org=_SYNTHETIC_PLACEHOLDER,
        jurisdiction=_SYNTHETIC_PLACEHOLDER,
        centroid={"type": "Point", "coordinates": [lng, lat]},
        created_at=datetime.now(UTC),
    )
    boundary = resolve_via_solar_api(site=geo_lookup_site, params=params)  # GEO

    # VIS-05/OBS-01/OBS-02 — real Celery dispatch, never inline.
    refinement_dict = _await_task(
        refine_vision_task.delay(lat, lng, boundary),
        timeout_s,
        label="vision refinement",
        fallback={"status": "insufficient_data", "obstacles": []},
    )

    weather = fetch_weather(lat=lat, lng=lng)

    # VIZ-05 — real Celery dispatch, never inline, and only when the
    # panorama is switched on at all (see the pack's panorama_enabled).
    panorama = PanoramaResult(status="not_generated", reason="Panorama generation is disabled")
    if get_panorama_enabled():
        panorama = PanoramaResult(
            **_await_task(
                generate_panorama_task.delay(boundary, weather, params),
                timeout_s,
                label="panorama",
                fallback={"status": "not_generated", "reason": "Panorama generation timed out"},
            )
        )

    ml_score = score_with_ml_model(
        boundary=boundary, refinement=refinement_dict, weather=weather, params=params
    )  # ML

    try:
        return create(
            lat_rounded=lat_r,
            lng_rounded=lng_r,
            boundary=boundary,
            vision_refinement=refinement_dict,
            weather_snapshot=weather,
            panorama_url=getattr(panorama, "url", None),
            ml_suitability_score=getattr(ml_score, "score", None),
            ml_model_version=getattr(ml_score, "model_version", None),
        )
    except IntegrityError:
        # CACHE-01's unique (lat_rounded, lng_rounded) constraint caught a
        # concurrent request that inserted this exact location between our
        # find_by_key() above and this insert — that's a hit now, not a
        # crash (CACHE-02/05: a cached location always looks like a hit).
        concurrent_hit = find_by_key(lat_r, lng_r)
        if concurrent_hit is None:
            raise  # not the race we expected — a real bug, don't mask it
        mark_reused(concurrent_hit.reused_from_analysis_id)
        return concurrent_hit
