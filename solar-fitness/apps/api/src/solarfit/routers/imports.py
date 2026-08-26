"""STUB — Owner: Person 1 (Site & Geometry).

Implements API-07 (bulk import) and SITE-07 (duplicate detection) of
Solar_Fitness_Engine_Development_Document_v1.1, plus API-08/09
(export, webhook) since they're a direct extension of this person's own
IMPORTED provider work.

Depends on:
  - solarfit.providers.imported (this person's own provider, task 8)
  - solarfit.repositories.sites (this person's own repository, task 4)
"""

from fastapi import APIRouter

router = APIRouter(prefix="/v1/imports", tags=["imports"])

# TODO(Person 1): POST /  — bulk CSV/GeoJSON/shapefile import, per-row
#                            validation + error report (API-07); duplicate
#                            detection on create/import (SITE-07).
# TODO(Person 1): GET /export — CSV/GeoJSON/PDF export (API-08).
# TODO(Person 1): webhook emitter on assessment completion (API-09) —
#                  likely a Celery task in workers/, dispatched from
#                  Person 4's routers/assessments.py, registered here.
