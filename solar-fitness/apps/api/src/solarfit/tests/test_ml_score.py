"""Tests for engine/ml_score.py + repositories/ml_models.py — §9.13 ML
Suitability Model (ML-01..05), tasks 10 and 11 of Person 4's list.

DB-touching tests run against an in-memory SQLite database (via the
sqlite_engine fixture), same pattern as the USN/calibration test files.
Object storage is a real (in-memory, monkeypatched) upload/download
round-trip rather than a no-op, so score_with_ml_model() can actually
load back a model trained earlier in the same test — no real S3/network
calls either way.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.orm import sessionmaker

from solarfit.engine import ml_score
from solarfit.repositories.ml_models import MLModelVersion, MLTrainingSample


@pytest.fixture
def ml_session_factory(sqlite_engine, monkeypatch):
    MLTrainingSample.metadata.create_all(
        sqlite_engine, tables=[MLTrainingSample.__table__, MLModelVersion.__table__]
    )
    session_local = sessionmaker(bind=sqlite_engine)
    monkeypatch.setattr(ml_score, "get_session", lambda: session_local())
    return session_local


@pytest.fixture
def fake_object_storage(monkeypatch):
    """In-memory store standing in for S3 — a real upload/download
    round-trip within a test, never a real network call."""
    store: dict[str, bytes] = {}
    monkeypatch.setattr(ml_score, "_upload_model_artifact", lambda key, data: store.__setitem__(key, data))
    monkeypatch.setattr(ml_score, "_download_model_artifact", lambda key: store[key])
    return store


SAMPLE_BOUNDARY = {
    "type": "Polygon",
    "coordinates": [[[0, 0], [0, 10], [10, 10], [10, 0], [0, 0]]],
}
SAMPLE_REFINEMENT = {"confidence": 0.9, "obstacles": [{"type": "vent"}], "obstruction_notes": ["shadow on east edge"]}
SAMPLE_WEATHER = {"irradiance": 850.0, "cloud_cover": 15.0, "temperature": 28.0}


def _seed_samples(session_factory, n_groups: int, *, area_start: float = 100.0, area_step: float = 5.0) -> None:
    """Seeds n_groups distinct site_id groups, 3 rows each, with a
    label deterministically related to a feature (boundary_area) so a
    real model has something learnable to fit."""
    with session_factory() as session:
        for g in range(n_groups):
            area = area_start + g * area_step
            features = {
                "boundary_area": area,
                "vertex_count": 4.0,
                "vision_confidence": 0.85,
                "has_vision_data": 1.0,
                "obstacle_count": 0.0,
                "obstruction_note_count": 0.0,
                "irradiance": 800.0,
                "cloud_cover": 20.0,
                "temperature": 30.0,
            }
            for _ in range(3):
                session.add(
                    MLTrainingSample(
                        id=str(uuid4()),
                        site_id=f"site-{g}",
                        features=features,
                        label_source="fit_score",
                        label_value=area * 0.3,
                        created_at=datetime.now(UTC),
                    )
                )
        session.commit()


def _train_and_approve(session_factory, fake_object_storage, n_groups: int = 20) -> dict:
    _seed_samples(session_factory, n_groups)
    result = ml_score.train()
    assert result is not None
    approval = ml_score.approve_model_version(result["version_id"], approved_by="reviewer-1")
    assert approval["status"] == "approved"
    return result


# ---------------------------------------------------------------------------
# extract_features — ML-01 feature set
# ---------------------------------------------------------------------------


def test_extract_features_reads_all_three_sources():
    features = ml_score.extract_features(SAMPLE_BOUNDARY, SAMPLE_REFINEMENT, SAMPLE_WEATHER)

    assert features["boundary_area"] == pytest.approx(100.0)  # 10x10 square
    assert features["vertex_count"] == 5  # closed ring: 5 coordinate entries
    assert features["vision_confidence"] == 0.9
    assert features["has_vision_data"] == 1.0
    assert features["obstacle_count"] == 1.0
    assert features["obstruction_note_count"] == 1.0
    assert features["irradiance"] == 850.0
    assert features["cloud_cover"] == 15.0
    assert features["temperature"] == 28.0


def test_extract_features_missing_refinement_and_weather_are_none_not_fabricated():
    features = ml_score.extract_features(SAMPLE_BOUNDARY, None, None)

    assert features["vision_confidence"] is None
    assert features["has_vision_data"] == 0.0
    assert features["irradiance"] is None
    assert features["cloud_cover"] is None
    assert features["temperature"] is None
    # geometry-derived fields are still computed — no dependency on refinement/weather
    assert features["boundary_area"] == pytest.approx(100.0)


def test_extract_features_non_polygon_boundary_handled_gracefully():
    features = ml_score.extract_features({"type": "Point", "coordinates": [0, 0]}, None, None)

    assert features["boundary_area"] == 0.0
    assert features["vertex_count"] == 0.0


def test_extract_features_deterministic_same_inputs_same_output():
    """Train/serve parity relies on this being a pure, deterministic
    function — it's the one function object imported by both train()
    and score_with_ml_model()."""
    first = ml_score.extract_features(SAMPLE_BOUNDARY, SAMPLE_REFINEMENT, SAMPLE_WEATHER)
    second = ml_score.extract_features(SAMPLE_BOUNDARY, SAMPLE_REFINEMENT, SAMPLE_WEATHER)
    assert first == second


# ---------------------------------------------------------------------------
# Task 10 — ML-01, train()
# ---------------------------------------------------------------------------


def test_train_returns_none_with_no_samples(ml_session_factory):
    assert ml_score.train() is None


def test_train_returns_none_below_group_threshold(ml_session_factory):
    _seed_samples(ml_session_factory, n_groups=3)  # default threshold is 10

    assert ml_score.train() is None


def test_train_produces_proposed_version_with_metrics(ml_session_factory, fake_object_storage):
    _seed_samples(ml_session_factory, n_groups=20)

    result = ml_score.train()

    assert result is not None
    assert result["status"] == "proposed"
    assert result["group_count"] == 20
    assert result["sample_count"] == 60

    metrics = result["metrics"]
    assert isinstance(metrics["test_mae"], float)
    assert isinstance(metrics["baseline_mae"], float)
    assert metrics["beats_baseline"] in (True, False)
    assert metrics["cv_results"] is not None  # 20 groups is plenty for real CV
    assert metrics["cv_folds"] >= 2

    with ml_session_factory() as session:
        row = session.get(MLModelVersion, result["version_id"])
        assert row is not None
        assert row.status == "proposed"
        assert row.feature_list == ml_score.FEATURE_NAMES
        assert row.artifact_storage_key in fake_object_storage  # real upload happened


def test_train_uploads_artifact_with_expected_key_shape(ml_session_factory, fake_object_storage):
    _seed_samples(ml_session_factory, n_groups=20)

    result = ml_score.train()

    key = result["version"]
    assert f"ml-models/{key}.joblib" in fake_object_storage


def test_train_falls_back_when_too_few_groups_for_cross_validation(
    ml_session_factory, fake_object_storage, monkeypatch
):
    """Forces the cv-skip branch: lower the group threshold so train()
    proceeds with only 2 total groups, which GroupShuffleSplit will
    leave with 1 group in the trainval split — too few for GroupKFold."""
    monkeypatch.setattr(ml_score, "get_ml_min_training_groups", lambda: 1)
    _seed_samples(ml_session_factory, n_groups=2)

    result = ml_score.train()

    assert result is not None
    assert result["metrics"]["cv_results"] is None
    assert result["metrics"]["cv_skipped_reason"] is not None
    assert result["metrics"]["cv_folds"] == 0


def test_train_never_auto_approves(ml_session_factory, fake_object_storage):
    _seed_samples(ml_session_factory, n_groups=20)

    ml_score.train()

    with ml_session_factory() as session:
        from sqlalchemy import select

        approved = session.scalars(select(MLModelVersion).where(MLModelVersion.status == "approved")).first()
        assert approved is None


# ---------------------------------------------------------------------------
# Task 11 — ML-04, approval gate
# ---------------------------------------------------------------------------


def test_approve_model_version_single_active_invariant(ml_session_factory, fake_object_storage):
    _seed_samples(ml_session_factory, n_groups=20)
    first = ml_score.train()
    ml_score.approve_model_version(first["version_id"], approved_by="reviewer-1")

    _seed_samples(ml_session_factory, n_groups=20, area_start=500.0)  # more data, new groups
    second = ml_score.train()
    ml_score.approve_model_version(second["version_id"], approved_by="reviewer-2")

    with ml_session_factory() as session:
        first_row = session.get(MLModelVersion, first["version_id"])
        second_row = session.get(MLModelVersion, second["version_id"])
        assert first_row.status == "rejected"
        assert second_row.status == "approved"


def test_approve_unknown_version_raises(ml_session_factory):
    with pytest.raises(ValueError, match="No ml_model_versions row"):
        ml_score.approve_model_version("does-not-exist", approved_by="reviewer-1")


# ---------------------------------------------------------------------------
# Task 11 — ML-02/05, score_with_ml_model()
# ---------------------------------------------------------------------------


def test_score_insufficient_data_when_no_approved_model(ml_session_factory):
    result = ml_score.score_with_ml_model(SAMPLE_BOUNDARY, SAMPLE_REFINEMENT, SAMPLE_WEATHER)

    assert result.status == "insufficient_data"
    assert result.score is None
    assert result.model_version is None


def test_score_returns_bounded_score_with_approved_model(ml_session_factory, fake_object_storage):
    trained = _train_and_approve(ml_session_factory, fake_object_storage)

    result = ml_score.score_with_ml_model(SAMPLE_BOUNDARY, SAMPLE_REFINEMENT, SAMPLE_WEATHER)

    assert result.status == "ok"
    assert result.score is not None
    assert 0.0 <= result.score <= 100.0
    assert result.model_version == trained["version"]


def test_score_insufficient_data_when_features_mostly_missing(ml_session_factory, fake_object_storage):
    _train_and_approve(ml_session_factory, fake_object_storage)

    # No refinement, no weather -> 5 of 9 features are None (vision_confidence,
    # irradiance, cloud_cover, temperature, plus has_vision_data stays 0.0 not
    # None) -> exceeds MAX_MISSING_FEATURES_ALLOWED (3).
    result = ml_score.score_with_ml_model({"type": "Point", "coordinates": [0, 0]}, None, None)

    assert result.status == "insufficient_data"
    assert result.score is None


def test_score_reproducible_same_inputs_same_output(ml_session_factory, fake_object_storage):
    _train_and_approve(ml_session_factory, fake_object_storage)

    first = ml_score.score_with_ml_model(SAMPLE_BOUNDARY, SAMPLE_REFINEMENT, SAMPLE_WEATHER)
    second = ml_score.score_with_ml_model(SAMPLE_BOUNDARY, SAMPLE_REFINEMENT, SAMPLE_WEATHER)

    assert first == second


# ---------------------------------------------------------------------------
# ML-01 non-substitution — structural, both directions
# ---------------------------------------------------------------------------


def _imported_modules(module) -> set[str]:
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(module))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def test_ml_score_never_imports_fitness():
    from solarfit.engine import ml_score as ml_score_module

    imported = _imported_modules(ml_score_module)
    assert "solarfit.engine.fitness" not in imported


def test_fitness_never_imports_ml_score():
    from solarfit.engine import fitness as fitness_module

    imported = _imported_modules(fitness_module)
    assert "solarfit.engine.ml_score" not in imported


def test_ml_models_repo_never_imports_fitness():
    from solarfit.repositories import ml_models as ml_models_module

    imported = _imported_modules(ml_models_module)
    assert "solarfit.engine.fitness" not in imported
