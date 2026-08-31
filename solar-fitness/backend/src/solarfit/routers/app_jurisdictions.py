"""Owner: keerthana (Vendor domain, customer-account admin, jurisdictions).

GET /app/jurisdictions — a small admin reference screen listing which
state-specific constraint-pack overrides exist. packs/registry.py is
the one place jurisdiction overrides are actually wired in (CON-08),
and today it hardcodes exactly one: `if jurisdiction == "AP"`. This
list mirrors that by hand rather than walking packs/jurisdictions/ and
guessing at metadata no module actually declares — there is no
per-module CODE/NAME convention to introspect (see the investigation
this was built from). Extend both together when a second jurisdiction
lands, the same way registry.py's own override function will need
extending.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends

from solarfit.auth_users import AuthenticatedUser, current_user
from solarfit.packs import config_pack
from solarfit.routers.common import CamelModel

router = APIRouter(prefix="/app", tags=["app-jurisdictions"])

# One entry per jurisdiction registry.py's _jurisdiction_overrides() special-cases.
_KNOWN_JURISDICTIONS = [
    {
        "code": "AP",
        "state": "Andhra Pradesh",
        "pack": "jurisdictions/in_ap",
        "rules": [
            {
                "name": "net_metering_cap",
                "kind": "regulatory",
                "description": (
                    "Stricter net-metering export ratio than the national rooftop_v1 default."
                ),
            }
        ],
    }
]


class JurisdictionRuleOut(CamelModel):
    name: str
    kind: str
    description: str


class JurisdictionConstraintPackOut(CamelModel):
    id: str
    jurisdiction: str
    state: str
    version: str
    updated_at: datetime
    rules: list[JurisdictionRuleOut]


def _pack_yaml_path(pack: str) -> Path:
    return config_pack._packs_dir() / f"{pack}.yaml"


def _updated_at(pack: str) -> datetime:
    """The pack yaml's own filesystem mtime — a real, if approximate,
    signal of when it last changed, rather than a fabricated timestamp
    (no CFG-02-style change-log exists for config packs today)."""
    try:
        mtime = _pack_yaml_path(pack).stat().st_mtime
        return datetime.fromtimestamp(mtime, tz=UTC)
    except OSError:
        return datetime.now(UTC)


@router.get("/jurisdictions", response_model=list[JurisdictionConstraintPackOut])
def list_jurisdictions(
    _user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> list[JurisdictionConstraintPackOut]:
    out = []
    for j in _KNOWN_JURISDICTIONS:
        out.append(
            JurisdictionConstraintPackOut(
                id=j["code"],
                jurisdiction=j["code"],
                state=j["state"],
                version=config_pack.pack_version(pack=j["pack"]),
                updated_at=_updated_at(j["pack"]),
                rules=[JurisdictionRuleOut(**r) for r in j["rules"]],
            )
        )
    return out
