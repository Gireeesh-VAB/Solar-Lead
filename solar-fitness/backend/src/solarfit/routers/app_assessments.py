"""Owner: omkar (Scoring, USN & Assessment API).

Roadmap workstream "Assessments, frontend-shaped & secured" — 2
endpoints. Wraps routers/assessments.py::orchestrate_assessment()
UNCHANGED (no new computation), adds auth + persistence + a
frontend-shaped response.

Real mapping gaps, flagged not guessed at (per the roadmap's own note):
  - confidence bucket: no threshold exists anywhere upstream — this
    file sets one explicitly (N/A when score is None, High >= 0.7,
    Medium >= 0.4, else Low).
  - bindingConstraint {name, reason, kind}: the backend only has a bare
    constraint-name string; matched against capacity.ceilings to pull
    reason/kind. Gate failures and "insufficient_data:..." sentinels
    aren't in the ceiling list — synthesized as {name, reason: <the
    detail text already on the AssessmentResponse>, kind: "physical"}
    rather than crashing on a lookup miss.
  - visionRefinement.deltaKwp: no such number exists in the backend at
    all — omitted, not sent as a fabricated value.
  - generation {p50AnnualKwh, p90AnnualKwh}: unimplemented backend-wide
    (engine/generation.py is still a placeholder-ratio stub) — omitted
    entirely, same reasoning.
  - cache.originalDate: AnalysisResult (the frozen contract) has no
    created_at field, and repositories/analysis_cache.py exposes no
    public lookup that would provide one without reaching into another
    person's private ORM row — omitted, not hacked around.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from solarfit.auth_users import AuthenticatedUser, current_user, require_role
from solarfit.db import session_scope
from solarfit.domain.constraint import CapacityResult
from solarfit.repositories import assessments as assessments_repo
from solarfit.repositories import sites as sites_repo
from solarfit.routers.assessments import (
    AssessmentResponse,
    SiteNotFoundError,
    orchestrate_assessment,
)

router = APIRouter(tags=["app-assessments"])

ConfidenceLabel = Literal["High", "Medium", "Low", "N/A"]


def _to_camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(word.capitalize() for word in rest)


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)


class BindingConstraintOut(_CamelModel):
    name: str
    reason: str
    kind: str


class AppAssessmentResponse(_CamelModel):
    id: str
    site_id: str
    site_type: str

    verdict: str
    score: float | None
    confidence: ConfidenceLabel
    binding_constraint: BindingConstraintOut
    reasons: list[str]
    limitations: str

    capacity: CapacityResult
    boundary: dict
    usable_area_m2: float | None

    vision_refinement: dict | None
    panorama_url: str | None
    ml_suitability_score: float | None
    ml_model_version: str | None
    cache_hit: bool

    engine_version: str
    constraint_pack_version: str
    created_at: str


class AssessmentListItem(AppAssessmentResponse):
    owner_org: str


def _confidence_label(score: float | None, confidence: float) -> ConfidenceLabel:
    if score is None:
        return "N/A"
    if confidence >= 0.7:
        return "High"
    if confidence >= 0.4:
        return "Medium"
    return "Low"


def _binding_constraint_out(response: AssessmentResponse) -> BindingConstraintOut:
    name = response.binding_constraint
    for ceiling in response.capacity.ceilings:
        if ceiling.constraint == name:
            return BindingConstraintOut(name=name, reason=ceiling.reason, kind=ceiling.kind)
    # Gate failures ("gate:...") and "insufficient_data:..." sentinels
    # aren't in the ceiling list — synthesize from what we do have
    # rather than treating a lookup miss as an error.
    detail = next((r for r in response.reasons if name.split(":")[-1] in r), response.reasons[0])
    return BindingConstraintOut(name=name, reason=detail, kind="physical")


def _to_app_response(row_id: str, response: AssessmentResponse, created_at) -> AppAssessmentResponse:
    return AppAssessmentResponse(
        id=row_id,
        site_id=response.site_id,
        site_type=response.site_type,
        verdict=response.verdict,
        score=response.score,
        confidence=_confidence_label(response.score, response.confidence),
        binding_constraint=_binding_constraint_out(response),
        reasons=response.reasons,
        limitations=response.limitations,
        capacity=response.capacity,
        boundary=response.boundary,
        usable_area_m2=response.usable_area_m2,
        vision_refinement=response.vision_refinement.model_dump() if response.vision_refinement else None,
        panorama_url=response.panorama_url,
        ml_suitability_score=response.ml_suitability_score,
        ml_model_version=response.ml_model_version,
        cache_hit=response.cache_hit,
        engine_version=response.engine_version,
        constraint_pack_version=response.constraint_pack_version,
        created_at=created_at.isoformat(),
    )


@router.post("/app/assessments/{site_id}", response_model=AppAssessmentResponse)
def post_app_assessment(
    site_id: str,
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> AppAssessmentResponse:
    """Runs the real engine unchanged, then persists the result.
    A customer may only assess their own org's sites; an admin may
    assess any site — mirrors repositories/sites.py::list_sites()'s
    owner_org-scoping pattern already established for GET /app/sites."""
    with session_scope() as read_session:
        site = sites_repo.get(read_session, site_id)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Site {site_id} not found")
    if user.role != "admin" and site.owner_org != user.owner_org:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Site {site_id} not found")

    try:
        response = orchestrate_assessment(site_id)
    except SiteNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    with session_scope() as session:
        row = assessments_repo.save_assessment(
            session,
            owner_org=site.owner_org,
            **response.model_dump(),
        )
        session.commit()
        row_id, created_at = row.id, row.created_at

    return _to_app_response(row_id, response, created_at)


@router.get("/app/admin/assessments", response_model=list[AssessmentListItem])
def list_all_assessments(
    user: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
    limit: int = 50,
    offset: int = 0,
) -> list[AssessmentListItem]:
    """Cross-org, admin-only — reads the table post_app_assessment()
    writes above."""
    del user
    with session_scope() as session:
        rows = assessments_repo.list_assessments(session, owner_org=None, limit=limit, offset=offset)
        results = []
        for row in rows:
            response = AssessmentResponse(
                site_id=row.site_id,
                site_type=row.site_type,
                verdict=row.verdict,
                score=row.score,
                confidence=row.confidence,
                binding_constraint=row.binding_constraint,
                reasons=row.reasons,
                limitations=row.limitations,
                capacity=CapacityResult(**row.capacity),
                boundary=row.boundary,
                usable_area_m2=row.usable_area_m2,
                vision_refinement=row.vision_refinement,
                panorama_url=row.panorama_url,
                ml_suitability_score=row.ml_suitability_score,
                ml_model_version=row.ml_model_version,
                cache_hit=row.cache_hit,
                reused_from_analysis_id=row.reused_from_analysis_id,
                usn=row.usn,
                engine_version=row.engine_version,
                constraint_pack_version=row.constraint_pack_version,
            )
            item = _to_app_response(row.id, response, row.created_at)
            results.append(AssessmentListItem(owner_org=row.owner_org, **item.model_dump(by_alias=False)))
        return results
