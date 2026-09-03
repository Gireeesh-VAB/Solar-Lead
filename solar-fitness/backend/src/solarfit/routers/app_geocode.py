"""Address search for the customer check form: suggestions, then a point.

Exists so the BROWSER never needs Geocoding or Places permission. Those
APIs are enabled separately from Maps JavaScript, and the key the frontend
ships is public: it is embedded in the bundle and visible to anyone who
opens the page, so it is referrer-restricted and deliberately narrow.
Granting it Geocoding or Places would widen a key that anyone can copy.

Instead the server does the lookups with its own key, which never leaves
the backend and can be IP-restricted. One key needs those APIs, and it is
the one nobody can read off a web page.

Two endpoints, in the order the UI calls them:

  GET /app/geocode/suggest?q=...        typing -> ranked suggestions
  GET /app/geocode?placeId=... | address=...   -> a point

Both authenticated. An unauthenticated route here is an open proxy onto
the project's Google quota — anyone who found the URL could spend it.

Absence is data, not an error: a query Google cannot place comes back 200
with found=false or an empty list. That is ordinary user input (a typo, a
half-typed word), not a failed request. A provider outage or a
misconfigured key is a 503, because those two need different messages in
the UI — one says "try another address", the other says "search is
unavailable, place your pin by hand".
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from solarfit.auth_users import AuthenticatedUser, current_user
from solarfit.providers import places, solar_api

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/app", tags=["app-geocode"])

_UNAVAILABLE = "Address search is temporarily unavailable"


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SuggestionOut(_CamelModel):
    place_id: str
    description: str


class SuggestionsOut(_CamelModel):
    suggestions: list[SuggestionOut] = Field(default_factory=list)


class GeocodeOut(_CamelModel):
    found: bool
    lat: float | None = None
    lng: float | None = None
    formatted: str | None = None


@router.get("/geocode/suggest", response_model=SuggestionsOut)
def suggest(
    q: Annotated[str, Query(min_length=1, max_length=300)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
    session: Annotated[str | None, Query(max_length=100)] = None,
) -> SuggestionsOut:
    """Ranked address suggestions for partial input.

    `session` groups a burst of keystrokes and the resolve that follows
    into one billable Places session; without it Google bills per
    keystroke. The client generates it and discards it after a selection.
    """
    query = q.strip()
    if not query:
        # min_length=1 lets "   " through, which would otherwise become a
        # billable lookup for an empty string on our key.
        return SuggestionsOut()

    try:
        found = places.suggest_addresses(query, session_token=session)
    except places.PlacesError as exc:
        logger.exception("Address suggestions unavailable for %r", query)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _UNAVAILABLE) from exc

    return SuggestionsOut(
        suggestions=[SuggestionOut(place_id=pid, description=text) for pid, text in found]
    )


@router.get("/geocode", response_model=GeocodeOut)
def geocode(
    user: Annotated[AuthenticatedUser, Depends(current_user)],
    address: Annotated[str | None, Query(max_length=300)] = None,
    place_id: Annotated[str | None, Query(alias="placeId", max_length=400)] = None,
    session: Annotated[str | None, Query(max_length=100)] = None,
) -> GeocodeOut:
    """Resolve a point, from either a picked suggestion or free text.

    `placeId` wins when both are given: the customer chose that specific
    place, and the text in the box is only what they happened to have
    typed at the time.
    """
    # Neither parameter supplied at all is a caller error. Supplying one
    # that is blank or whitespace is an EMPTY SEARCH, which is ordinary —
    # it answers "nothing found" rather than rejecting the request, and
    # never becomes a billable lookup for an empty string on our key.
    if place_id is None and address is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Provide either placeId or address"
        )
    if not (place_id or "").strip() and not (address or "").strip():
        return GeocodeOut(found=False)

    try:
        if (place_id or "").strip():
            found = places.resolve_place(place_id, session_token=session)
        else:
            found = solar_api.geocode_address_detailed(address.strip())
    except (places.PlacesError, solar_api.SolarApiError) as exc:
        # A denied or unconfigured key, or Google being unreachable. Real
        # reason to the log, a usable message to the caller — the customer
        # cannot fix an API restriction, but they can place a pin.
        logger.exception("Geocoding unavailable for %r / %r", address, place_id)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _UNAVAILABLE) from exc

    if found is None:
        return GeocodeOut(found=False)

    point, formatted = found
    lng, lat = point["coordinates"]
    # `formatted` is echoed back so the customer can see WHICH place was
    # matched — "Kukatpally, Hyderabad" and a bare pin are very different
    # levels of confidence about whether the search worked.
    return GeocodeOut(found=True, lat=lat, lng=lng, formatted=formatted)
