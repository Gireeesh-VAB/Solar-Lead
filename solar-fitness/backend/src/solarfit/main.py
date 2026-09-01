"""FastAPI app entrypoint — Day 0 scaffold.

Run with: uv run uvicorn solarfit.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from solarfit.config import get_settings
from solarfit.routers import (
    app_admin_engine,
    app_admin_platform,
    app_admin_vendors,
    app_assessments,
    app_auth,
    app_calibration_ml,
    app_checks,
    app_imports,
    app_jurisdictions,
    app_sites,
    app_usn,
    app_vendor,
    assessments,
    imports,
    sites,
)

app = FastAPI(title="Solar Site Fitness & Capacity Engine — Rooftop API")

# CORS: the /app/* web frontend is served from a separate origin. Explicit
# allowlist (Settings.cors_allowed_origins), never a wildcard — bearer
# tokens are involved. The existing /sites, /v1/* integration API doesn't
# need this (server-to-server, no browser involved), so this is scoped to
# what the new auth surface actually requires, not a blanket app-wide change.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sites.router)
app.include_router(imports.router)
app.include_router(assessments.router)
app.include_router(app_auth.router)
app.include_router(app_sites.router)
app.include_router(app_imports.router)
app.include_router(app_admin_platform.router)
app.include_router(app_admin_engine.router)
app.include_router(app_vendor.router)
app.include_router(app_admin_vendors.router)
app.include_router(app_jurisdictions.router)
app.include_router(app_calibration_ml.router)
app.include_router(app_usn.router)
app.include_router(app_assessments.router)
app.include_router(app_checks.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
