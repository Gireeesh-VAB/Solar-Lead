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
