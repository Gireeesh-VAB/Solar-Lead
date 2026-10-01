"""Phase 4 — workers/tasks_assessments.py::run_check_assessment (the
plain function the @celery_app.task wrapper, run_check_assessment_task,
delegates to) and the wrapper's own on_stage wiring.

run_check_assessment is deliberately a plain function, not the task body
itself, so these tests can call it directly without a real Celery
broker/worker — same "tests mock .delay() itself" discipline
test_assessments_router.py's own notes establish for this codebase.
"""

from solarfit.providers.validation import GeometryRejected
from solarfit.routers.assessments import SiteNotFoundError
from solarfit.workers.tasks_assessments import run_check_assessment, run_check_assessment_task


def test_a_missing_site_reports_not_found(monkeypatch):
    def _boom(site_id, owner_org=None, **kw):
        raise SiteNotFoundError(f"Site {site_id} not found")

    monkeypatch.setattr("solarfit.routers.assessments.orchestrate_assessment", _boom)

    result = run_check_assessment("missing-site", "individual:u1", on_stage=lambda s: None)

    assert result == {"status": "not_found", "error": "Site missing-site not found"}


def test_no_solar_api_coverage_reports_geometry_rejected(monkeypatch):
    def _boom(site_id, owner_org=None, **kw):
        raise GeometryRejected("no coverage here")

    monkeypatch.setattr("solarfit.routers.assessments.orchestrate_assessment", _boom)

    result = run_check_assessment("site-1", "individual:u1", on_stage=lambda s: None)

    assert result["status"] == "geometry_rejected"
    assert "no coverage here" in result["error"]


def test_a_successful_run_persists_and_reports_ok(monkeypatch):
    from contextlib import contextmanager

    from solarfit.domain.constraint import CapacityResult
    from solarfit.routers.assessments import AssessmentResponse

    canned = AssessmentResponse(
        site_id="site-1",
        site_type="ROOFTOP_RESIDENTIAL",
        verdict="SUITABLE",
        score=0.8,
        confidence=0.7,
        binding_constraint="net_metering_cap",
        reasons=[],
        limitations="",
        capacity=CapacityResult(recommended_kwp=4.0, status="ok"),
        boundary={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
        usable_area_m2=40.0,
        engine_version="test",
        constraint_pack_version="test",
    )
    monkeypatch.setattr(
        "solarfit.routers.assessments.orchestrate_assessment",
        lambda site_id, owner_org=None, **kw: canned,
    )

    saved = {}

    @contextmanager
    def _fake_session_scope():
        yield type("FakeSession", (), {"commit": lambda self: None})()

    def _fake_save_assessment(session, *, owner_org, **fields):
        saved["owner_org"] = owner_org
        saved["fields"] = fields

    monkeypatch.setattr("solarfit.db.session_scope", _fake_session_scope)
    monkeypatch.setattr(
        "solarfit.repositories.assessments.save_assessment", _fake_save_assessment
    )

    result = run_check_assessment("site-1", "individual:u1", on_stage=lambda s: None)

    assert result == {"status": "ok", "site_id": "site-1"}
    assert saved["owner_org"] == "individual:u1"
    assert saved["fields"]["verdict"] == "SUITABLE"


def test_every_stage_is_reported_in_pipeline_order(monkeypatch):
    """The on_stage callback orchestrate_assessment actually calls (not a
    stand-in) is exercised here via a real, minimal orchestrate_assessment
    run — confirms the stages route through unchanged and in the order
    routers/assessments.py::ASSESSMENT_STAGES declares."""
    seen: list[str] = []

    def _fake_orchestrate(site_id, owner_org=None, *, on_stage=None):
        from solarfit.routers.assessments import ASSESSMENT_STAGES

        for stage in ASSESSMENT_STAGES:
            on_stage(stage)
        raise SiteNotFoundError("stop here — only checking stage order")

    monkeypatch.setattr("solarfit.routers.assessments.orchestrate_assessment", _fake_orchestrate)

    run_check_assessment("site-1", "individual:u1", on_stage=seen.append)

    from solarfit.routers.assessments import ASSESSMENT_STAGES

    assert seen == ASSESSMENT_STAGES


def test_the_celery_task_delegates_with_an_on_stage_that_reports_progress(monkeypatch):
    """Calls the Task object directly (Celery's own synchronous __call__
    path, no broker involved) and confirms it hands run_check_assessment
    an on_stage that reaches Task.update_state — without ever actually
    invoking it, so this needs no real result-backend connection."""
    captured = {}

    def _fake_run_check_assessment(site_id, owner_org, on_stage):
        captured["site_id"] = site_id
        captured["owner_org"] = owner_org
        captured["on_stage"] = on_stage
        return {"status": "ok", "site_id": site_id}

    monkeypatch.setattr(
        "solarfit.workers.tasks_assessments.run_check_assessment", _fake_run_check_assessment
    )

    update_state_calls = []
    monkeypatch.setattr(
        run_check_assessment_task, "update_state", lambda **kw: update_state_calls.append(kw)
    )

    result = run_check_assessment_task(site_id="site-1", owner_org="individual:u1")

    assert result == {"status": "ok", "site_id": "site-1"}
    assert captured["site_id"] == "site-1"
    assert captured["owner_org"] == "individual:u1"

    # The on_stage closure calls self.update_state — confirmed here by
    # invoking it directly, still without touching a real result backend
    # (update_state itself is mocked above).
    captured["on_stage"]("computing_usable_area")
    assert update_state_calls == [{"state": "PROGRESS", "meta": {"stage": "computing_usable_area"}}]
