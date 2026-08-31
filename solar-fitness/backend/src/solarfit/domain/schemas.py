"""Owner: Person 1 (Site & Geometry).

SITE-02 — a registered JSON Schema per rooftop site type, validated on
create/update.

Why a schema registry and not just Pydantic
-------------------------------------------
`Site` (domain/site.py) is the frozen shape every person codes against —
it says what fields EXIST. These schemas say what each site TYPE
requires, which differs per type and changes without touching the shared
contract. Keeping them apart means adding a rooftop type is a new schema
file, not an edit to a model four people import.

The USN field group (USN-05)
----------------------------
`usn` / `usn_source` appear ONLY in the residential and C&I schemas.
ROOFTOP_GOVT is not billing-linked, so the schema forbids the field
outright rather than merely omitting it — a government site carrying a
consumer number would be data we have no basis to hold, and §17 lists
"USN absent from non-billing-linked site types" as a non-negotiable.
Person 4 owns what goes IN the field (USN-01..06); this owns whether the
field may exist at all.
"""

from __future__ import annotations

from typing import Any

from solarfit.domain.site import BILLING_LINKED_SITE_TYPES, RoofSiteType

__all__ = [
    "SITE_SCHEMAS",
    "SchemaViolation",
    "allows_usn",
    "schema_for",
    "validate_site_payload",
]

_GEOJSON_POINT: dict[str, Any] = {
    "type": "object",
    "required": ["type", "coordinates"],
    "properties": {
        "type": {"const": "Point"},
        "coordinates": {
            "type": "array",
            "minItems": 2,
            "maxItems": 3,
            "items": {"type": "number"},
        },
    },
}

_GEOJSON_POLYGON: dict[str, Any] = {
    "type": "object",
    "required": ["type", "coordinates"],
    "properties": {
        "type": {"const": "Polygon"},
        "coordinates": {"type": "array", "minItems": 1, "items": {"type": "array"}},
    },
}

_USN_GROUP: dict[str, Any] = {
    "usn": {
        "type": ["string", "null"],
        "minLength": 3,
        "maxLength": 64,
        "description": "Utility service number (USN-01). Billing-linked types only.",
    },
    "usn_source": {
        "type": ["string", "null"],
        "enum": ["manual", "bill_ocr", "payment_proof_ocr", None],
        "description": "Which of USN-02/03's three paths supplied the value.",
    },
}


def _base_schema(site_type: RoofSiteType, *, extra_required: list[str] | None = None) -> dict:
    schema: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://solarfit.local/schemas/site/{site_type.lower()}.json",
        "title": site_type,
        "type": "object",
        "required": ["site_type", "name", "owner_org", "jurisdiction", "centroid"],
        "properties": {
            "site_type": {"const": site_type},
            "name": {"type": "string", "minLength": 1, "maxLength": 255},
            "owner_org": {"type": "string", "minLength": 1, "maxLength": 255},
            "jurisdiction": {"type": "string", "minLength": 2, "maxLength": 32},
            "centroid": _GEOJSON_POINT,
            "boundary": {"oneOf": [_GEOJSON_POLYGON, {"type": "null"}]},
            "geometry_source": {
                "type": ["string", "null"],
                "enum": ["manual_polygon", "solar_api", "imported", "field_measured", None],
            },
            "geometry_confidence": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
        },
    }
    if extra_required:
        schema["required"].extend(extra_required)

    if site_type in BILLING_LINKED_SITE_TYPES:
        schema["properties"].update(_USN_GROUP)
    else:
        # USN-05 / §17: not merely absent — forbidden.
        schema["properties"]["usn"] = False
        schema["properties"]["usn_source"] = False

    return schema


SITE_SCHEMAS: dict[str, dict] = {
    "ROOFTOP_RESIDENTIAL": _base_schema("ROOFTOP_RESIDENTIAL"),
    "ROOFTOP_CI": _base_schema("ROOFTOP_CI"),
    "ROOFTOP_GOVT": _base_schema("ROOFTOP_GOVT"),
}


class SchemaViolation(ValueError):
    """SITE-02. The payload does not satisfy its type's schema."""


def schema_for(site_type: str) -> dict:
    try:
        return SITE_SCHEMAS[site_type]
    except KeyError as exc:
        raise SchemaViolation(
            f"no schema registered for site type {site_type!r}; "
            f"known types: {sorted(SITE_SCHEMAS)}"
        ) from exc


def allows_usn(site_type: str) -> bool:
    """USN-05. Whether this type may carry a consumer number at all."""
    return site_type in BILLING_LINKED_SITE_TYPES


def validate_site_payload(payload: dict) -> None:
    """SITE-02. Validate a site payload against its registered schema.

    Deliberately hand-rolled against the schema dicts rather than pulling
    in a full JSON Schema engine: the rules that actually matter here are
    required-fields and the USN prohibition, and a dependency that runs
    on every write should earn its place. The schemas stay valid JSON
    Schema documents so they can be published to API consumers and
    enforced by a real validator later if the rules grow.
    """
    site_type = payload.get("site_type")
    if not site_type:
        raise SchemaViolation("payload has no site_type")

    schema = schema_for(site_type)

    missing = [f for f in schema["required"] if payload.get(f) in (None, "")]
    if missing:
        raise SchemaViolation(
            f"{site_type} requires {', '.join(sorted(missing))}"
        )

    if not allows_usn(site_type):
        present = [f for f in ("usn", "usn_source") if payload.get(f) is not None]
        if present:
            raise SchemaViolation(
                f"{site_type} is not billing-linked and must not carry "
                f"{', '.join(present)} (USN-05)"
            )

    confidence = payload.get("geometry_confidence")
    if confidence is not None and not (0.0 <= float(confidence) <= 1.0):
        raise SchemaViolation(f"geometry_confidence {confidence} is outside 0..1")
