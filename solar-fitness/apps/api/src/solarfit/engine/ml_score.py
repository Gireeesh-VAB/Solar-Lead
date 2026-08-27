"""Owner: Person 4 (Scoring, USN & Assessment API).

Implements §9.13 ML Suitability Model (ML-01..05) of
Solar_Fitness_Engine_Development_Document_v1.2 — tasks 10 and 11 of
Person 4's list in Rooftop_Backend_Implementation_Plan.html:

  ML-01  Compute/store ml_suitability_score alongside, never instead of, FIT.
         Offline training script over GEO/AREA (boundary) / VIS
         (refinement) / weather features, with FIT/CAL as labels.
  ML-02  Record the model version against every stored score.
  ML-03  Retrain only as an offline/scheduled job — never from the
         request path.
  ML-04  New model versions require approval before becoming the active
         scorer (mirrors CAL-03's "propose, don't apply silently").
  ML-05  Missing mandatory upstream inputs -> insufficient_data, never a
         fabricated number.

This is additive metadata only — NEVER a replacement for
engine/fitness.py's FIT verdict (§17). Enforced structurally: this
module never imports engine/fitness.py, and vice versa (checked by a
structural test in tests/test_ml_score.py).

Design notes (flagged, not silent):
  - Model choice is scikit-learn's HistGradientBoostingRegressor, not
    XGBoost, despite this stub's own earlier docstring suggesting
    `uv add scikit-learn xgboost`. The spec text says "(scikit-learn/
    XGBoost)" — an explicit either/or. HistGradientBoostingRegressor
    natively handles missing values (NaN) with no separate imputation
    step and avoids a second heavy native-code dependency.
  - train()'s return type is widened from the stub's original `-> None`
    to `dict | None` — a training job that returns nothing gives the
    caller (and tests) no way to observe what happened. None remains a
    valid, meaningful return (insufficient data), matching
    repositories/calibration.py's propose_utilisation_factor_update
    precedent.
  - No orchestration endpoint exists yet to produce real (features,
    label) training pairs — record_training_sample() is built and
    ready, but nothing calls it automatically. Wired in once
    routers/assessments.py (Phase 3) exists.
  - ml_suitability_score is scored 0..100, deliberately a different
    scale from FitnessResult.score's 0..1 — no spec text pins either
    scale, and keeping them visually distinct reinforces that the two
    are not directly comparable or substitutable.
  - Model versions are NOT scoped per site_type (unlike FIT's
    per-site-type config) — one single globally-active model. No text
    in ML-01..05 suggests a per-site-type split; flagged for override
    if that assumption is wrong.

Depends on: solarfit.domain.assessment.MLScore (frozen, Day 0),
solarfit.repositories.ml_models (this person's own, same task).
"""

from __future__ import annotations

import io
from datetime import UTC, datetime

import joblib
import numpy as np
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import GridSearchCV, GroupKFold, GroupShuffleSplit

from solarfit.config import get_settings
from solarfit.db import get_session
from solarfit.domain.assessment import MLScore
from solarfit.packs.config_pack import (
    get_ml_cv_max_folds,
    get_ml_min_training_groups,
    get_ml_test_split_fraction,
)
from solarfit.repositories import ml_models as ml_models_repo

FEATURE_NAMES = [
    "boundary_area",
    "vertex_count",
    "vision_confidence",
    "has_vision_data",
    "obstacle_count",
    "obstruction_note_count",
    "irradiance",
    "cloud_cover",
    "temperature",
]

DEFAULT_PARAM_GRID = {
    "max_iter": [50, 100],
    "max_depth": [3, 5],
    "learning_rate": [0.05, 0.1],
}

MAX_MISSING_FEATURES_ALLOWED = 3  # of len(FEATURE_NAMES)


# ---------------------------------------------------------------------------
# Feature extraction — shared between train() and score_with_ml_model()
# ---------------------------------------------------------------------------


def _as_float(value: object) -> float | None:
    return float(value) if value is not None else None  # type: ignore[arg-type]


def _polygon_area_and_vertex_count(boundary: dict) -> tuple[float, int]:
    """A relative ML feature computed via the shoelace formula on raw
    GeoJSON coordinates — NOT a geodetically-correct area (that
    authority stays with Person 1's engine/area.py). Fine for ranking/
    correlation, not an official figure."""
    if boundary.get("type") != "Polygon":
        return 0.0, 0
    rings = boundary.get("coordinates") or []
    if not rings:
        return 0.0, 0
    exterior = rings[0]
    n = len(exterior)
    if n < 3:
        return 0.0, n
    area = 0.0
    for i in range(n):
        x1, y1 = exterior[i][0], exterior[i][1]
        x2, y2 = exterior[(i + 1) % n][0], exterior[(i + 1) % n][1]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0, n


