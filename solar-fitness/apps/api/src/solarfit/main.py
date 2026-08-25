"""FastAPI app entrypoint — Day 0 scaffold.

Run with: uv run uvicorn solarfit.main:app --reload
"""

from fastapi import FastAPI

from solarfit.routers import assessments, imports, sites

app = FastAPI(title="Solar Site Fitness & Capacity Engine — Rooftop API")

app.include_router(sites.router)
app.include_router(imports.router)
app.include_router(assessments.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
