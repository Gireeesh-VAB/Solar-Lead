"""Owner: Person 4 (Scoring, USN & Assessment API).

Implements the core-assessment slice of §9.8 Interface (API-01..05) of
Solar_Fitness_Engine_Development_Document_v1.2 — tasks 12 and 13 of
Person 4's list in Rooftop_Backend_Implementation_Plan.html:

  Task 12 (API-01/02): orchestration endpoint combining Person 1/2/3's
    outputs into the single response shape, with vision_refinement/
    panorama_url/ml_suitability_score/cache_hit as optional additive
    fields; synchronous cache-hit path.
  Task 13 (API-03/04/05): async batch submission with pollable status;
    engine/pack version stamped on every response; versioned API path.

Two corrections found by re-reading the frozen contracts directly
(superseding earlier phases' assumptions):
  - CapacityResult has no pack_version field — constraint_pack_version
    comes from packs.config_pack.pack_version() instead.
  - AnalysisResult has no weather field — record_training_sample() (see
    below) fetches weather separately via providers.weather.fetch_weather()
    rather than trying to pull it off the cached analysis.

This is deliberately the last piece wired to real implementations — it
calls directly into every other person's still-stub module with no
try/except NotImplementedError anywhere, matching the rest of this
codebase's philosophy: a not-yet-built dependency should raise loudly,
not be silently worked around. Tests monkeypatch every dependency, same
discipline as engine/fitness.py, providers/usn_ocr.py, and
repositories/calibration.py's own test suites.

USN capture's HTTP surface (upload/confirm endpoints) is NOT part of
tasks 12/13 and stays out of scope here — a real, still-open gap, not
silently absorbed into this router.

Depends on: solarfit.domain.assessment.AnalysisResult (frozen, Day 0),
solarfit.repositories.analysis_cache.get_or_create_analysis (Person 3),
solarfit.packs.{universal,rooftop} + engine.resolver + engine.generation
(Person 2), solarfit.engine.fitness / engine.ml_score /
repositories.calibration (this person's own modules).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from solarfit import __version__ as engine_version
from solarfit.auth import current_org
from solarfit.db import session_scope
from solarfit.domain.assessment import FitnessVerdict, VisionRefinement
from solarfit.domain.constraint import CapacityResult
from solarfit.domain.site import RoofSiteType, UsnCapture
from solarfit.engine import fitness, generation, resolver
from solarfit.engine import ml_score as ml_score_engine
from solarfit.engine.area import compute_usable_area_m2
from solarfit.engine.consumption import estimate_annual_consumption
from solarfit.packs import config_pack, rooftop, universal
from solarfit.packs.config_pack import pack_version
from solarfit.providers import weather as weather_provider
from solarfit.providers.validation import GeometryRejected
from solarfit.repositories import analysis_cache as analysis_cache_repo
from solarfit.repositories import calibration
from solarfit.repositories import sites as sites_repo
from solarfit.workers.celery_app import celery_app

router = APIRouter(prefix="/v1/assessments", tags=["assessments"])


class SiteNotFoundError(Exception):
    pass


class AssessmentResponse(BaseModel):
    site_id: str
    site_type: RoofSiteType

    verdict: FitnessVerdict
    score: float | None
    confidence: float
    binding_constraint: str
    reasons: list[str]
    limitations: str

    capacity: CapacityResult
    boundary: dict
    usable_area_m2: float | None

    # Optional, additive per API-01 — never required, never displacing the above.
    vision_refinement: VisionRefinement | None = None
    panorama_url: str | None = None
    ml_suitability_score: float | None = None
    ml_model_version: str | None = None
    cache_hit: bool = False
    reused_from_analysis_id: str | None = None
    usn: UsnCapture | None = None

    engine_version: str  # API-04
    constraint_pack_version: str  # API-04


def _collect_ceilings_and_gates(
    site, usable_area_m2: float, annual_consumption_kwh: float | None = None
) -> tuple[list, list]:
    """Rooftop-only product — both packs apply uniformly, no site-type
    conditionals here (matches §17's resolver discipline).

    `annual_consumption_kwh` is CON-05's input, derived from the
    customer's own bill by engine/consumption.py. Passing None leaves
    consumption_offset at insufficient_data, which is what every
    assessment did before a bill could be captured: the system was then
    sized by roof area alone, and a household came back at tens of kWp it
    could never use.
    """
    consumption_params = (
        {"annual_consumption_kwh": annual_consumption_kwh}
        if annual_consumption_kwh is not None
        else {}
    )
    ceilings = [
        universal.usable_area_ceiling(site, usable_area_m2),
        universal.evacuation_headroom_ceiling(site, {}),
        rooftop.net_metering_cap(site, {}),
        rooftop.consumption_offset_ceiling(site, consumption_params),
        rooftop.transformer_headroom_ceiling(site, {}),
        rooftop.subsidy_tier_cap(site, {}),  # already reads site.usn internally
    ]
    gates = [
        universal.minimum_viable_size_gate(site, usable_area_m2),
        rooftop.structural_gate(site, {}),
    ]
    return ceilings, gates


def orchestrate_assessment(site_id: str, owner_org: str | None = None) -> AssessmentResponse:
    """API-01/02. Capacity and fitness are recomputed fresh on every
    call, even when analysis.cache_hit is True — only geometry/vision/
    weather/panorama/ml are reused from Person 3's cache; capacity and
    fitness depend on site-specific things (subsidy tier, jurisdiction)
    the cache key doesn't capture.

    `owner_org` is optional so internal callers without tenant context
    (this module's own tests calling this function directly) don't need
    one — every real HTTP route always passes the caller's real
    owner_org from API-06's current_org dependency. 404, never 403, for
    another tenant's site — same reasoning as routers/sites.py's
    _owned_or_404: confirming the id exists at all is itself a leak.
    """
    with session_scope() as session:
        site = sites_repo.get(session, site_id)
        # CON-05's input, read here rather than in a second session. Kept
        # off the domain Site because that contract is frozen Day 0 and
        # only the capacity path below needs it.
        bill_low, bill_high = sites_repo.get_bill_range(session, site_id)
    if site is None or (owner_org is not None and site.owner_org != owner_org):
        raise SiteNotFoundError(f"Site {site_id} not found")

    lng, lat = site.centroid["coordinates"]

    analysis = analysis_cache_repo.get_or_create_analysis(lat, lng, site.site_type, params={})

    # OBS-04/05/07 — classify and (above threshold) auto-apply this
    # site's detected obstacles via the real async task, dispatched
    # against this site's real id (never the cache's site-independent
    # synthetic one — see analysis_cache.py's own note on why that broke
    # auto-apply entirely). Idempotent per site
    # (repositories/sites.py::applied_obstacle_ids), so replaying the
    # same cached detection on every assessment call is safe and cheap
    # once a site has already picked up what applies to it.
    if analysis.vision_refinement and analysis.vision_refinement.obstacles:
        from solarfit.domain.assessment import Obstacle
        from solarfit.workers.celery_app import apply_obstacles_task

        obstacles_payload = [o.model_dump() for o in analysis.vision_refinement.obstacles]
        task_result = apply_obstacles_task.delay(site.id, obstacles_payload).get(
            timeout=config_pack.get_async_task_timeout_s()
        )
        analysis.vision_refinement.obstacles = [Obstacle(**o) for o in task_result["obstacles"]]
        # Pick up any exclusion the apply just persisted before computing
        # usable area below.
        with session_scope() as session:
            site = sites_repo.get(session, site_id)

    # AREA-01..06 — usable_area_m2 isn't a cached field (see
    # analysis_cache.py::_row_to_result's own docstring: it's deliberately
    # left None there so a config-pack coefficient change picks up
    # immediately without needing to invalidate anything). It has to be
    # computed here, fresh, on every call — against the pipeline-resolved
    # boundary (analysis.boundary, which went through VIS/OBS refinement)
    # combined with this site's own persisted exclusions. Previously this
    # read analysis.usable_area_m2 directly, which is always None, so
    # every real (non-mocked) assessment silently computed capacity
    # against a usable area of 0.0.
    usable_site = site.model_copy(update={"boundary": analysis.boundary})
    usable_area_m2 = compute_usable_area_m2(usable_site)

    # CON-05 — the customer's own bill, converted to annual units.
    consumption = estimate_annual_consumption(bill_low, bill_high)

    ceilings, gates = _collect_ceilings_and_gates(
        site, usable_area_m2, consumption.annual_kwh if consumption else None
    )
    capacity = resolver.resolve_capacity(ceilings)

    generation_estimate = (
        generation.estimate_generation_kwh(site, capacity.recommended_kwp)
        if capacity.recommended_kwp
        else None
    )

    # CAL-05 — wired in for real (was flagged "not wired into the router
    # yet" when repositories/calibration.py was built).
    calibration_state = calibration.get_calibration_confidence_adjustment(
        site.site_type, site.geometry_source
    )

    fitness_result = fitness.score_fitness(
        site,
        capacity,
        params={
            "gates": gates,
            "generation": generation_estimate,
            "calibration_state": calibration_state,
        },
    )

    # ML-01 training-sample capture — wired in for real (was flagged
    # "not called by anything yet" when engine/ml_score.py was built).
    if fitness_result.score is not None:
        weather = weather_provider.fetch_weather(lat, lng)
        ml_score_engine.record_training_sample(
            site.id,
            analysis.boundary,
            analysis.vision_refinement.model_dump() if analysis.vision_refinement else None,
            weather,
            label_source="fit_score",
            label_value=fitness_result.score,
        )

    return AssessmentResponse(
        site_id=site.id,
        site_type=site.site_type,
        verdict=fitness_result.verdict,
        score=fitness_result.score,
        confidence=fitness_result.confidence,
        binding_constraint=fitness_result.binding_constraint,
        reasons=fitness_result.reasons,
        limitations=fitness_result.limitations,
        capacity=capacity,
        boundary=analysis.boundary,
        usable_area_m2=usable_area_m2,
        vision_refinement=analysis.vision_refinement,
        panorama_url=analysis.panorama.url if analysis.panorama else None,
        ml_suitability_score=analysis.ml_score.score if analysis.ml_score else None,
        ml_model_version=analysis.ml_score.model_version if analysis.ml_score else None,
        cache_hit=analysis.cache_hit,
        reused_from_analysis_id=analysis.reused_from_analysis_id,
        usn=site.usn,
        engine_version=engine_version,
        constraint_pack_version=pack_version(),
    )


# ---------------------------------------------------------------------------
# API-03 — async batch submission with pollable status.
#
# Registered BEFORE POST /{site_id} below: FastAPI/Starlette matches
# routes in registration order, and "/batch" would otherwise be
# captured by the "/{site_id}" path parameter first (site_id="batch"),
# never reaching this route at all.
# ---------------------------------------------------------------------------


class BatchSubmitRequest(BaseModel):
    site_ids: list[str]


class BatchSubmitResponse(BaseModel):
    job_id: str


class BatchStatusResponse(BaseModel):
    job_id: str
    status: str
    results: list[dict] | None = None


@router.post("/batch", response_model=BatchSubmitResponse)
def post_batch_assessment(
    body: BatchSubmitRequest,
    owner_org: Annotated[str, Depends(current_org)],
) -> BatchSubmitResponse:
    from solarfit.workers.tasks_assessments import run_batch_assessment

    # API-06 tenant scoping for a batch: every site_id must belong to the
    # caller before anything is enqueued — otherwise an authenticated
    # caller from one tenant could assess another tenant's sites just by
    # guessing/enumerating ids. 404, not 403, for the same reason
    # _owned_or_404 uses one in sites.py.
    with session_scope() as session:
        for site_id in body.site_ids:
            site = sites_repo.get(session, site_id)
            if site is None or site.owner_org != owner_org:
                raise HTTPException(status_code=404, detail=f"Site {site_id} not found")

    task = run_batch_assessment.delay(body.site_ids)
    return BatchSubmitResponse(job_id=task.id)


@router.get("/batch/{job_id}", response_model=BatchStatusResponse)
def get_batch_assessment_status(
    job_id: str,
    _owner_org: Annotated[str, Depends(current_org)],
) -> BatchStatusResponse:
    """API-06 requires authentication here, but not full per-job tenant
    scoping: a batch job's id isn't recorded against the owner_org that
    submitted it anywhere today, so any authenticated caller who knows
    (or brute-forces) a job_id can currently poll its status. job_id
    itself is an unguessable Celery UUID, which limits the practical
    exposure, but this is a real, narrower gap than full ownership
    checking — flagged here rather than silently treated as closed."""
    async_result = celery_app.AsyncResult(job_id)
    return BatchStatusResponse(
        job_id=job_id,
        status=async_result.status,
        results=async_result.result if async_result.successful() else None,
    )


@router.post("/{site_id}", response_model=AssessmentResponse)
def post_assessment(
    site_id: str,
    owner_org: Annotated[str, Depends(current_org)],
) -> AssessmentResponse:
    try:
        return orchestrate_assessment(site_id, owner_org)
    except SiteNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except GeometryRejected as e:
        # GEO-04: absent Solar API coverage is a recordable outcome, not a
        # server fault. Google covers India building-by-building, so this
        # is the common case here rather than an edge one — a 500 both
        # misreports it as our bug and leaves the caller with nothing
        # actionable. The site still exists; it just needs geometry from a
        # source that outranks solar_api (GEO-02 manual trace, GEO-05
        # import, GEO-06 field measurement).
        raise HTTPException(
            status_code=422,
            detail=(
                f"{e} — this location has no automatic roof data. Trace the "
                "roof boundary manually to continue."
            ),
        ) from e