def extract_features(
    boundary: dict, refinement: dict | None, weather: dict | None
) -> dict[str, float | None]:
    """ML-01's GEO/AREA/VIS/weather feature set. A single function
    imported by both train() and score_with_ml_model() — see
    test_ml_score.py's train/serve parity test. Missing values are
    None, never a fabricated default."""
    area, vertex_count = _polygon_area_and_vertex_count(boundary)
    refinement = refinement or {}
    weather = weather or {}

    return {
        "boundary_area": area,
        "vertex_count": float(vertex_count),
        "vision_confidence": _as_float(refinement.get("confidence")),
        "has_vision_data": 1.0 if refinement.get("confidence") is not None else 0.0,
        "obstacle_count": float(len(refinement.get("obstacles") or [])),
        "obstruction_note_count": float(len(refinement.get("obstruction_notes") or [])),
        "irradiance": _as_float(weather.get("irradiance")),
        "cloud_cover": _as_float(weather.get("cloud_cover")),
        "temperature": _as_float(weather.get("temperature")),
    }


def _features_to_matrix(feature_dicts: list[dict[str, float | None]]) -> np.ndarray:
    """None -> NaN only here, at matrix-build time — never manually
    imputed, since HistGradientBoostingRegressor handles NaN natively."""
    return np.array(
        [[row.get(name, np.nan) if row.get(name) is not None else np.nan for name in FEATURE_NAMES] for row in feature_dicts],
        dtype=float,
    )


def record_training_sample(
    site_id: str,
    boundary: dict,
    refinement: dict | None,
    weather: dict | None,
    *,
    label_source: str,
    label_value: float,
) -> str:
    """ML-01. Not called automatically by anything yet — see module
    docstring. Returns the new sample's id."""
    features = extract_features(boundary, refinement, weather)
    with get_session() as session:
        sample = ml_models_repo.save_training_sample(
            session,
            site_id=site_id,
            features=features,
            label_source=label_source,
            label_value=label_value,
        )
        session.commit()
        return sample.id


# ---------------------------------------------------------------------------
# Object storage — model artifacts. Same lazy-construction, monkeypatch-
# friendly shape as providers/usn_ocr.py's helpers.
# ---------------------------------------------------------------------------


def _object_storage_client():
    import boto3

    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.object_storage_endpoint_url or None,
        aws_access_key_id=settings.object_storage_access_key or None,
        aws_secret_access_key=settings.object_storage_secret_key or None,
    )


def _upload_model_artifact(key: str, data: bytes) -> None:
    settings = get_settings()
    _object_storage_client().put_object(Bucket=settings.object_storage_bucket, Key=key, Body=data)


def _download_model_artifact(key: str) -> bytes:
    settings = get_settings()
    response = _object_storage_client().get_object(Bucket=settings.object_storage_bucket, Key=key)
    return response["Body"].read()


def _serialize_model(model) -> bytes:
    """joblib's dump()/load() are file-like, not dumps()/loads() —
    route through an in-memory buffer to get plain bytes."""
    buffer = io.BytesIO()
    joblib.dump(model, buffer)
    return buffer.getvalue()


def _deserialize_model(data: bytes):
    return joblib.load(io.BytesIO(data))


# ---------------------------------------------------------------------------
# Task 10 — ML-01, offline training
# ---------------------------------------------------------------------------


