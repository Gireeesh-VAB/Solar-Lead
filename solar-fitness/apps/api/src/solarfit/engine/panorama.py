"""STUB — Owner: Person 3 (AI Pipeline & Cache).

Implements §9.12 3D Visualization (VIZ-01..05) of
Solar_Fitness_Engine_Development_Document_v1.1:

  VIZ-01  Mesh/panorama from boundary + elevation data (trimesh/Open3D).
  VIZ-02  Persist only a reference URL + generation params/version;
          upload the artifact to object storage.
  VIZ-03  Insufficient elevation/imagery -> explicit not_generated status
          + reason. Never fabricate a plausible-looking mesh.
  VIZ-04  Regenerate only on boundary-version change or explicit refresh.
  VIZ-05  Run as an async worker task (workers/), chained after VIS
          completes or is skipped — never in the request path.

Depends on: solarfit.domain.assessment.PanoramaResult (frozen, Day 0).

Add trimesh / Open3D / pyrender to apps/api/pyproject.toml when you
start this (uv add trimesh open3d pyrender or a matplotlib fallback) —
they're deliberately not pre-installed by the Day-0 foundation since
nobody else needs them.
"""

from solarfit.domain.assessment import PanoramaResult


def generate_panorama(boundary: dict, weather: dict | None, params: dict | None = None) -> PanoramaResult:
    """VIZ-01..05. Raises NotImplementedError until Person 3 implements it."""
    raise NotImplementedError
