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
from solarfit.providers import places, solar_api

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
def test_a_blank_address_is_an_empty_search_not_an_error(address, client, auth):
    """An empty box is not a malformed request — it is a search for
    nothing, which finds nothing. Google is never called either way: an
    empty string is not worth a billable lookup on our key."""
    with patch.object(solar_api, "geocode_address_detailed") as geocoder:
        response = client.get("/app/geocode", params={"address": address}, headers=auth)

    geocoder.assert_not_called()
    assert response.status_code == 200
    assert response.json()["found"] is False


def test_supplying_neither_placeid_nor_address_is_a_caller_error(client, auth):
    """Distinct from a blank one: sending no parameter at all is a bug in
    the caller, not a customer searching for nothing."""
    response = client.get("/app/geocode", headers=auth)
    assert response.status_code == 422


def test_an_over_long_address_is_refused(client, auth):
    """Bounded so the route cannot be used to push arbitrary payloads at
    Google on our key."""
    with patch.object(solar_api, "geocode_address_detailed") as geocoder:
        response = client.get("/app/geocode", params={"address": "x" * 500}, headers=auth)

    assert response.status_code == 422
    geocoder.assert_not_called()


# ---------------------------------------------------------------------------
# Suggestions — the autocomplete half
# ---------------------------------------------------------------------------


def test_suggest_requires_auth(client):
    assert client.get("/app/geocode/suggest", params={"q": "kukat"}).status_code == 401


def test_suggest_returns_googles_own_predictions(client, auth):
    predictions = [
        ("ChIJ_place_1", "Kukatpally, Hyderabad, Telangana, India"),
        ("ChIJ_place_2", "Kukatpally Housing Board Colony, Hyderabad"),
    ]
    with patch.object(places, "suggest_addresses", return_value=predictions) as suggester:
        response = client.get(
            "/app/geocode/suggest", params={"q": "kukat", "session": "tok-1"}, headers=auth
        )

    assert response.status_code == 200
    body = response.json()["suggestions"]
    assert [s["placeId"] for s in body] == ["ChIJ_place_1", "ChIJ_place_2"]
    assert body[0]["description"] == "Kukatpally, Hyderabad, Telangana, India"
    # The session token must reach Google, or every keystroke bills separately.
    suggester.assert_called_once_with("kukat", session_token="tok-1")


def test_suggest_with_no_matches_returns_an_empty_list(client, auth):
    """A half-typed word Google cannot place yet is ordinary, not an error
    — and never a fabricated suggestion."""
    with patch.object(places, "suggest_addresses", return_value=[]):
        response = client.get("/app/geocode/suggest", params={"q": "zzqq"}, headers=auth)

    assert response.status_code == 200
    assert response.json()["suggestions"] == []


def test_suggest_does_not_call_google_for_a_blank_query(client, auth):
    with patch.object(places, "suggest_addresses") as suggester:
        response = client.get("/app/geocode/suggest", params={"q": "   "}, headers=auth)

    suggester.assert_not_called()
    assert response.status_code == 200
    assert response.json()["suggestions"] == []


def test_suggest_provider_failure_is_503(client, auth):
    with patch.object(
        places, "suggest_addresses", side_effect=places.PlacesError("REQUEST_DENIED")
    ):
        response = client.get("/app/geocode/suggest", params={"q": "kukat"}, headers=auth)

    assert response.status_code == 503
    assert "REQUEST_DENIED" not in response.text


# ---------------------------------------------------------------------------
# Resolving a picked suggestion
# ---------------------------------------------------------------------------


def test_geocode_resolves_a_place_id(client, auth):
    with patch.object(places, "resolve_place", return_value=(POINT, FORMATTED)) as resolver:
        response = client.get(
            "/app/geocode", params={"placeId": "ChIJ_abc", "session": "tok-1"}, headers=auth
        )

    assert response.status_code == 200
    body = response.json()
    assert body["found"] is True
    assert body["lat"] == pytest.approx(17.4875418)
    assert body["formatted"] == FORMATTED
    resolver.assert_called_once_with("ChIJ_abc", session_token="tok-1")


def test_place_id_wins_over_a_typed_address(client, auth):
    """The customer picked that specific place; the text in the box is
    only whatever they happened to have typed at the time."""
    with (
        patch.object(places, "resolve_place", return_value=(POINT, FORMATTED)) as resolver,
        patch.object(solar_api, "geocode_address_detailed") as geocoder,
    ):
        client.get(
            "/app/geocode", params={"placeId": "ChIJ_abc", "address": "half typed"}, headers=auth
        )

    resolver.assert_called_once()
    geocoder.assert_not_called()


def test_an_unknown_place_id_is_found_false(client, auth):
    with patch.object(places, "resolve_place", return_value=None):
        response = client.get("/app/geocode", params={"placeId": "stale"}, headers=auth)

    assert response.status_code == 200
    assert response.json()["found"] is False


def test_place_resolution_failure_is_503(client, auth):
    with patch.object(places, "resolve_place", side_effect=places.PlacesError("boom")):
        response = client.get("/app/geocode", params={"placeId": "ChIJ_abc"}, headers=auth)

    assert response.status_code == 503
