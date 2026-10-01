"""VIZ-02's local-storage read side.

Serves the .glb files providers/storage.py writes when
object_storage_backend is "local", so a developer gets working 3D models
with no S3/MinIO credentials. With the "s3" backend this route is inert —
panorama_url then points straight at the object store and nothing reaches
here.

Deliberately narrow:

  * GET only. There is no upload, delete or list endpoint — the only
    writer is providers/storage.py, in-process.
  * Every path goes through storage.safe_artifact_path(), the same
    containment check the writer uses, so `..`, absolute paths, Windows
    drive letters and symlinks out of the tree are all rejected. One rule,
    one implementation, no way for the two sides to drift apart.
  * A rejected path returns the same 404 as a genuinely missing file —
    a distinct 403 would confirm to a prober which paths exist.

Unauthenticated by design, matching the S3 backend it stands in for:
panorama keys are SHA-256 boundary hashes, and the frontend loads the
model into a WebGL canvas with GLTFLoader, which cannot easily carry a
bearer token. Treat these URLs as unguessable, not as secrets — the file
holds roof geometry, no personal data.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from solarfit.config import get_settings
from solarfit.providers.storage import safe_artifact_path

logger = logging.getLogger(__name__)

router = APIRouter(tags=["artifacts"])

# Only what this route actually produces. An unknown extension is served
# as a plain download rather than anything a browser will execute.
_CONTENT_TYPES = {".glb": "model/gltf-binary", ".gltf": "model/gltf+json"}


@router.get("/artifacts/{artifact_path:path}")
def get_artifact(artifact_path: str) -> FileResponse:
    """Read-only access to one generated artifact."""
    settings = get_settings()
    if settings.object_storage_backend != "local" or not settings.local_storage_dir:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact storage is not local")

    target = safe_artifact_path(Path(settings.local_storage_dir), artifact_path)
    if target is None:
        # Logged, because a traversal attempt is worth seeing; still a 404
        # to the caller so probing tells them nothing.
        logger.warning("Rejected artifact path outside the storage directory: %r", artifact_path)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact not found")

    if not target.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Artifact not found")

    return FileResponse(
        target,
        media_type=_CONTENT_TYPES.get(target.suffix.lower(), "application/octet-stream"),
        # The key is a hash of the BOUNDARY, not of the file, so the same
        # URL legitimately gets new bytes whenever the mesh generator
        # changes. A long max-age therefore pins browsers to a stale model
        # — must-revalidate keeps the cache but forces a conditional
        # request, which FileResponse answers with a cheap 304 via ETag.
        headers={"Cache-Control": "public, max-age=300, must-revalidate"},
    )
