"""STUB — Owner: Person 4 (Scoring, USN & Assessment API).

Implements §9.13 ML Suitability Model (ML-01..05) of
Solar_Fitness_Engine_Development_Document_v1.1 — additive metadata
only; NEVER a replacement for engine/fitness.py's FIT verdict (§17).

  ML-01  Compute/store ml_suitability_score alongside, never instead of, FIT.
  ML-02  Record the model version against every stored score.
  ML-03  Retrain only as an offline/scheduled job — never from the
         request path.
  ML-04  New model versions require approval before becoming the active
         scorer (mirrors CAL-03's "propose, don't apply silently").
  ML-05  Missing mandatory upstream inputs -> insufficient_data, never a
         fabricated number.

Depends on: solarfit.domain.assessment.MLScore (frozen, Day 0).

Add scikit-learn / xgboost to apps/api/pyproject.toml when you start
this (uv add scikit-learn xgboost) — deliberately not pre-installed by
the Day-0 foundation.
"""

from solarfit.domain.assessment import MLScore


def score_with_ml_model(
    boundary: dict, refinement: dict | None, weather: dict | None, params: dict | None = None
) -> MLScore:
    """ML-01..05. Raises NotImplementedError until Person 4 implements it."""
    raise NotImplementedError


def train() -> None:
    """ML-03. Offline/scheduled training entrypoint — never called from
    the request path."""
    raise NotImplementedError
