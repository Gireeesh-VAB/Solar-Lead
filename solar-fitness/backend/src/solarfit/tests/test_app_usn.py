"""Tests for routers/app_usn.py — the "USN HTTP routes" roadmap
workstream (4 endpoints).

providers/usn_ocr.py's own DB/OCR/storage dependencies are monkeypatched
exactly as test_usn_ocr.py already does (in-memory SQLite for the
evidence table, no real GCP/S3 calls). repositories/sites.py itself
needs a live PostGIS-backed Postgres for real geometry storage, which
this environment doesn't reliably have right now — same discipline
test_calibration.py and test_assessments_router.py already use:
sites_repo.get()/update_usn() are monkeypatched with an in-memory fake
site rather than exercised against the real DB, so these tests verify
this router's own logic (site-type gating, wiring usn_ocr + sites_repo
together, response shape) without depending on someone else's live
infrastructure.
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from solarfit.db import get_session
from solarfit.domain.site import Site, UsnCapture
from solarfit.main import app
from solarfit.providers import usn_ocr
from solarfit.repositories.usn_uploads import UsnOcrUpload
from solarfit.routers import app_usn


@pytest.fixture
def usn_session_factory(sqlite_engine, monkeypatch):
    UsnOcrUpload.metadata.create_all(sqlite_engine, tables=[UsnOcrUpload.__table__])
    session_local = sessionmaker(bind=sqlite_engine)
    monkeypatch.setattr(usn_ocr, "session_scope", lambda: session_local())
    return session_local


@pytest.fixture
def no_op_storage(monkeypatch):
    monkeypatch.setattr(usn_ocr, "_upload_to_object_storage", lambda key, data: None)


def _make_site(**overrides) -> Site:
    defaults = {
        "id": "site-1",
        "site_type": "ROOFTOP_RESIDENTIAL",
        "name": "Test Site",
        "owner_org": "Test Org",
        "jurisdiction": "AP",
        "centroid": {"type": "Point", "coordinates": [78.4867, 17.3850]},
        "boundary": None,
        "exclusions": None,
        "geometry_source": "solar_api",
        "imagery_date": datetime.now(UTC),
        "imagery_quality": "HIGH",
        "geometry_confidence": 0.9,
        "shading": None,
        "usn": None,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return Site(**defaults)


@pytest.fixture
def fake_sites(monkeypatch):
    """Stands in for a real Postgres-backed sites table — an in-memory
    dict keyed by site_id, mirroring sites_repo's real get()/update_usn()
    contracts closely enough for this router's own logic to be tested
    honestly."""
    store: dict[str, Site] = {"site-1": _make_site()}

    def _get(session, site_id):
        del session
        return store.get(site_id)

    def _update_usn(session, site_id, *, usn, usn_source):
        del session
        site = store[site_id]
        updated = site.model_copy(update={"usn": UsnCapture(usn=usn, usn_source=usn_source)})
        store[site_id] = updated
        return updated

    monkeypatch.setattr(app_usn.sites_repo, "get", _get)
    monkeypatch.setattr(app_usn.sites_repo, "update_usn", _update_usn)
    return store


@pytest.fixture
def client(fake_sites):
    app.dependency_overrides[get_session] = lambda: None
    app.dependency_overrides[app_usn.current_user] = lambda: _FAKE_USER
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class _FakeUser:
    id = "user-1"
    role = "customer"


_FAKE_USER = _FakeUser()


# ---------------------------------------------------------------------------
# Site-type gating (USN-05)
# ---------------------------------------------------------------------------


def test_manual_usn_422s_on_non_billing_linked_site_type(client, fake_sites):
    fake_sites["site-1"] = _make_site(site_type="ROOFTOP_GOVT")

    response = client.post("/app/sites/site-1/usn/manual", json={"usn": "AP1234567890"})

    assert response.status_code == 422


def test_manual_usn_404s_on_unknown_site(client, fake_sites):
    response = client.post("/app/sites/does-not-exist/usn/manual", json={"usn": "AP1234567890"})
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# USN-01 manual
# ---------------------------------------------------------------------------


def test_manual_usn_persists_immediately(client, fake_sites):
    response = client.post("/app/sites/site-1/usn/manual", json={"usn": "AP1234567890"})

    assert response.status_code == 200
    body = response.json()
    assert body["usn"] == "AP1234567890"
    assert body["usnSource"] == "manual"
    assert fake_sites["site-1"].usn.usn == "AP1234567890"


def test_manual_usn_rejects_malformed_value(client, fake_sites):
    response = client.post("/app/sites/site-1/usn/manual", json={"usn": "ab"})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# USN-02/03 OCR extraction — preview only, never auto-persisted
# ---------------------------------------------------------------------------


def test_bill_usn_returns_preview_without_persisting(
    client, fake_sites, usn_session_factory, no_op_storage, monkeypatch
):
    monkeypatch.setattr(usn_ocr, "_run_text_detection", lambda image: "USN: AP987654321\n")

    response = client.post(
        "/app/sites/site-1/usn/bill", files={"file": ("bill.png", b"fake-image-bytes", "image/png")}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["usn"] == "AP987654321"
    assert body["extractionStatus"] == "extracted"
    assert "uploadId" in body
    # Never auto-persisted — the site's usn is still None until /confirm.
    assert fake_sites["site-1"].usn is None


def test_payment_proof_usn_returns_preview(
    client, fake_sites, usn_session_factory, no_op_storage, monkeypatch
):
    monkeypatch.setattr(usn_ocr, "_run_text_detection", lambda image: "no usn here")

    response = client.post(
        "/app/sites/site-1/usn/payment-proof",
        files={"file": ("proof.png", b"fake-image-bytes", "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["usn"] is None
    assert body["extractionStatus"] == "not_found"


# ---------------------------------------------------------------------------
# USN-04 confirm — the step that actually writes the Site
# ---------------------------------------------------------------------------


def test_confirm_usn_writes_the_site(client, fake_sites, usn_session_factory, no_op_storage, monkeypatch):
    monkeypatch.setattr(usn_ocr, "_run_text_detection", lambda image: "USN: AP987654321\n")
    preview = client.post(
        "/app/sites/site-1/usn/bill", files={"file": ("bill.png", b"fake-image-bytes", "image/png")}
    ).json()

    response = client.post(
        "/app/sites/site-1/usn/confirm",
        json={"uploadId": preview["uploadId"], "confirmedUsn": "AP987654321"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["usn"] == "AP987654321"
    assert body["usnSource"] == "bill_ocr"
    assert fake_sites["site-1"].usn.usn == "AP987654321"


def test_confirm_usn_unknown_upload_id_is_404(client, fake_sites, usn_session_factory):
    response = client.post(
        "/app/sites/site-1/usn/confirm",
        json={"uploadId": "does-not-exist", "confirmedUsn": "AP987654321"},
    )
    assert response.status_code == 404
