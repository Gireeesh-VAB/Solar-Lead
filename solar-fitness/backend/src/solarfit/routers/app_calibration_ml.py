"""Owner: omkar (Scoring, USN & Assessment API).

Roadmap workstream "Calibration & ML approval" — 4 endpoints closing the
propose-with-no-approve gap in repositories/calibration.py and
engine/ml_score.py. Admin-only, mirrors routers/app_auth.py's
_CamelModel convention so JSON keys match lib/types.ts.

Real product mismatch, flagged not silently fitted: the frontend
imagines a per-jurisdiction "remote vs. measured" variance record; the
backend tracks a per-site-type utilisation-factor correction instead.
This router maps the closest honest fields (site_type, not jurisdiction)
rather than inventing a dimension the data doesn't have.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from solarfit.auth_users import AuthenticatedUser, require_role
from solarfit.engine import ml_score as ml_score_engine
from solarfit.repositories import calibration as calibration_repo

router = APIRouter(prefix="/app/admin", tags=["app-admin-calibration-ml"])


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class CalibrationProposalActionResponse(_CamelModel):
    proposal_id: str
    site_type: str
    status: str
    reviewed_by: str | None


class ModelVersionActionResponse(_CamelModel):
    version_id: str
    version: str
    status: str


class CalibrationProposalOut(_CamelModel):
    id: str
    jurisdiction: str
    metric: str
    remote_value: float
    measured_value: float
    variance_pct: float
    sample_size: int
    proposed_adjustment: str
    status: str
    proposed_at: str
    proposed_by: str


class ModelMetricOut(_CamelModel):
    label: str
    value: str


class ModelVersionOut(_CamelModel):
    id: str
    model_name: str
    version: str
    status: str
    metrics: list[ModelMetricOut]
    proposed_at: str
    proposed_by: str
    changelog: str


@router.get("/calibration-proposals", response_model=list[CalibrationProposalOut])
def list_calibration_proposals(
    _user: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> list[CalibrationProposalOut]:
    proposals = calibration_repo.list_utilisation_factor_proposals()
    return [
        CalibrationProposalOut(
            id=p["id"],
            jurisdiction=p["jurisdiction"],
            metric=p["metric"],
            remote_value=p["remote_value"],
            measured_value=p["measured_value"],
            variance_pct=p["variance_pct"],
            sample_size=p["sample_size"],
            proposed_adjustment=p["proposed_adjustment"],
            status=p["status"],
            proposed_at=p["proposed_at"].isoformat(),
            proposed_by=p["proposed_by"],
        )
        for p in proposals
    ]


@router.get("/model-versions", response_model=list[ModelVersionOut])
def list_model_versions(
    _user: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> list[ModelVersionOut]:
    versions = ml_score_engine.list_model_versions()
    return [
        ModelVersionOut(
            id=v["id"],
            model_name=v["model_name"],
            version=v["version"],
            status=v["status"],
            metrics=[ModelMetricOut(**m) for m in v["metrics"]],
            proposed_at=v["proposed_at"].isoformat(),
            proposed_by=v["proposed_by"],
            changelog=v["changelog"],
        )
        for v in versions
    ]


@router.post(
    "/calibration-proposals/{proposal_id}/approve",
    response_model=CalibrationProposalActionResponse,
)
def approve_calibration_proposal(
    proposal_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> CalibrationProposalActionResponse:
    try:
        result = calibration_repo.approve_utilisation_factor_proposal(proposal_id, approved_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return CalibrationProposalActionResponse(**result)


@router.post(
    "/calibration-proposals/{proposal_id}/reject",
    response_model=CalibrationProposalActionResponse,
)
def reject_calibration_proposal(
    proposal_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> CalibrationProposalActionResponse:
    try:
        result = calibration_repo.reject_utilisation_factor_proposal(proposal_id, rejected_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return CalibrationProposalActionResponse(**result)


@router.post("/model-versions/{version_id}/approve", response_model=ModelVersionActionResponse)
def approve_model_version(
    version_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> ModelVersionActionResponse:
    try:
        result = ml_score_engine.approve_model_version(version_id, approved_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return ModelVersionActionResponse(**result)


@router.post("/model-versions/{version_id}/reject", response_model=ModelVersionActionResponse)
def reject_model_version(
    version_id: str,
    user: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> ModelVersionActionResponse:
    try:
        result = ml_score_engine.reject_model_version(version_id, rejected_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return ModelVersionActionResponse(**result)
