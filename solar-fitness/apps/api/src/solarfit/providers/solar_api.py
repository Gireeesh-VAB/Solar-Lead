"""STUB — Owner: Person 1 (Site & Geometry).

Implements GEO-04 (SOLAR_API) AND §9.17 Shading Analysis's extraction
half (SHADE-01) of Solar_Fitness_Engine_Development_Document_v1.2:
Google Geocoding (address -> lat/lng) then Google Solar API
buildingInsights:findClosest; parse into the internal Boundary shape.
Record (never raise on) absent/BASE-tier/sparse responses.

  SHADE-01  The same Building Insights response already carries
            per-roof-segment sunshine/shading data (e.g.
            sunshineQuantiles / maxSunshineHoursPerYear) — extract it
            into a ShadingEstimate(source="solar_api", ...) alongside
            the boundary. No new API call, no new imagery. When the
            boundary instead comes from MANUAL_POLYGON/IMPORTED/
            FIELD_MEASURED, leave Site.shading as
            ShadingEstimate(source="unavailable") — SHADE-04 reads that
            as insufficient_data for the shading sub-score, never a
            guess.

Feeds the customer-selected geo-location flow: address/pin -> Google
Maps geocode -> Solar API building insights -> boundary handed to
Person 3's providers/vision.py (VIS) for refinement.

Depends on: solarfit.config.get_settings() for GOOGLE_MAPS_API_KEY /
GOOGLE_SOLAR_API_KEY (frozen, Day 0), solarfit.domain.site.ShadingEstimate
(frozen, Day 0), solarfit.providers.base (same track).
"""

from solarfit.domain.site import Site


def resolve_via_solar_api(site: Site, params: dict) -> dict:
    """GEO-04. Raises NotImplementedError until Person 1 implements it."""
    raise NotImplementedError


def extract_shading_estimate(solar_api_response: dict) -> dict:
    """SHADE-01. Pulls the shading-relevant fields out of the same
    response resolve_via_solar_api() already fetched — never a second
    call. Returns a dict matching ShadingEstimate's shape. Raises
    NotImplementedError until Person 1 implements it."""
    raise NotImplementedError
