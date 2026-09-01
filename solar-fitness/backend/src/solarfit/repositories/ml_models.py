"""Owner: Person 4 (Scoring, USN & Assessment API).

Persistence for §9.13 ML Suitability Model (ML-01..05) — task 10/11's
training-sample and model-version tables. Mirrors the providers/
(engine/ml_score.py does the ML work + object-storage I/O) vs
repositories/ (this file, pure persistence) split already used for
USN capture (providers/usn_ocr.py vs repositories/usn_uploads.py).

No FK to `sites` yet — that table doesn't exist (Person 1's
repositories/sites.py is still a stub). site_id is a plain indexed
string for now.

Never queried by engine/fitness.py, and this module never imports it —
ML-01's "additive... never in place of the deterministic FIT verdict"
(§17), enforced structurally, checked by a test in test_ml_score.py.
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Float, Integer, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from solarfit.db import Base


class MLTrainingSample(Base):
    __tablename__ = "ml_training_samples"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    site_id: Mapped[str] = mapped_column(String, index=True)
    features: Mapped[dict] = mapped_column(JSON)
    label_source: Mapped[str] = mapped_column(String)  # "fit_score" | "calibration_outcome"
    label_value: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MLModelVersion(Base):
    __tablename__ = "ml_model_versions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    version: Mapped[str] = mapped_column(String, unique=True)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    feature_list: Mapped[list] = mapped_column(JSON)
    hyperparameters: Mapped[dict] = mapped_column(JSON)
    metrics: Mapped[dict] = mapped_column(JSON)
    artifact_storage_key: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)  # "proposed" | "approved" | "rejected"
    approved_by: Mapped[str | None] = mapped_column(String, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sample_count: Mapped[int] = mapped_column(Integer)
    group_count: Mapped[int] = mapped_column(Integer)
    changelog: Mapped[str | None] = mapped_column(String, nullable=True)


def save_training_sample(
    session: Session,
    *,
    site_id: str,
    features: dict,
    label_source: str,
    label_value: float,
) -> MLTrainingSample:
    """ML-01. Not called automatically by anything yet — no orchestration
    endpoint exists to produce (features, label) pairs from a real
    pipeline run. Ready for routers/assessments.py to call once built."""
    sample = MLTrainingSample(
        id=str(uuid4()),
        site_id=site_id,
        features=features,
        label_source=label_source,
        label_value=label_value,
        created_at=datetime.now(UTC),
    )
    session.add(sample)
    session.flush()
    return sample


def get_all_training_samples(session: Session) -> list[MLTrainingSample]:
    return list(session.scalars(select(MLTrainingSample)).all())


def save_model_version(
    session: Session,
    *,
    version: str,
    feature_list: list[str],
    hyperparameters: dict,
    metrics: dict,
    artifact_storage_key: str,
    sample_count: int,
    group_count: int,
    changelog: str | None = None,
) -> MLModelVersion:
    """ML-04. Always inserted with status="proposed" — never auto-active."""
    row = MLModelVersion(
        id=str(uuid4()),
        version=version,
        trained_at=datetime.now(UTC),
        feature_list=feature_list,
        hyperparameters=hyperparameters,
        metrics=metrics,
        artifact_storage_key=artifact_storage_key,
        status="proposed",
        approved_by=None,
        approved_at=None,
        sample_count=sample_count,
        group_count=group_count,
        changelog=changelog,
    )
    session.add(row)
    session.flush()
    return row


def get_approved_model_version(session: Session) -> MLModelVersion | None:
    stmt = select(MLModelVersion).where(MLModelVersion.status == "approved")
    return session.scalars(stmt).first()


def list_model_versions(session: Session) -> list[MLModelVersion]:
    """Newest-trained first."""
    stmt = select(MLModelVersion).order_by(MLModelVersion.trained_at.desc())
    return list(session.scalars(stmt))


def approve_version(session: Session, version_id: str, approved_by: str) -> MLModelVersion:
    """ML-04. Single globally-active model — demotes any previously
    approved version to "rejected" before promoting this one."""
    target = session.get(MLModelVersion, version_id)
    if target is None:
        raise ValueError(f"No ml_model_versions row for id={version_id}")

    currently_approved = get_approved_model_version(session)
    if currently_approved is not None and currently_approved.id != version_id:
        currently_approved.status = "rejected"

    target.status = "approved"
    target.approved_by = approved_by
    target.approved_at = datetime.now(UTC)
    session.flush()
    return target


def reject_version(session: Session, version_id: str, rejected_by: str) -> MLModelVersion:
    """Counterpart to approve_version() above — for a version currently
    "proposed" (never demotes an already-"approved" version; use
    approve_version() on a different candidate for that)."""
    target = session.get(MLModelVersion, version_id)
    if target is None:
        raise ValueError(f"No ml_model_versions row for id={version_id}")

    target.status = "rejected"
    target.approved_by = rejected_by
    target.approved_at = datetime.now(UTC)
    session.flush()
    return target
