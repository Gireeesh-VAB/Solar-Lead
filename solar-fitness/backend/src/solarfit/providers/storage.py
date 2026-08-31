"""Owner: Person 3 (AI Pipeline & Cache).

VIZ-02's object-storage half: persist a rendered artifact (currently
just the `.glb` mesh from engine/panorama.py) and hand back a
reference URL — the artifact itself never lives in the database.

Backed by any S3-compatible endpoint (AWS S3, MinIO, ...) via boto3,
configured through solarfit.config's object_storage_* settings (all
default to "" — unconfigured). Never raises: an unconfigured store or
a failed upload both degrade to None, same "never block the pipeline"
discipline as VIS-04 — engine/panorama.py turns that into an explicit
PanoramaResult(status="not_generated"), never a fabricated URL.

Depends on: solarfit.config.get_settings() for the object_storage_*
fields (frozen, Day 0).
"""

import logging

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from solarfit.config import get_settings
from solarfit.providers.vision import with_retries

logger = logging.getLogger(__name__)


def upload_glb(data: bytes, key: str) -> str | None:
    """VIZ-02. Uploads `data` (a .glb mesh) under `key`. Returns the
    object's URL, or None if object storage isn't configured or the
    upload fails for any reason (retried a few times first — same
    with_retries loop as providers/vision.py's HTTP calls) — never
    raises."""
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

    return f"{settings.object_storage_endpoint_url.rstrip('/')}/{settings.object_storage_bucket}/{key}"
