"""workers/tasks_vendors.py::sweep_vendor_sla — the thin Celery wrapper
around repositories/vendors.py::sweep_vendor_job_sla(). Calls the task
object directly (Celery's own synchronous __call__ path, no broker
involved), monkeypatching the repo function so this test doesn't depend
on real DB state or timing — that's what test_vendor_sla_sweep.py
already covers in depth."""

from solarfit.workers.tasks_vendors import sweep_vendor_sla


def test_sweep_vendor_sla_calls_the_repo_function_with_real_config_values(monkeypatch):
    captured = {}

    def _fake_sweep(session, *, at_risk_window, reassignment_extension):
        captured["at_risk_window"] = at_risk_window
        captured["reassignment_extension"] = reassignment_extension
        return {"marked_at_risk": 2, "marked_overdue": 1, "reassigned": 3}

    class _FakeSession:
        def commit(self):
            captured["committed"] = True

    from contextlib import contextmanager

    @contextmanager
    def _fake_session_scope():
        yield _FakeSession()

    monkeypatch.setattr("solarfit.repositories.vendors.sweep_vendor_job_sla", _fake_sweep)
    monkeypatch.setattr("solarfit.workers.tasks_vendors.session_scope", _fake_session_scope)

    result = sweep_vendor_sla()

    assert result == {"marked_at_risk": 2, "marked_overdue": 1, "reassigned": 3}
    assert captured["committed"] is True
    # Real config-pack values (rooftop_v1.yaml), not hardcoded literals.
    assert captured["at_risk_window"].total_seconds() == 24 * 3600
    assert captured["reassignment_extension"].days == 2
