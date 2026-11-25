"""§16 Testing — NASA POWER provider client. No live network calls:
httpx.get is monkeypatched to return a canned climatology response.
"""

import httpx
import pytest

from solarfit.providers import nasa_power


class _FakeResponse:
    def __init__(self, json_body, status_code=200):
        self._json_body = json_body
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._json_body


def _canned_response(ann=5.5):
    return {
        "properties": {
            "parameter": {
                "ALLSKY_SFC_SW_DWN": {
                    "JAN": 4.5,
                    "FEB": 5.0,
                    "ANN": ann,
                }
            }
        }
    }


def test_fetch_nasa_power_irradiance_normalizes_response(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse(_canned_response(ann=5.5)))

    result = nasa_power.fetch_nasa_power_irradiance(lat=17.385, lng=78.4867)

    assert result["irradiance_w_m2"] == pytest.approx(5.5 * 1000 / 24)


def test_fetch_nasa_power_irradiance_sends_expected_params(monkeypatch):
    captured = {}

    def _fake_get(url, params=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        return _FakeResponse(_canned_response())

    monkeypatch.setattr(httpx, "get", _fake_get)

    nasa_power.fetch_nasa_power_irradiance(lat=17.385, lng=78.4867)

    assert captured["url"] == nasa_power._BASE_URL
    assert captured["params"] == {
        "parameters": "ALLSKY_SFC_SW_DWN",
        "community": "RE",
        "longitude": 78.4867,
        "latitude": 17.385,
        "format": "JSON",
    }


def test_fetch_nasa_power_irradiance_raises_typed_error_on_http_failure(monkeypatch):
    def _raise(*a, **k):
        raise httpx.ConnectError("network down")

    monkeypatch.setattr(httpx, "get", _raise)

    with pytest.raises(nasa_power.NASAPowerError):
        nasa_power.fetch_nasa_power_irradiance(lat=17.385, lng=78.4867)


def test_fetch_nasa_power_irradiance_raises_typed_error_on_malformed_response(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse({"properties": {}}))

    with pytest.raises(nasa_power.NASAPowerError):
        nasa_power.fetch_nasa_power_irradiance(lat=17.385, lng=78.4867)


def test_fetch_nasa_power_irradiance_raises_typed_error_on_fill_value(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse(_canned_response(ann=-999)))

    with pytest.raises(nasa_power.NASAPowerError):
        nasa_power.fetch_nasa_power_irradiance(lat=17.385, lng=78.4867)


def test_fetch_nasa_power_irradiance_uses_injected_client(monkeypatch):
    class _FakeClient:
        def get(self, url, params=None, timeout=None):
            return _FakeResponse(_canned_response(ann=5.5))

    def _fail_if_called(*a, **k):
        raise AssertionError("httpx.get should not be called when a client is injected")

    monkeypatch.setattr(httpx, "get", _fail_if_called)

    result = nasa_power.fetch_nasa_power_irradiance(
        lat=17.385, lng=78.4867, client=_FakeClient()
    )

    assert result["irradiance_w_m2"] == pytest.approx(5.5 * 1000 / 24)
