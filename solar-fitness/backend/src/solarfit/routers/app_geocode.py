"""Address -> coordinates, for the customer check form.

Exists so the BROWSER never needs Geocoding permission. Google's
Geocoding API is enabled separately from Maps JavaScript, and the key the
frontend ships is a public one: it is embedded in the bundle and visible
to anyone who opens the page, so it is referrer-restricted and
deliberately narrow. Granting it Geocoding too would widen a key that
anyone can copy.

Instead the server geocodes with its own key, which never leaves the
backend and can be IP-restricted. One key needs the API, and it is the
one nobody can read off a web page.

Authenticated on purpose. An unauthenticated geocode route is an open
proxy onto the project's Google quota — anyone who found the URL could
spend it.

Absence is data, not an error: an address Google cannot place comes back
200 with found=false. That is ordinary user input (a typo, a landmark
Google does not know), not a failure of the request. A provider outage or
a misconfigured key is a 503, because those two need different messages
in the UI — one says "try another address", the other says "search is
unavailable, place your pin by hand".
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from solarfit.auth_users import AuthenticatedUser, current_user
from solarfit.providers import solar_api

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/app", tags=["app-geocode"])


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class GeocodeOut(_CamelModel):
    found: bool
    lat: float | None = None
    lng: float | None = None
    formatted: str | None = None


@router.get("/geocode", response_model=GeocodeOut)
def geocode(
    address: Annotated[str, Query(min_length=1, max_length=300)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> GeocodeOut:
    """Resolve a free-text address to a point."""
    query = address.strip()
    if not query:
        # min_length=1 lets "   " through, which would otherwise become a
        # billable lookup for an empty string on our key.
        return GeocodeOut(found=False)

    try:
        found = solar_api.geocode_address_detailed(query)
    except solar_api.SolarApiError as exc:
        # A denied or unconfigured key, or Google being unreachable. Real
        # reason to the log, a usable message to the caller — the customer
        # cannot fix an API restriction, but they can place a pin.
        logger.exception("Geocoding unavailable for %r", address)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Address search is temporarily unavailable",
        ) from exc

    if found is None:
        return GeocodeOut(found=False)

    point, formatted = found
    lng, lat = point["coordinates"]
    # `formatted` is echoed back so the customer can see WHICH place was
    # matched — "Kukatpally, Hyderabad" and a bare pin are very different
    # levels of confidence about whether the search worked.
    return GeocodeOut(found=True, lat=lat, lng=lng, formatted=formatted)
