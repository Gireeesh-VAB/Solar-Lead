"""Owner: Person 1 (Site & Geometry).

Address autocomplete, via Google's Places API (New).

Separate from providers/solar_api.py's geocode_address(): Geocoding is
built to resolve a COMPLETE address and returns a single best match, so
it is the wrong tool for someone half-way through typing. Measured on
this project's key — "kukat" returns 4 useful predictions from Places and
1 result from Geocoding, and a bare "a1" geocodes confidently to Golconda
Fort, which is how a customer ends up pinned to a monument.

Two calls, in the order the UI makes them:

  suggest_addresses()   partial text -> [(place_id, description)]
  resolve_place()       place_id     -> coordinates

Both take a session token. Google bills autocomplete per KEYSTROKE unless
the requests are grouped: one token shared across a burst of typing plus
the final resolve is billed as a single session. Passing None still works
and simply costs more, so the token is optional rather than required.

Never invents a suggestion. No predictions means an empty list, and the
caller shows nothing rather than a plausible-looking guess.
"""

import logging

import httpx

from solarfit.config import get_settings

logger = logging.getLogger(__name__)

_AUTOCOMPLETE_URL = "https://places.googleapis.com/v1/places:autocomplete"
_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"

TIMEOUT_SECONDS = 10.0

# This is an India-only rooftop product — INR tariffs, USN capture, state
# DISCOM rules — so predictions are biased to India rather than returning
# a Hyderabad customer results from Hyderabad, Pakistan. A bias, not a
# filter: Google still ranks within the country.
_REGION_CODES = ["in"]

# Enough to choose from without turning the box into a wall of text.
_MAX_SUGGESTIONS = 6


class PlacesError(RuntimeError):
    """The Places API could not be reached or refused the request.

    Distinct from "no matches": one is a configuration or network problem
    the customer cannot act on, the other is ordinary typing."""


def _api_key() -> str:
    settings = get_settings()
    key = settings.google_maps_api_key or settings.google_solar_api_key
    if not key:
        raise PlacesError("no Google API key configured — set GOOGLE_MAPS_API_KEY in backend/.env")
    return key


def suggest_addresses(
    query: str, *, session_token: str | None = None, client: httpx.Client | None = None
) -> list[tuple[str, str]]:
    """Partial text -> up to _MAX_SUGGESTIONS (place_id, description) pairs.

    Returns [] when Google has nothing to offer — an empty result is
    ordinary for a half-typed word, not a failure.
    """
    query = query.strip()
    if not query:
        return []

    body: dict = {"input": query, "includedRegionCodes": _REGION_CODES}
    if session_token:
        body["sessionToken"] = session_token

    owns_client = client is None
    client = client or httpx.Client(timeout=TIMEOUT_SECONDS)
    try:
        response = client.post(
            _AUTOCOMPLETE_URL,
            headers={"Content-Type": "application/json", "X-Goog-Api-Key": _api_key()},
            json=body,
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as exc:
        raise PlacesError(f"places autocomplete failed: {exc}") from exc
    finally:
        if owns_client:
            client.close()

    suggestions: list[tuple[str, str]] = []
    for entry in (payload.get("suggestions") or [])[:_MAX_SUGGESTIONS]:
        prediction = entry.get("placePrediction") or {}
        place_id = prediction.get("placeId")
        description = (prediction.get("text") or {}).get("text")
        # A prediction missing either half cannot be selected, so it is
        # dropped rather than rendered as an unclickable row.
        if place_id and description:
            suggestions.append((place_id, description))
    return suggestions


def resolve_place(
    place_id: str, *, session_token: str | None = None, client: httpx.Client | None = None
) -> tuple[dict, str | None] | None:
    """place_id -> (GeoJSON Point, formatted address), or None if unknown.

    Same return shape as solar_api.geocode_address_detailed(), so the
    router can treat a picked suggestion and a typed address identically.
    """
    place_id = place_id.strip()
    if not place_id:
        return None

    owns_client = client is None
    client = client or httpx.Client(timeout=TIMEOUT_SECONDS)
    try:
        response = client.get(
            _DETAILS_URL.format(place_id=place_id),
            headers={
                "X-Goog-Api-Key": _api_key(),
                # Field mask is mandatory on the New API, and narrowing it
                # to what we use also lowers the billing tier.
                "X-Goog-FieldMask": "location,formattedAddress",
            },
            params={"sessionToken": session_token} if session_token else None,
        )
        if response.status_code == 404:
            return None  # a stale or fabricated place_id
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as exc:
        raise PlacesError(f"place details failed: {exc}") from exc
    finally:
        if owns_client:
            client.close()

    location = payload.get("location") or {}
    lat, lng = location.get("latitude"), location.get("longitude")
    if lat is None or lng is None:
        logger.info("Place %s carried no location", place_id)
        return None

    point = {"type": "Point", "coordinates": [float(lng), float(lat)]}
    return point, payload.get("formattedAddress")
