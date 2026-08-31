"""§16 Testing — Day 4 production-hardening: the retry/backoff loop
shared by providers/vision.py's HTTP calls and providers/storage.py's
object-storage upload.
"""

from unittest.mock import patch

import pytest

from solarfit.providers.vision import TransientError, with_retries


def test_with_retries_succeeds_on_first_try():
    calls = []

    def fn():
        calls.append(1)
        return "ok"

    with patch("solarfit.providers.vision.time.sleep") as sleep:
        result = with_retries(fn)

    assert result == "ok"
    assert len(calls) == 1
    sleep.assert_not_called()


def test_with_retries_recovers_after_transient_failures():
    attempts = {"count": 0}

    def fn():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise TransientError("transient")
        return "ok"

    with patch("solarfit.providers.vision.time.sleep") as sleep:
        result = with_retries(fn, attempts=3)

    assert result == "ok"
    assert attempts["count"] == 3
    assert sleep.call_count == 2  # backoff before attempt 2 and attempt 3


def test_with_retries_raises_the_last_exception_after_exhausting_attempts():
    def fn():
        raise TransientError("still failing")

    with patch("solarfit.providers.vision.time.sleep"), pytest.raises(TransientError, match="still failing"):
        with_retries(fn, attempts=3)


def test_with_retries_never_retries_a_non_retryable_exception():
    calls = []

    def fn():
        calls.append(1)
        raise ValueError("not transient")

    with patch("solarfit.providers.vision.time.sleep") as sleep, pytest.raises(ValueError, match="not transient"):
        with_retries(fn, attempts=3)

    assert len(calls) == 1  # no retry attempted
    sleep.assert_not_called()
