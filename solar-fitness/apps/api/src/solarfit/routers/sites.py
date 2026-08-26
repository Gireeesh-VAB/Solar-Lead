"""STUB — Owner: Person 1 (Site & Geometry).

Implements the site-creation/read/list slice of §9.8 Interface (API-06),
per FR §11's routers/sites.py. Covers: SITE-01..07 CRUD surface,
GEO-01..09 provider orchestration on create, AREA-01..06 usable-area
computation, and API-06 (API-key auth + per-tenant rate limiting).

Depends on:
  - solarfit.domain.site.Site (frozen contract, Day 0 — already available)
  - solarfit.repositories.sites (this person's own repository, task 4)
  - solarfit.providers.{base,manual,solar_api,imported} (this person's
    own providers, tasks 5-8)
  - solarfit.engine.area (this person's own usable-area math, task 11)

"Done when" (see Rooftop_Backend_Implementation_Plan.html): an address
can be POSTed, geocoded, resolved via the Solar API, stored with a
versioned boundary, and returns a computed usable area.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/v1/sites", tags=["sites"])

# TODO(Person 1): POST /  — create a site (SITE-01/02/03), queue geometry
#                            resolution (GEO-01..09), compute usable area
#                            (AREA-01..06).
# TODO(Person 1): GET /{site_id} — fetch a single site.
# TODO(Person 1): GET /  — tenant-scoped list.
