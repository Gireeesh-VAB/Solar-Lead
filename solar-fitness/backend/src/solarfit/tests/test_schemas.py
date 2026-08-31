"""SITE-02 — per-type JSON Schemas, and USN-05's field-group rule. Person 1."""

import pytest

from solarfit.domain import schemas
from solarfit.domain.site import BILLING_LINKED_SITE_TYPES

LON, LAT = 78.4867, 17.3850


def _payload(site_type: str = "ROOFTOP_RESIDENTIAL", **overrides) -> dict:
    base = {
        "site_type": site_type,
        "name": "Test roof",
        "owner_org": "org-alpha",
        "jurisdiction": "IN-TG",
        "centroid": {"type": "Point", "coordinates": [LON, LAT]},
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------- #
# registry
# --------------------------------------------------------------------- #


def test_every_rooftop_type_has_a_schema():
    assert set(schemas.SITE_SCHEMAS) == {
        "ROOFTOP_RESIDENTIAL",
        "ROOFTOP_CI",
        "ROOFTOP_GOVT",
    }


def test_schemas_are_valid_json_schema_documents():
    for site_type, schema in schemas.SITE_SCHEMAS.items():
        assert schema["$schema"].startswith("https://json-schema.org/")
        assert schema["title"] == site_type
        assert schema["properties"]["site_type"]["const"] == site_type


def test_unknown_site_type_has_no_schema():
    with pytest.raises(schemas.SchemaViolation, match="no schema registered"):
        schemas.schema_for("ROOFTOP_MARTIAN")


# --------------------------------------------------------------------- #
# USN-05 — the field group appears only on billing-linked types
# --------------------------------------------------------------------- #


def test_billing_linked_types_declare_the_usn_group():
    for site_type in BILLING_LINKED_SITE_TYPES:
        props = schemas.SITE_SCHEMAS[site_type]["properties"]
        assert props["usn"]["type"] == ["string", "null"]
        assert "usn_source" in props


def test_govt_schema_forbids_usn_rather_than_omitting_it():
    """§17 non-negotiable: USN absent from non-billing-linked types.
    `False` in JSON Schema means 'this property may not appear' —
    stronger than simply not describing it."""
    props = schemas.SITE_SCHEMAS["ROOFTOP_GOVT"]["properties"]
    assert props["usn"] is False
    assert props["usn_source"] is False


def test_allows_usn_matches_the_frozen_contract():
    assert schemas.allows_usn("ROOFTOP_RESIDENTIAL")
    assert schemas.allows_usn("ROOFTOP_CI")
    assert not schemas.allows_usn("ROOFTOP_GOVT")


def test_usn_on_a_government_site_is_rejected():
    with pytest.raises(schemas.SchemaViolation, match="not billing-linked"):
        schemas.validate_site_payload(_payload("ROOFTOP_GOVT", usn="1234567890"))


def test_usn_source_alone_on_a_government_site_is_also_rejected():
    with pytest.raises(schemas.SchemaViolation, match="usn_source"):
        schemas.validate_site_payload(_payload("ROOFTOP_GOVT", usn_source="manual"))


def test_usn_on_a_residential_site_is_fine():
    schemas.validate_site_payload(_payload("ROOFTOP_RESIDENTIAL", usn="1234567890"))


def test_government_site_without_usn_is_fine():
    schemas.validate_site_payload(_payload("ROOFTOP_GOVT"))


# --------------------------------------------------------------------- #
# required fields
# --------------------------------------------------------------------- #


def test_valid_payload_passes():
    schemas.validate_site_payload(_payload())


@pytest.mark.parametrize("field", ["name", "owner_org", "jurisdiction", "centroid"])
def test_missing_required_field_is_rejected(field):
    payload = _payload()
    payload[field] = None
    with pytest.raises(schemas.SchemaViolation, match=field):
        schemas.validate_site_payload(payload)


def test_missing_site_type_is_rejected():
    with pytest.raises(schemas.SchemaViolation, match="no site_type"):
        schemas.validate_site_payload({"name": "x"})


def test_confidence_outside_zero_to_one_is_rejected():
    with pytest.raises(schemas.SchemaViolation, match="outside 0..1"):
        schemas.validate_site_payload(_payload(geometry_confidence=1.5))


def test_absent_confidence_is_fine():
    schemas.validate_site_payload(_payload(geometry_confidence=None))
