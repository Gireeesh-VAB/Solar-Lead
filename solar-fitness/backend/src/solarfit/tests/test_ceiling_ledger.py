"""§16 Testing — CON-04's ceiling ledger reaching the frontend.

These ceilings were always computed and stored in `capacity`; the ledger
was hardcoded to [] on the way out, so the customer saw a kWp figure and
a constraint NAME with nothing behind it.

The assertion that matters most is the one about `kwp: None`. A ceiling
that could not be evaluated must not arrive as 0: "we haven't checked
this" and "this limits you to nothing" are opposite claims, and a zero
would render as the second — telling a customer their roof is worthless
because a DISCOM field was blank.
"""

from types import SimpleNamespace

import pytest

from solarfit.repositories.assessments import ceiling_ledger, to_frontend_assessment_dict

CEILINGS = [
    {
        "constraint": "usable_area",
        "ceiling_kwp": 41.409,
        "reason": "207.0 m2 usable area at 0.2 kWp/m2",
        "kind": "physical",
        "status": "ok",
    },
    {
        "constraint": "consumption_offset",
        "ceiling_kwp": 1.2857,
        "reason": "sized to offset 100% of 1800.0 kWh/yr consumption",
        "kind": "commercial",
        "status": "ok",
    },
    {
        "constraint": "transformer_headroom",
        "ceiling_kwp": None,
        "reason": "transformer_kva not provided",
        "kind": "regulatory",
        "status": "insufficient_data",
    },
]


def _row(**overrides):
    defaults = {
        "id": "a-1",
        "site_id": "s-1",
        "verdict": "SUITABLE_SUBJECT_TO_SURVEY",
        "score": 0.6,
        "confidence": 0.5,
        "binding_constraint": "consumption_offset",
        "reasons": ["sized to consumption"],
        "capacity": {
            "recommended_kwp": 1.2857,
            "max_technical_kwp": 41.409,
            "headroom_kwp": 40.123,
            "ceilings": CEILINGS,
        },
        "usable_area_m2": 207.045,
        "panorama_url": None,
        "ml_suitability_score": None,
        "cache_hit": False,
        "engine_version": "test",
        "created_at": SimpleNamespace(isoformat=lambda: "2026-09-03T00:00:00Z"),
    }
    return SimpleNamespace(**{**defaults, **overrides})


def test_every_stored_ceiling_reaches_the_ledger():
    ledger = ceiling_ledger(_row())

    assert [entry["label"] for entry in ledger] == [
        "usable_area",
        "consumption_offset",
        "transformer_headroom",
    ]


def test_an_unevaluated_ceiling_keeps_null_not_zero():
    """The regression this guards: 0 kWp would tell a customer their roof
    is worthless because a DISCOM field was blank."""
    ledger = ceiling_ledger(_row())
    unevaluated = next(e for e in ledger if e["label"] == "transformer_headroom")

    assert unevaluated["kwp"] is None
    assert unevaluated["kwp"] != 0
    assert unevaluated["status"] == "insufficient_data"


def test_the_binding_constraint_is_flagged():
    ledger = ceiling_ledger(_row())

    binding = [e["label"] for e in ledger if e["is_binding"]]
    assert binding == ["consumption_offset"]


def test_binding_flag_follows_the_row_not_a_hardcoded_name():
    """Consumption is NOT always the deciding limit — a roof with no bill
    is capped by area instead."""
    ledger = ceiling_ledger(_row(binding_constraint="usable_area"))

    assert [e["label"] for e in ledger if e["is_binding"]] == ["usable_area"]


def test_reason_and_kind_survive_the_trip():
    ledger = ceiling_ledger(_row())
    area = next(e for e in ledger if e["label"] == "usable_area")

    assert area["note"] == "207.0 m2 usable area at 0.2 kWp/m2"
    assert area["kind"] == "physical"
    assert area["kwp"] == pytest.approx(41.409)


def test_frontend_dict_carries_the_ledger_and_its_context():
    data = to_frontend_assessment_dict(_row())

    assert len(data["ceiling_ledger"]) == 3
    assert data["usable_area_m2"] == pytest.approx(207.045)
    assert data["max_technical_kwp"] == pytest.approx(41.409)
    assert data["headroom_kwp"] == pytest.approx(40.123)


@pytest.mark.parametrize("capacity", [None, {}, {"ceilings": []}])
def test_a_missing_ledger_is_empty_not_an_error(capacity):
    """Older assessments predate this and must not break the result page."""
    data = to_frontend_assessment_dict(_row(capacity=capacity))

    assert data["ceiling_ledger"] == []
    assert data["max_technical_kwp"] is None
    assert data["headroom_kwp"] is None


def test_a_ceiling_missing_optional_fields_still_renders():
    """Defensive: a ceiling written by an older engine version should not
    take the whole page down over an absent `kind`."""
    ledger = ceiling_ledger(_row(capacity={"ceilings": [{"constraint": "usable_area"}]}))

    assert ledger[0]["label"] == "usable_area"
    assert ledger[0]["kwp"] is None
    assert ledger[0]["kind"] == "physical"
    assert ledger[0]["status"] == "ok"
