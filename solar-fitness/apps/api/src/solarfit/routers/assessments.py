"""STUB — Owner: Person 4 (Scoring, USN & Assessment API).

Implements the core-assessment slice of §9.8 Interface (API-01..05) of
Solar_Fitness_Engine_Development_Document_v1.1 — the orchestration
endpoint that ties every other person's work into the single response
shape.

Depends on (built last, against real implementations at the integration
checkpoints — build against the Day-0 domain contracts + mocks first):
  - solarfit.domain.assessment.AnalysisResult (frozen contract, Day 0)
  - solarfit.repositories.analysis_cache.get_or_create_analysis (Person 3)
  - solarfit.packs.{universal,rooftop} + engine.resolver + engine.generation
    (Person 2)
  - solarfit.engine.fitness, engine.ml_score, providers.usn_ocr (this
    person's own modules)

"Done when": given stub Ceiling-list/CapacityResult fixtures from Person 2
and a stub AnalysisResult from Person 3, FIT and ML produce a verdict +
score independently and testably; USN round-trips through all three
input paths in isolation. This endpoint is deliberately the last piece
wired to real implementations, at Checkpoint 1 (rules-only) and
Checkpoint 2 (full VIS/VIZ/ML/CACHE/USN pipeline).
"""

from fastapi import APIRouter

router = APIRouter(prefix="/v1/assessments", tags=["assessments"])

# TODO(Person 4): POST /{site_id}  — synchronous assessment; cache-hit
#                                     path resolves instantly (API-01/02).
# TODO(Person 4): POST /batch — async batch submission, pollable status
#                                (API-03).
# Every response must stamp engine_version + constraint_pack_version
# (API-04) and live under a versioned path, never breaking the existing
# response shape (API-05).
