"""§16 Testing — weather provider client. No live network calls:
httpx.get is monkeypatched to return a canned Open-Meteo-shaped response.
"""

import httpx
import pytest

from solarfit.providers import weather


class _FakeResponse:
    def __init__(self, json_body, status_code=200):
        self._json_body = json_body
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._json_body


def test_fetch_weather_normalizes_open_meteo_response(monkeypatch):
    canned = {
        "current": {
            "shortwave_radiation": 512.3,
            "temperature_2m": 28.4,
            "cloud_cover": 40,
        }
    }
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse(canned))

    result = weather.fetch_weather(17.385, 78.4867)

    assert result == {
        "irradiance_w_m2": 512.3,
        "temperature_c": 28.4,
        "cloud_cover_pct": 40.0,
    }


def test_fetch_weather_raises_typed_error_on_http_failure(monkeypatch):
    def _raise(*a, **k):
        raise httpx.ConnectError("network down")

    monkeypatch.setattr(httpx, "get", _raise)

    with pytest.raises(weather.WeatherProviderError):
        weather.fetch_weather(17.385, 78.4867)


def test_fetch_weather_raises_typed_error_on_malformed_response(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse({"current": {}}))

    with pytest.raises(weather.WeatherProviderError):
        weather.fetch_weather(17.385, 78.4867)
