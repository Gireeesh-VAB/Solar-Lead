"""Owner: karthik (App Platform & Foundation).

Tests for routers/app_imports.py (the async, persisted import path) and
workers/tasks_imports.py::run_import_job (the Celery task it dispatches).

Router-level tests monkeypatch run_import_job.delay so the HTTP layer
never actually runs the task inline — the same pattern
test_assessments_router.py already uses for its own batch endpoint.
Task-level tests call run_import_job.run() directly (bypassing Celery
entirely, per test_celery_tasks.py's precedent) with
solarfit.db.session_scope patched to the test's own transactional
db_session, so process_one_row()'s real writes roll back with everything
else instead of landing in the real dev database.
"""

from __future__ import annotations

import csv
import io
import json
from contextlib import contextmanager
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import box as shapely_box
from shapely.geometry import mapping

from solarfit.db import get_session
from solarfit.main import app
from solarfit.repositories import import_jobs as import_jobs_repo

LON, LAT = 78.4867, 17.3850


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _poly(dlon: float = 0.0, dlat: float = 0.0, size: float = 0.0005) -> dict:
    return mapping(shapely_box(LON + dlon, LAT + dlat, LON + dlon + size, LAT + dlat + size))


def _geojson_bytes(*geoms: dict) -> bytes:
    return json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": g, "properties": {"name": f"Roof {i}"}}
                for i, g in enumerate(geoms, start=1)
            ],
        }
    ).encode()


def _csv_bytes(rows: list[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["name", "lat", "lng"])
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return buf.getvalue().encode()


# --------------------------------------------------------------------- #
# POST /app/imports — router layer, dispatch mocked
# --------------------------------------------------------------------- #


def test_create_import_job_dispatches_and_returns_queued(client, make_auth_header, monkeypatch):
    import solarfit.workers.tasks_imports as tasks_imports_module

    calls = []
    monkeypatch.setattr(tasks_imports_module.run_import_job, "delay", lambda *a, **kw: calls.append((a, kw)))

    headers = make_auth_header(role="customer")
    response = client.post(
        "/app/imports",
        headers=headers,
        files={"file": ("roofs.geojson", _geojson_bytes(_poly()), "application/geo+json")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "queued"
    assert body["totalRows"] == 1
    assert body["rows"] == []
    assert len(calls) == 1  # the task really was dispatched


def test_create_import_job_requires_a_customer_account(client, make_auth_header):
    headers = make_auth_header(role="vendor")
    response = client.post(
        "/app/imports",
        headers=headers,
        files={"file": ("roofs.geojson", _geojson_bytes(_poly()), "application/geo+json")},
    )
    assert response.status_code == 403


def test_create_import_job_empty_file_is_422(client, make_auth_header):
    headers = make_auth_header(role="customer")
    response = client.post("/app/imports", headers=headers, files={"file": ("empty.csv", b"", "text/csv")})
    assert response.status_code == 422


def test_list_import_jobs_is_scoped_to_the_caller(client, make_auth_header, monkeypatch):
    import solarfit.workers.tasks_imports as tasks_imports_module

    monkeypatch.setattr(tasks_imports_module.run_import_job, "delay", lambda *a, **kw: None)

    mine = make_auth_header(role="customer", email=f"mine-{uuid4().hex[:8]}@example.com")
    theirs = make_auth_header(role="customer", email=f"theirs-{uuid4().hex[:8]}@example.com")
    client.post("/app/imports", headers=mine, files={"file": ("a.geojson", _geojson_bytes(_poly()), "application/geo+json")})
    client.post("/app/imports", headers=theirs, files={"file": ("b.geojson", _geojson_bytes(_poly()), "application/geo+json")})

    response = client.get("/app/imports", headers=mine)
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_import_job_includes_rows(client, make_auth_header, monkeypatch, db_session):
    import solarfit.workers.tasks_imports as tasks_imports_module

    monkeypatch.setattr(tasks_imports_module.run_import_job, "delay", lambda *a, **kw: None)

    headers = make_auth_header(role="customer")
    created = client.post(
        "/app/imports",
        headers=headers,
        files={"file": ("a.geojson", _geojson_bytes(_poly()), "application/geo+json")},
    ).json()

    import_jobs_repo.record_row_result(db_session, created["id"], row_number=1, status="success", identifier="Roof 1")

    response = client.get(f"/app/imports/{created['id']}", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body["rows"]) == 1
    assert body["rows"][0]["status"] == "success"


def test_get_unknown_import_job_is_404(client, make_auth_header):
    headers = make_auth_header(role="customer")
    response = client.get("/app/imports/00000000-0000-0000-0000-000000000000", headers=headers)
    assert response.status_code == 404


# --------------------------------------------------------------------- #
# run_import_job — the Celery task itself, run synchronously
# --------------------------------------------------------------------- #


def test_run_import_job_processes_rows_and_marks_complete(db_session, monkeypatch):
    from solarfit.workers.tasks_imports import run_import_job

    @contextmanager
    def _fake_session_scope():
        yield db_session

    monkeypatch.setattr("solarfit.db.session_scope", _fake_session_scope)

    owner_org = f"org-{uuid4().hex[:8]}"
    job = import_jobs_repo.create_job(db_session, file_name="rows.geojson", total_rows=1, created_by="tester@example.com")

    rows = [{"boundary": _poly(), "name": "Roof A"}]
    result = run_import_job.run(
        str(job.id), rows, owner_org=owner_org, site_type="ROOFTOP_RESIDENTIAL", jurisdiction="IN-TG"
    )

    assert result["status"] == "complete"
    refreshed = import_jobs_repo.get_job(db_session, job.id)
    assert refreshed.status == "complete"
    assert refreshed.processed_rows == 1
    assert refreshed.error_rows == 0

    row_results = import_jobs_repo.list_rows(db_session, job.id)
    assert len(row_results) == 1
    assert row_results[0].status == "success"


def test_run_import_job_marks_partial_when_a_row_fails(db_session, monkeypatch):
    from solarfit.workers.tasks_imports import run_import_job

    @contextmanager
    def _fake_session_scope():
        yield db_session

    monkeypatch.setattr("solarfit.db.session_scope", _fake_session_scope)

    owner_org = f"org-{uuid4().hex[:8]}"
    job = import_jobs_repo.create_job(db_session, file_name="rows.geojson", total_rows=2, created_by="tester@example.com")

    rows = [{"boundary": _poly()}, {"_error": "no geometry at all"}]
    result = run_import_job.run(
        str(job.id), rows, owner_org=owner_org, site_type="ROOFTOP_RESIDENTIAL", jurisdiction="IN-TG"
    )

    assert result["status"] == "partial"
    refreshed = import_jobs_repo.get_job(db_session, job.id)
    assert refreshed.error_rows == 1

    row_results = {r.status for r in import_jobs_repo.list_rows(db_session, job.id)}
    assert row_results == {"success", "error"}
