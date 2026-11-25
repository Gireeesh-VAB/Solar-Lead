"""§16 Testing — VIZ-02's local artifact backend and the read-only route
that serves it (providers/storage.py + routers/artifacts.py).

The local backend is what makes 3D models work on a dev box with no S3
credentials, so the tests that matter most here are the containment ones:
a key that escapes the storage directory must never be written, and a
path that escapes it must never be read.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from solarfit.main import app
from solarfit.providers.storage import safe_artifact_path, upload_glb

client = TestClient(app)

# A key that walks out of the storage root, expressed the several ways an
# attacker would actually try it.
ESCAPING_KEYS = [
    "../escaped.glb",
    "panorama/../../escaped.glb",
    "panorama/../../../../../../etc/passwd",
    "/etc/passwd",
    "",
]


def _local_settings(tmp_path: Path, base_url: str = "http://localhost:8000") -> MagicMock:
    return MagicMock(
        object_storage_backend="local",
        local_storage_dir=str(tmp_path),
        public_base_url=base_url,
    )


# --------------------------------------------------------------------------
# safe_artifact_path — the single containment rule both sides share
# --------------------------------------------------------------------------


def test_safe_artifact_path_accepts_a_key_inside_the_root(tmp_path):
    resolved = safe_artifact_path(tmp_path, "panorama/abc123.glb")
    assert resolved is not None
    assert resolved == (tmp_path / "panorama" / "abc123.glb").resolve()


@pytest.mark.parametrize("key", ESCAPING_KEYS)
def test_safe_artifact_path_rejects_keys_escaping_the_root(tmp_path, key):
    assert safe_artifact_path(tmp_path, key) is None


def test_safe_artifact_path_rejects_the_root_itself(tmp_path):
    assert safe_artifact_path(tmp_path, ".") is None


# --------------------------------------------------------------------------
# Local upload
# --------------------------------------------------------------------------


def test_upload_glb_local_writes_the_file_and_returns_its_url(tmp_path):
    with patch("solarfit.providers.storage.get_settings", return_value=_local_settings(tmp_path)):
        url = upload_glb(b"glTF-fake-bytes", key="panorama/abc123.glb")

    assert url == "http://localhost:8000/artifacts/panorama/abc123.glb"
    written = tmp_path / "panorama" / "abc123.glb"
    assert written.read_bytes() == b"glTF-fake-bytes"  # real bytes, not a stub


def test_upload_glb_local_strips_a_trailing_slash_from_the_base_url(tmp_path):
    settings = _local_settings(tmp_path, base_url="http://example.test/")
    with patch("solarfit.providers.storage.get_settings", return_value=settings):
        url = upload_glb(b"x", key="panorama/a.glb")

    assert url == "http://example.test/artifacts/panorama/a.glb"  # never a double slash


@pytest.mark.parametrize("key", ESCAPING_KEYS)
def test_upload_glb_local_refuses_to_write_outside_the_storage_dir(tmp_path, key):
    with patch("solarfit.providers.storage.get_settings", return_value=_local_settings(tmp_path)):
        assert upload_glb(b"payload", key=key) is None

    assert not list(tmp_path.rglob("*.glb"))
    assert not (tmp_path.parent / "escaped.glb").exists()


def test_upload_glb_local_returns_none_when_unconfigured(tmp_path):
    settings = MagicMock(
        object_storage_backend="local", local_storage_dir="", public_base_url="http://x"
    )
    with patch("solarfit.providers.storage.get_settings", return_value=settings):
        assert upload_glb(b"payload", key="panorama/a.glb") is None


def test_upload_glb_local_returns_none_when_the_write_fails(tmp_path):
    with (
        patch("solarfit.providers.storage.get_settings", return_value=_local_settings(tmp_path)),
        patch.object(Path, "write_bytes", side_effect=OSError("disk full")),
    ):
        assert upload_glb(b"payload", key="panorama/a.glb") is None  # degrades, never raises


# --------------------------------------------------------------------------
# The read-only route
# --------------------------------------------------------------------------


def test_get_artifact_serves_a_stored_file(tmp_path):
    artifact = tmp_path / "panorama" / "abc123.glb"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"glTF\x02\x00\x00\x00")

    with patch("solarfit.routers.artifacts.get_settings", return_value=_local_settings(tmp_path)):
        response = client.get("/artifacts/panorama/abc123.glb")

    assert response.status_code == 200
    assert response.content == b"glTF\x02\x00\x00\x00"
    assert response.headers["content-type"] == "model/gltf-binary"


def test_get_artifact_404s_for_a_missing_file(tmp_path):
    with patch("solarfit.routers.artifacts.get_settings", return_value=_local_settings(tmp_path)):
        assert client.get("/artifacts/panorama/nope.glb").status_code == 404


def test_get_artifact_rejects_path_traversal(tmp_path):
    secret = tmp_path.parent / "secret.txt"
    secret.write_text("do not serve me")

    with patch("solarfit.routers.artifacts.get_settings", return_value=_local_settings(tmp_path)):
        for attempt in ("../secret.txt", "panorama/../../secret.txt", "%2e%2e/secret.txt"):
            response = client.get(f"/artifacts/{attempt}")
            # 404 not 403 — a distinct status would confirm what exists.
            assert response.status_code == 404, attempt
            assert b"do not serve me" not in response.content


def test_get_artifact_is_read_only(tmp_path):
    """No writer on this route — only providers/storage.py, in-process."""
    with patch("solarfit.routers.artifacts.get_settings", return_value=_local_settings(tmp_path)):
        for method in (client.post, client.put, client.delete, client.patch):
            assert method("/artifacts/panorama/abc123.glb").status_code == 405


def test_get_artifact_404s_when_the_backend_is_s3(tmp_path):
    """With the s3 backend this route is inert — panorama_url points
    straight at the object store and nothing should reach here."""
    settings = MagicMock(object_storage_backend="s3", local_storage_dir=str(tmp_path))
    artifact = tmp_path / "a.glb"
    artifact.write_bytes(b"glTF")

    with patch("solarfit.routers.artifacts.get_settings", return_value=settings):
        assert client.get("/artifacts/a.glb").status_code == 404