def train(*, param_grid: dict | None = None) -> dict | None:
    """ML-01/03. Offline/scheduled only — never called from the request
    path. Returns None when there isn't enough accumulated data yet;
    a summary dict (including a candidate-vs-baseline comparison) once
    a candidate has been proposed."""
    with get_session() as session:
        samples = ml_models_repo.get_all_training_samples(session)

    if not samples:
        return None

    site_ids = np.array([s.site_id for s in samples])
    group_count = len(set(site_ids))
    if group_count < get_ml_min_training_groups():
        return None

    X = _features_to_matrix([s.features for s in samples])
    y = np.array([s.label_value for s in samples], dtype=float)

    test_fraction = get_ml_test_split_fraction()
    splitter = GroupShuffleSplit(n_splits=1, test_size=test_fraction, random_state=42)
    trainval_idx, test_idx = next(splitter.split(X, y, groups=site_ids))

    X_trainval, y_trainval, groups_trainval = X[trainval_idx], y[trainval_idx], site_ids[trainval_idx]
    X_test, y_test = X[test_idx], y[test_idx]

    trainval_group_count = len(set(groups_trainval))
    max_folds = min(get_ml_cv_max_folds(), trainval_group_count)
    grid = param_grid or DEFAULT_PARAM_GRID

    cv_results: dict | None
    cv_skipped_reason: str | None
    if max_folds >= 2:
        cv = GroupKFold(n_splits=max_folds)
        search = GridSearchCV(
            HistGradientBoostingRegressor(random_state=42),
            grid,
            cv=cv,
            scoring="neg_mean_absolute_error",
        )
        search.fit(X_trainval, y_trainval, groups=groups_trainval)
        best_params = search.best_params_
        cv_results = {"best_score_neg_mae": float(search.best_score_), "folds": max_folds}
        cv_skipped_reason = None
    else:
        cv_skipped_reason = f"only {trainval_group_count} group(s) available for cross-validation"
        best_params = {name: values[0] for name, values in grid.items()}
        cv_results = None

    candidate = HistGradientBoostingRegressor(random_state=42, **best_params)
    candidate.fit(X_trainval, y_trainval)

    baseline = DummyRegressor(strategy="mean")
    baseline.fit(X_trainval, y_trainval)

    if len(X_test):
        candidate_predictions = candidate.predict(X_test)
        baseline_predictions = baseline.predict(X_test)
        test_mae = float(mean_absolute_error(y_test, candidate_predictions))
        baseline_mae = float(mean_absolute_error(y_test, baseline_predictions))
        test_r2 = float(r2_score(y_test, candidate_predictions)) if len(X_test) > 1 else None
        baseline_r2 = float(r2_score(y_test, baseline_predictions)) if len(X_test) > 1 else None
        beats_baseline = test_mae < baseline_mae
    else:
        test_mae = test_r2 = baseline_mae = baseline_r2 = beats_baseline = None

    # Final artifact is refit on the full dataset (train+val+test) using
    # the hyperparameters selected/evaluated above — standard practice
    # once test-set metrics are already captured, so the deployed model
    # isn't needlessly starved of the held-out test rows.
    final_model = HistGradientBoostingRegressor(random_state=42, **best_params)
    final_model.fit(X, y)

    version = f"ml_v_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}"
    storage_key = f"ml-models/{version}.joblib"
    _upload_model_artifact(storage_key, _serialize_model(final_model))

    metrics = {
        "test_mae": test_mae,
        "test_r2": test_r2,
        "baseline_mae": baseline_mae,
        "baseline_r2": baseline_r2,
        "beats_baseline": beats_baseline,
        "cv_results": cv_results,
        "cv_skipped_reason": cv_skipped_reason,
        "cv_folds": max_folds if cv_results else 0,
    }

    with get_session() as session:
        row = ml_models_repo.save_model_version(
            session,
            version=version,
            feature_list=FEATURE_NAMES,
            hyperparameters=best_params,
            metrics=metrics,
            artifact_storage_key=storage_key,
            sample_count=len(samples),
            group_count=group_count,
        )
        session.commit()
        version_id = row.id

    return {
        "version_id": version_id,
        "version": version,
        "status": "proposed",
        "sample_count": len(samples),
        "group_count": group_count,
        "metrics": metrics,
    }


# ---------------------------------------------------------------------------
# Task 11 — ML-02/03/04/05, versioned inference + approval gate
# ---------------------------------------------------------------------------


def approve_model_version(version_id: str, approved_by: str) -> dict:
    """ML-04. Single globally-active model — demotes any previously
    approved version to "rejected"."""
    with get_session() as session:
        row = ml_models_repo.approve_version(session, version_id, approved_by)
        session.commit()
        return {"version_id": row.id, "version": row.version, "status": row.status}


def score_with_ml_model(
    boundary: dict, refinement: dict | None, weather: dict | None, params: dict | None = None
) -> MLScore:
    """ML-01/02/05. Never trains, never imports engine/fitness.py."""
    del params  # no use yet — kept for signature stability with future callers

    with get_session() as session:
        approved = ml_models_repo.get_approved_model_version(session)
        if approved is None:
            return MLScore(status="insufficient_data", score=None, model_version=None)

        features = extract_features(boundary, refinement, weather)
        missing_count = sum(1 for name in FEATURE_NAMES if features.get(name) is None)
        if missing_count > MAX_MISSING_FEATURES_ALLOWED:
            return MLScore(status="insufficient_data", score=None, model_version=approved.version)

        artifact_key = approved.artifact_storage_key
        model_version = approved.version

    model = _deserialize_model(_download_model_artifact(artifact_key))
    prediction = float(model.predict(_features_to_matrix([features]))[0])
    score = max(0.0, min(100.0, prediction))

    return MLScore(score=score, model_version=model_version, status="ok")
