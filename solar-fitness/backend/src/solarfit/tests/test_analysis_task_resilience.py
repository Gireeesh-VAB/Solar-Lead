"""§16 Testing — a slow or dead Celery task must not fail a customer's check.

The regression these guard is a real one, seen three times in production
logs: generate_panorama_task exceeded async_task_timeout_s, celery raised
TimeoutError from .get(), and the whole assessment 500'd. The customer saw
"We couldn't finish this check" because a cosmetic 3D mesh — which
nothing on the site even renders any more — took too long to download a
DSM.

engine/panorama.py and providers/vision.py both honour their own
never-raise contracts (VIZ-03, VIS-04). The gap was that the WAIT happens
outside them, so those contracts were bypassed entirely.
"""

from unittest.mock import MagicMock, patch

import pytest
from celery.exceptions import TimeoutError as CeleryTimeoutError

from solarfit.repositories.analysis_cache import _await_task

FALLBACK = {"status": "not_generated", "reason": "Panorama generation timed out"}


def _result(**kwargs) -> MagicMock:
    task = MagicMock()
    task.get.configure_mock(**kwargs)
    return task


def test_a_completed_task_returns_its_real_result():
    task = _result(return_value={"status": "ok", "url": "https://x/y.glb"})

    assert _await_task(task, 30.0, label="panorama", fallback=FALLBACK) == {
        "status": "ok",
        "url": "https://x/y.glb",
    }
    task.get.assert_called_once_with(timeout=30.0)


def test_a_timeout_degrades_instead_of_raising():
    """The exact failure that killed three checks."""
    task = _result(side_effect=CeleryTimeoutError("The operation timed out."))

    assert _await_task(task, 30.0, label="panorama", fallback=FALLBACK) == FALLBACK


@pytest.mark.parametrize(
    "failure",
    [
        CeleryTimeoutError("timed out"),
        ConnectionError("broker unreachable"),
        RuntimeError("worker died mid-task"),
        OSError("redis connection reset"),
    ],
)
def test_every_route_to_no_answer_degrades_the_same_way(failure):
    """A dead worker, an unreachable broker and a slow task are one
    outcome from the caller's side: no result, and an assessment that
    still completes on the data it does have."""
    task = _result(side_effect=failure)

    assert _await_task(task, 30.0, label="vision refinement", fallback={"status": "x"}) == {
        "status": "x"
    }


def test_the_timeout_is_actually_applied():
    """A wait with no ceiling would hang the request thread indefinitely
    rather than degrading."""
    task = _result(return_value={})

    _await_task(task, 12.5, label="panorama", fallback=FALLBACK)
    task.get.assert_called_once_with(timeout=12.5)


def test_a_failure_is_logged_loudly_enough_to_notice():
    """Degrading silently would turn a broken worker into a permanent,
    invisible loss of every panorama and refinement."""
    task = _result(side_effect=CeleryTimeoutError("timed out"))

    with patch("solarfit.repositories.analysis_cache.logger") as logger:
        _await_task(task, 30.0, label="panorama", fallback=FALLBACK)

    logger.warning.assert_called_once()
    assert logger.warning.call_args.kwargs.get("exc_info") is True


def test_panorama_is_not_dispatched_while_disabled():
    """VIZ-05 is switched off: nothing renders a .glb, so generating one
    cost ~11 s and a billable DSM download on every single check."""
    from solarfit.packs.config_pack import get_panorama_enabled

    assert get_panorama_enabled() is False
