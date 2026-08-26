"""STUB — Owner: Person 4 (Scoring, USN & Assessment API).

Implements §9.9 Calibration (CAL-01..05) of
Solar_Fitness_Engine_Development_Document_v1.1:

  CAL-01  On field survey submission, compute variance between remote
          and measured usable area; store the labelled pair with site
          type, region, geometry source, class.
  CAL-02  Flag variance-exceeds-threshold records; mark the remote
          estimate superseded.
  CAL-03  Recompute utilisation factors per class once the sample count
          crosses a threshold — surface for approval, never apply
          silently. Coordinate the config value itself with Person 2
          (solarfit.packs.config_pack).
  CAL-04  (Should) Variance-distribution report.
  CAL-05  Feed calibration state into FIT-04 confidence and the ML
          retraining set (engine/ml_score.py).

Depends on: solarfit.domain.site.Site (frozen, Day 0).
"""


def record_field_survey(site_id: str, measured_area_m2: float) -> dict:
    """CAL-01/02. Raises NotImplementedError until Person 4 implements it."""
    raise NotImplementedError


def propose_utilisation_factor_update(site_type: str) -> dict | None:
    """CAL-03. Raises NotImplementedError until Person 4 implements it."""
    raise NotImplementedError
