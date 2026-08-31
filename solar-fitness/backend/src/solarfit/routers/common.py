"""Shared /app/* router helpers.

`app_auth.py` established the camelCase-response convention (JSON keys
match lib/types.ts field-for-field) with a locally-defined `_CamelModel`.
This module gives every router after it the same base class from one
place, rather than each file redefining it — app_auth.py itself is left
untouched; this is purely additive for the routers built after it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

__all__ = ["CamelModel"]


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
