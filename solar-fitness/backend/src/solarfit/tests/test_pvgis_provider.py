"""§16 Testing — PVGIS provider client. No live network calls:
httpx.get is monkeypatched to return a canned PVGIS PVcalc-shaped response.
"""

import httpx
import pytest

from solarfit.providers import pvgis


class _FakeResponse:
    def __init__(self, json_body, status_code=200):
        self._json_body = json_body
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._json_body


def _canned_response():
    return {
        "outputs": {
            "totals": {"fixed": {"E_y": 8234.5}},
            "monthly": {
                "fixed": [
                    {"month": i, "E_m": 600.0 + i} for i in range(1, 13)
                ]
            },
        }
    }


def test_fetch_pvgis_generation_normalizes_response(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse(_canned_response()))

    result = pvgis.fetch_pvgis_generation(
        lat=17.385, lng=78.4867, peak_power_kwp=10.0, loss_pct=14.0, tilt_deg=10.0, azimuth_deg=0.0
    )

    assert result["annual_kwh"] == 8234.5
    assert result["monthly_kwh"] == [600.0 + i for i in range(1, 13)]
    assert len(result["monthly_kwh"]) == 12


def test_fetch_pvgis_generation_sends_expected_params(monkeypatch):
    captured = {}

    def _fake_get(url, params=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        return _FakeResponse(_canned_response())

    monkeypatch.setattr(httpx, "get", _fake_get)

    pvgis.fetch_pvgis_generation(
        lat=17.385, lng=78.4867, peak_power_kwp=10.0, loss_pct=14.0, tilt_deg=10.0, azimuth_deg=180.0
    )

    assert captured["url"] == pvgis._BASE_URL
    assert captured["params"] == {
        "lat": 17.385,
        "lon": 78.4867,
        "peakpower": 10.0,
        "loss": 14.0,
        "angle": 10.0,
        "aspect": 0.0,  # 180 (south, compass) -> 0 (south, PVGIS convention)
        "outputformat": "json",
    }


def test_fetch_pvgis_generation_converts_compass_azimuth_to_pvgis_aspect(monkeypatch):
    """PVGIS's `aspect` uses 0=South/-90=East/90=West (range -180..180),
    while azimuth_deg here is the same 0=North/90=East/180=South/270=West
    compass convention used by Solar API's roofSegmentStats.azimuthDegrees
    everywhere else in this codebase. A raw pass-through was confirmed
    (against the live API) to be rejected with a 400 for any azimuth
    above 180 — this pins the conversion so it can't regress."""
    captured = {}

    def _fake_get(url, params=None, timeout=None):
        captured["params"] = params
        return _FakeResponse(_canned_response())

    monkeypatch.setattr(httpx, "get", _fake_get)

    pvgis.fetch_pvgis_generation(
        lat=17.385, lng=78.4867, peak_power_kwp=10.0, loss_pct=14.0, tilt_deg=2.0, azimuth_deg=302.69916
    )

    assert captured["params"]["aspect"] == pytest.approx(122.69916)


def test_fetch_pvgis_generation_raises_typed_error_on_http_failure(monkeypatch):
    def _raise(*a, **k):
        raise httpx.ConnectError("network down")

    monkeypatch.setattr(httpx, "get", _raise)

    with pytest.raises(pvgis.PVGISError):
        pvgis.fetch_pvgis_generation(
            lat=17.385, lng=78.4867, peak_power_kwp=10.0, loss_pct=14.0, tilt_deg=10.0, azimuth_deg=0.0
        )


def test_fetch_pvgis_generation_raises_typed_error_on_malformed_response(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse({"outputs": {}}))

    with pytest.raises(pvgis.PVGISError):
        pvgis.fetch_pvgis_generation(
            lat=17.385, lng=78.4867, peak_power_kwp=10.0, loss_pct=14.0, tilt_deg=10.0, azimuth_deg=0.0
        )


def test_fetch_pvgis_generation_uses_injected_client(monkeypatch):
    class _FakeClient:
        def get(self, url, params=None, timeout=None):
            return _FakeResponse(_canned_response())

    def _fail_if_called(*a, **k):
        raise AssertionError("httpx.get should not be called when a client is injected")

    monkeypatch.setattr(httpx, "get", _fail_if_called)

    result = pvgis.fetch_pvgis_generation(
        lat=17.385,
        lng=78.4867,
        peak_power_kwp=10.0,
        loss_pct=14.0,
        tilt_deg=10.0,
        azimuth_deg=0.0,
        client=_FakeClient(),
    )

    assert result["annual_kwh"] == 8234.5
