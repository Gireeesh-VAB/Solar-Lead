"""Owner: Person 1 (Site & Geometry).

Implements GEO-01 of Solar_Fitness_Engine_Development_Document_v1.1: a
GeometryProvider protocol plus a provider-precedence registry that
resolves the applicable provider chain at runtime.

Providers registered here (rooftop-only scope — GEO-03 WATER_INDEX is
on hold, deliberately absent):
  - manual.py       MANUAL_POLYGON  (GEO-02)
  - solar_api.py    SOLAR_API       (GEO-04)
  - imported.py     IMPORTED        (GEO-05)
  - FIELD_MEASURED  (GEO-06) — supersedes any remote geometry; recorded
    through repositories/sites.py's SITE-05 versioning rather than as a
    separate provider module, since it arrives as an edit to an existing
    site rather than a resolution step.

Validation (GEO-07/08) and the confidence function (GEO-09) live in the
sibling validation.py.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from solarfit.domain.site import GeometrySource, Site

__all__ = [
    "APPROXIMATE_SOURCES",
    "PRECEDENCE",
    "GeometryProvider",
    "ProviderNotRegistered",
    "get_provider",
    "is_approximate",
    "outranks",
    "register",
    "registered_providers",
    "resolve_boundary",
]


@runtime_checkable
class GeometryProvider(Protocol):
    id: str
    applies_to: list[str]  # site types

    def resolve(self, site: Site, params: dict) -> dict: ...  # returns a GeoJSON Boundary


class ProviderNotRegistered(LookupError):
    """Raised when no provider is registered under the requested id."""


# GEO-01 precedence. Higher wins. Changing the ordering is a one-line
# edit here and nowhere else — no provider knows its own rank.
#
# Rationale: ground truth beats a human looking at imagery of THIS roof,
# which beats a bulk file of unknown provenance, which beats a fully
# automated remote lookup. Revisit once CAL-01's variance data shows
# which sources actually agree with field measurement.
# GEO-04's Solar API boundary is derived from the response's
# `boundingBox` — a lat/lng RECTANGLE around the building, never a traced
# outline. On a simple house it is close enough to be useful; on an
# L-shaped or irregular roof it is not the roof, and treating it as one is
# how panels end up placed beside a building rather than on it.
#
# Every other source is an actual traced polygon: a surveyor's field
# measurement, an operator's manual trace, or an imported cadastral shape.
APPROXIMATE_SOURCES: frozenset[str] = frozenset({"solar_api"})


def is_approximate(source: GeometrySource | None) -> bool:
    """Whether a boundary from `source` is a bounding box rather than a
    traced roof outline.

    None counts as approximate: a site with no recorded source has no
    evidence anyone traced it, and the safe reading of missing provenance
    is the weaker claim.
    """
    return source is None or source in APPROXIMATE_SOURCES


PRECEDENCE: dict[GeometrySource, int] = {
    "field_measured": 400,
    "manual_polygon": 300,
    "imported": 200,
    "solar_api": 100,
}

_REGISTRY: dict[str, GeometryProvider] = {}


def register(provider: GeometryProvider) -> GeometryProvider:
    """Register a provider under its `id`. Usable as a decorator."""
    if provider.id in _REGISTRY:
        raise ValueError(f"geometry provider {provider.id!r} is already registered")
    if provider.id not in PRECEDENCE:
        raise ValueError(
            f"geometry provider {provider.id!r} has no PRECEDENCE entry — "
            "add one rather than letting it rank implicitly"
        )
    _REGISTRY[provider.id] = provider
    return provider


def get_provider(provider_id: str) -> GeometryProvider:
    try:
        return _REGISTRY[provider_id]
    except KeyError as exc:
        raise ProviderNotRegistered(
            f"no geometry provider registered as {provider_id!r}; registered: {sorted(_REGISTRY)}"
        ) from exc


def registered_providers(site_type: str | None = None) -> list[GeometryProvider]:
    """Providers applicable to `site_type`, highest precedence first."""
    providers = [
        p
        for p in _REGISTRY.values()
        if site_type is None or not p.applies_to or site_type in p.applies_to
    ]
    return sorted(providers, key=lambda p: PRECEDENCE.get(p.id, 0), reverse=True)


def outranks(candidate: GeometrySource | None, incumbent: GeometrySource | None) -> bool:
    """Whether a `candidate` source may replace an `incumbent` one.

    GEO-06's "FIELD_MEASURED supersedes any remote geometry" falls out of
    the precedence table rather than being special-cased. A site with no
    geometry yet is always replaceable.
    """
    if incumbent is None:
        return True
    if candidate is None:
        return False
    return PRECEDENCE.get(candidate, 0) > PRECEDENCE.get(incumbent, 0)


def resolve_boundary(site: Site, provider_id: str, params: dict | None = None) -> dict:
    """Run one named provider. The chain itself is walked by the caller
    (routers/sites.py), which knows whether a lower-ranked source is
    acceptable for the request at hand."""
    return get_provider(provider_id).resolve(site, params or {})
