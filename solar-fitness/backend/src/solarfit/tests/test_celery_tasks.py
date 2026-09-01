"""Regression test for workers/celery_app.py::apply_obstacles_task.

Covers a real (non-mocked) integration bug fixed in this pass: the task
called `get_site(site_id)` with one argument against the real two-argument
`repositories.sites.get(session, site_id)` signature. Every other test in
this codebase monkeypatches `sites_repo.get` with whatever arity the
caller happened to use, which is exactly how this went unnoticed — this
test's fake matches the REAL signature instead, so a regression to the
one-argument call shape fails loudly here.
"""

from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import MagicMock

from solarfit.domain.site import Site
from solarfit.workers import celery_app as celery_app_module

BOUNDARY = {
    "type": "Polygon",
    "coordinates": [
        [[78.4860, 17.3845], [78.4874, 17.3845], [78.4874, 17.3855], [78.4860, 17.3855], [78.4860, 17.3845]]
    ],
}


@contextmanager
def _fake_session_scope():
    yield MagicMock(name="fake-session")


def _site() -> Site:
    return Site(
        id="site-1",
        site_type="ROOFTOP_RESIDENTIAL",
        name="Test Site",
        owner_org="Test Org",
        jurisdiction="TS",
        centroid={"type": "Point", "coordinates": [78.4867, 17.3850]},
        boundary=BOUNDARY,
        created_at=datetime.now(UTC),
    )


def test_apply_obstacles_task_calls_sites_get_with_a_real_session(monkeypatch):
    site = _site()
    calls: list[tuple] = []

    def _fake_get(session, site_id):
        calls.append((session, site_id))
        return site if site_id == site.id else None

    monkeypatch.setattr("solarfit.db.session_scope", _fake_session_scope)
    monkeypatch.setattr("solarfit.repositories.sites.get", _fake_get)
    monkeypatch.setattr("solarfit.engine.obstacles.apply_or_flag", lambda s, obstacles: obstacles)

    result = celery_app_module.apply_obstacles_task.run(
        "site-1",
        [
            {
                "type": "water_tank",
                "confidence": 0.5,
                "bounding_polygon": {
                    "type": "Polygon",
                    "coordinates": [
                        [[78.4862, 17.3847], [78.4864, 17.3847], [78.4864, 17.3849], [78.4862, 17.3849], [78.4862, 17.3847]]
                    ],
                },
            }
        ],
    )

    assert len(calls) == 1
    assert calls[0][1] == "site-1"  # site_id landed in the right positional slot
    assert result["site_id"] == "site-1"


def test_apply_obstacles_task_unknown_site_returns_none(monkeypatch):
    """get_site() returning None (site not found) must not itself crash
    the task before apply_or_flag() gets a chance to handle it."""
    monkeypatch.setattr("solarfit.db.session_scope", _fake_session_scope)
    monkeypatch.setattr("solarfit.repositories.sites.get", lambda session, site_id: None)

    seen_site = {}
    monkeypatch.setattr(
        "solarfit.engine.obstacles.apply_or_flag",
        lambda s, obstacles: seen_site.setdefault("site", s) or obstacles,
    )

    celery_app_module.apply_obstacles_task.run("does-not-exist", [])

    assert seen_site["site"] is None
