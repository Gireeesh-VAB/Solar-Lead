"""STUB — Owner: Person 4 (Scoring, USN & Assessment API).

Implements §9.7 Fitness Scoring (FIT-01..07) AND the scoring half of
§9.17 Shading Analysis (SHADE-04) of
Solar_Fitness_Engine_Development_Document_v1.2 — the deterministic,
reproducible verdict. This is the SOLE authoritative output; the ML
score (engine/ml_score.py) is additive metadata and must never override
it (FIT-06, §17).

  FIT-01  Weighted-component score from the scoring profile for the site type.
  FIT-02  Verdict: SUITABLE | SUITABLE_SUBJECT_TO_SURVEY | CONDITIONAL |
          INSUFFICIENT_DATA | NOT_SUITABLE.
  FIT-03  INSUFFICIENT_DATA takes precedence over any computed score.
  FIT-04  Confidence from geometry source, imagery recency, constraint
          completeness, gate resolution, calibration state.
  FIT-05  Human-readable reason list naming the binding constraint.
  FIT-06  Verdict/capacity always ship with confidence + binding
          constraint; this stays authoritative over the ML score.
  FIT-07  Attach the standard pre-feasibility limitations statement.
  SHADE-04  site.shading.shading_score is one of FIT-01's weighted
            components (alongside roof area, orientation, consumption
            offset). When site.shading.source == "unavailable", return
            INSUFFICIENT_DATA for that sub-component specifically —
            never assume zero or full shading, and never let it silently
            drag the overall score.

Depends on: solarfit.domain.constraint.CapacityResult (Person 2's
output, frozen contract), solarfit.domain.site.Site (frozen, Day 0, now
carries .shading — see domain/site.py's ShadingEstimate).
"""

from typing import Literal

from solarfit.domain.constraint import CapacityResult
from solarfit.domain.site import Site

FitnessVerdict = Literal[
    "SUITABLE",
    "SUITABLE_SUBJECT_TO_SURVEY",
    "CONDITIONAL",
    "INSUFFICIENT_DATA",
    "NOT_SUITABLE",
]


def score_fitness(site: Site, capacity: CapacityResult, params: dict | None = None) -> dict:
    """FIT-01..07. Raises NotImplementedError until Person 4 implements it."""
    raise NotImplementedError
