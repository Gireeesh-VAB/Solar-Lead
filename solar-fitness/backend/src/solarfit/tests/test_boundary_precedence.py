"""§16 Testing — GEO-01 precedence, applied where it actually decides.

The precedence table has always been right (field_measured 400 >
manual_polygon 300 > imported 200 > solar_api 100), but
orchestrate_assessment() ignored it: it overwrote the site's boundary
with the cached Solar API one unconditionally.

That made the survey flow pointless. A surveyor could stand on the roof,
trace it, have the polygon validated, versioned through SITE-05 and
stored — and the very next assessment would throw it away and measure
Google's bounding rectangle instead. The customer's usable area, and
therefore their system size, would still come from a box.
"""

import pytest

from solarfit.providers.base import PRECEDENCE, is_approximate, outranks

# ---------------------------------------------------------------------------
# The table itself
# ---------------------------------------------------------------------------


def test_a_traced_roof_outranks_the_solar_api_rectangle():
    assert outranks("manual_polygon", "solar_api")
    assert outranks("field_measured", "solar_api")
    assert outranks("imported", "solar_api")


def test_the_solar_api_rectangle_never_replaces_a_traced_roof():
    """The direction that matters: a re-resolve must not clobber a survey."""
    assert not outranks("solar_api", "manual_polygon")
    assert not outranks("solar_api", "field_measured")
    assert not outranks("solar_api", "imported")


def test_a_field_measurement_supersedes_every_remote_source():
    """GEO-06 falls out of the table rather than being special-cased."""
    assert PRECEDENCE["field_measured"] == max(PRECEDENCE.values())
    for other in PRECEDENCE:
        if other != "field_measured":
            assert outranks("field_measured", other)


# ---------------------------------------------------------------------------
# Approximate vs traced
# ---------------------------------------------------------------------------


def test_only_the_solar_api_boundary_is_approximate():
    """It is derived from the response's `boundingBox` — a rectangle
    around the building, not its outline."""
    assert is_approximate("solar_api")
    assert not is_approximate("manual_polygon")
    assert not is_approximate("field_measured")
    assert not is_approximate("imported")


def test_unknown_provenance_is_treated_as_approximate():
    """No recorded source is no evidence anyone traced it, so the safe
    reading is the weaker claim."""
    assert is_approximate(None)


# ---------------------------------------------------------------------------
# The guard the assessment actually uses
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "should_use_site_boundary"),
    [
        ("field_measured", True),
        ("manual_polygon", True),
        ("imported", True),
        ("solar_api", False),
        (None, False),
    ],
)
def test_the_assessment_guard_picks_the_better_boundary(source, should_use_site_boundary):
    """`outranks(site.geometry_source, "solar_api")` is the exact
    expression orchestrate_assessment() branches on. A traced source keeps
    the site's own geometry; an approximate one — or an equal one — falls
    back to the cached pipeline boundary, which carries VIS/OBS
    refinement the raw stored boundary does not."""
    uses_site = outranks(source, "solar_api")

    assert uses_site is should_use_site_boundary


def test_the_guard_is_present_in_the_router():
    """Pinned against the source: exercising orchestrate_assessment() end
    to end needs the whole pipeline stood up, and what matters here is
    that the branch exists at all — its absence is the bug."""
    import inspect

    import solarfit.routers.assessments as router

    source = inspect.getsource(router.orchestrate_assessment)
    assert 'outranks(site.geometry_source, "solar_api")' in source
    # And the fallback is still there for the case where a box is all we have.
    assert 'update={"boundary": analysis.boundary}' in source
