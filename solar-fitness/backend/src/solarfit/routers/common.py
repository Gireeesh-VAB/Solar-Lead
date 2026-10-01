"""Shared /app/* router helpers.

`app_auth.py` established the camelCase-response convention (JSON keys
match lib/types.ts field-for-field) with a locally-defined `_CamelModel`.
This module gives every router after it the same base class from one
place, rather than each file redefining it — app_auth.py itself is left
untouched; this is purely additive for the routers built after it.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict
from pydantic.alias_generators import to_camel

if TYPE_CHECKING:
    from fastapi import Request

    from solarfit.auth_users import AuthenticatedUser

__all__ = ["PHONE_ERROR_MESSAGE", "CamelModel", "IndianMobile", "actor_audit_fields", "request_audit_meta"]


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# Every phone field across the app (customer profile, vendor contact
# details) is optional but, when present, must be a real Indian mobile
# number — 10 digits, starting 6-9, matching the frontend's zod schemas
# in lib/validation/phone.ts so a number rejected client-side can never
# reach here, and one that somehow does still gets rejected the same way.
PHONE_ERROR_MESSAGE = "Please enter a valid 10-digit mobile number."
_INDIAN_MOBILE_PATTERN = re.compile(r"^[6-9]\d{9}$")


def _validate_indian_mobile(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    if trimmed == "":
        # Blank/whitespace-only clears the field rather than erroring —
        # these are all optional "no phone on file" is a valid state.
        return None
    if not _INDIAN_MOBILE_PATTERN.fullmatch(trimmed):
        raise ValueError(PHONE_ERROR_MESSAGE)
    return trimmed


IndianMobile = Annotated[str | None, BeforeValidator(_validate_indian_mobile)]


def actor_audit_fields(user: AuthenticatedUser) -> dict[str, str | None]:
    """The identity half of an audit_repo.write_audit_log() call, built
    the same way at every call site rather than each router re-deriving
    actor_id/actor_type/actor_role from AuthenticatedUser by hand.
    actor_type mirrors actor_role today (this app's three roles — admin,
    vendor, customer — are also its only actor types); kept as two
    separate kwargs to match the spec's field list and leave room for a
    future non-human actor_type ("system") without a schema change."""
    return {
        "actor": user.email,
        "actor_id": user.id,
        "actor_type": user.role,
        "actor_role": user.role,
    }


def request_audit_meta(request: Request) -> dict[str, str | None]:
    """ip_address/user_agent for an audit_repo.write_audit_log() call.
    request.client is None under some ASGI test transports, so this
    never assumes it's set."""
    return {
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }
