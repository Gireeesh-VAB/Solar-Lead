"""Owner: Person 3 (AI Pipeline & Cache).

VIZ-02's object-storage half: persist a rendered artifact (currently
just the `.glb` mesh from engine/panorama.py) and hand back a
reference URL — the artifact itself never lives in the database.

Two backends, chosen by Settings.object_storage_backend:

  "local"  Writes under Settings.local_storage_dir and returns a URL on
           routers/artifacts.py, which serves that directory read-only.
           The default, so 3D models work on a plain dev box with no AWS
           or MinIO credentials.
  "s3"     Any S3-compatible endpoint (AWS S3, MinIO, ...) via boto3,
           configured through the object_storage_* settings (all default
           to "" — unconfigured).

Never raises: an unconfigured store or a failed upload both degrade to
None, same "never block the pipeline" discipline as VIS-04 —
engine/panorama.py turns that into an explicit
PanoramaResult(status="not_generated"), never a fabricated URL.

Depends on: solarfit.config.get_settings() for the object_storage_*
fields (frozen, Day 0).
"""

import logging
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from solarfit.config import get_settings
from solarfit.providers.vision import with_retries

logger = logging.getLogger(__name__)


def safe_artifact_path(root: Path, key: str) -> Path | None:
    """Resolve `key` under `root`, or None if it escapes.

    Shared by the writer here and the reader in routers/artifacts.py so
    both sides apply exactly one traversal rule. Resolution happens before
    the containment check, so `../`, an absolute key, a Windows drive
    letter and a symlink pointing outside are all caught — checking the
    raw string first would not catch any of them.
    """
    if not key:
        return None
    candidate = (root / key).resolve()
    root = root.resolve()
    if candidate == root or not candidate.is_relative_to(root):
        return None
    return candidate


def _upload_local(data: bytes, key: str) -> str | None:
    """Write the artifact under local_storage_dir and return the URL
    routers/artifacts.py will serve it from."""
    settings = get_settings()
    if not settings.local_storage_dir or not settings.public_base_url:
        logger.info("Local artifact storage not configured — skipping upload for %s", key)
        return None

    target = safe_artifact_path(Path(settings.local_storage_dir), key)
    if target is None:
        logger.error("Refusing to write artifact outside the storage directory: %r", key)
        return None

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    except OSError:
        logger.exception("Local artifact write failed for %s", key)
        return None

    return f"{settings.public_base_url.rstrip('/')}/artifacts/{key.lstrip('/')}"


def _upload_s3(data: bytes, key: str) -> str | None:
    settings = get_settings()
    if not settings.object_storage_bucket or not settings.object_storage_endpoint_url:
        logger.info("Object storage not configured — skipping upload for %s", key)
        return None

    try:
        client = boto3.client(
            "s3",
            endpoint_url=settings.object_storage_endpoint_url,
            aws_access_key_id=settings.object_storage_access_key or None,
            aws_secret_access_key=settings.object_storage_secret_key or None,
        )
        with_retries(
            lambda: client.put_object(
                Bucket=settings.object_storage_bucket,
                Key=key,
                Body=data,
                ContentType="model/gltf-binary",
            ),
            base_delay_s=0.1,
            retryable_exceptions=(BotoCoreError, ClientError),
        )
    except (BotoCoreError, ClientError):
        logger.exception("Object storage upload failed for %s (after retries)", key)
        return None

    return (
        f"{settings.object_storage_endpoint_url.rstrip('/')}/{settings.object_storage_bucket}/{key}"
    )


def upload_glb(data: bytes, key: str) -> str | None:
    """VIZ-02. Uploads `data` (a .glb mesh) under `key`. Returns the
    object's URL, or None if storage isn't configured or the write fails
    for any reason (S3 uploads are retried a few times first — same
    with_retries loop as providers/vision.py's HTTP calls) — never
    raises."""
    if get_settings().object_storage_backend == "local":
        return _upload_local(data, key)
    return _upload_s3(data, key)
