"""§16 Testing — routers/app_geocode.py.

The route exists so the browser never needs Geocoding permission, so the
tests that matter are: it requires auth (otherwise it is an open proxy
onto the project's Google quota), and it tells "no such address" apart
from "search is broken" — those two need different words in front of a
customer, and collapsing them sends people hunting for a typo when the
real problem is an API key.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from solarfit.db import get_session
from solarfit.main import app
from solarfit.providers import solar_api

POINT = {"type": "Point", "coordinates": [78.3953462, 17.4875418]}
FORMATTED = "Kukatpally, Hyderabad, Telangana, India"


@pytest.fixture
def client(db_session):
    """current_user() resolves the bearer token against the DB, so the
    request session has to be the same transactional one make_auth_header
    created the user in — otherwise every call is a 401."""
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def auth(make_auth_header):
    return make_auth_header(role="customer", owner_org=None)


def test_geocode_requires_auth(client):
    """An unauthenticated route here is an open geocoding proxy — anyone
    who found the URL could spend the project's quota."""
    response = client.get("/app/geocode", params={"address": "Hyderabad"})
    assert response.status_code == 401


def test_geocode_returns_the_real_point(client, auth):
    with patch.object(
        solar_api, "geocode_address_detailed", return_value=(POINT, FORMATTED)
    ) as geocoder:
        response = client.get("/app/geocode", params={"address": "Kukatpally"}, headers=auth)

    assert response.status_code == 200
    body = response.json()
    assert body["found"] is True
    assert body["lat"] == pytest.approx(17.4875418)
    assert body["lng"] == pytest.approx(78.3953462)
    assert body["formatted"] == FORMATTED
    geocoder.assert_called_once_with("Kukatpally")


def test_address_is_trimmed_before_lookup(client, auth):
    with patch.object(
        solar_api, "geocode_address_detailed", return_value=(POINT, None)
    ) as geocoder:
        client.get("/app/geocode", params={"address": "  Kukatpally  "}, headers=auth)

    geocoder.assert_called_once_with("Kukatpally")


def test_a_missing_formatted_address_is_not_an_error(client, auth):
    with patch.object(solar_api, "geocode_address_detailed", return_value=(POINT, None)):
        body = client.get("/app/geocode", params={"address": "x"}, headers=auth).json()

    assert body["found"] is True
    assert body["formatted"] is None


def test_unknown_address_is_200_not_found_not_an_error(client, auth):
    """A typo or an unknown landmark is ordinary user input, not a failed
    request — the UI needs to say "try another address", which a 4xx would
    not distinguish from a broken one."""
    with patch.object(solar_api, "geocode_address_detailed", return_value=None):
        response = client.get("/app/geocode", params={"address": "zzqqxx"}, headers=auth)

    assert response.status_code == 200
    body = response.json()
    assert body["found"] is False
    assert body["lat"] is None
    assert body["lng"] is None


def test_provider_failure_is_503_not_a_not_found(client, auth):
    """A denied key must never be reported as "we couldn't find that
    address" — that sends everyone hunting for a typo when the real
    problem is an API restriction."""
    with patch.object(
        solar_api,
        "geocode_address_detailed",
        side_effect=solar_api.SolarApiError("geocoding failed: REQUEST_DENIED"),
    ):
        response = client.get("/app/geocode", params={"address": "Hyderabad"}, headers=auth)

    assert response.status_code == 503
    # The customer cannot fix an API restriction; they should not be shown one.
    assert "REQUEST_DENIED" not in response.text


@pytest.mark.parametrize("address", ["", "   "])
def test_blank_addresses_are_rejected_before_reaching_google(address, client, auth):
    with patch.object(solar_api, "geocode_address_detailed") as geocoder:
        response = client.get("/app/geocode", params={"address": address}, headers=auth)

    # Either way Google is never called — an empty string is not worth a
    # billable lookup on our key.
    geocoder.assert_not_called()

    if address == "":
        assert response.status_code == 422  # min_length rejects it outright
    else:
        # Whitespace clears min_length, so the route trims and short-circuits.
        assert response.status_code == 200
        assert response.json()["found"] is False


def test_an_over_long_address_is_refused(client, auth):
    """Bounded so the route cannot be used to push arbitrary payloads at
    Google on our key."""
    with patch.object(solar_api, "geocode_address_detailed") as geocoder:
        response = client.get("/app/geocode", params={"address": "x" * 500}, headers=auth)

    assert response.status_code == 422
    geocoder.assert_not_called()
