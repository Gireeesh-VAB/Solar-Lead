"""Owner: keerthana (Vendor domain, customer-account admin, jurisdictions).

GET /app/jurisdictions — a small admin reference screen listing which
state-specific constraint-pack overrides exist. packs/registry.py is
the one place jurisdiction overrides are actually wired in (CON-08),
and today it hardcodes exactly one: `if jurisdiction == "AP"`.

This walks packages/config-packs/jurisdictions/*.yaml directly instead
of a hardcoded Python list — each pack file carries its own `meta:`
block (code/state/rules) for display purposes, so a new jurisdiction
pack shows up here automatically once the yaml exists, no code change
needed (registry.py's own override function still needs extending
separately — that's the engine wiring, this is just the read side).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import yaml
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from solarfit.auth_users import AuthenticatedUser, current_user, require_role
from solarfit.db import get_session
from solarfit.packs import config_pack
from solarfit.repositories import audit as audit_repo
from solarfit.routers.common import CamelModel

router = APIRouter(prefix="/app", tags=["app-jurisdictions"])


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


def _jurisdictions_dir() -> Path:
    return config_pack._packs_dir() / "jurisdictions"


def _updated_at(path: Path) -> datetime:
    """The pack yaml's own filesystem mtime — a real, if approximate,
    signal of when it last changed, rather than a fabricated timestamp
    (no CFG-02-style change-log exists for config packs today)."""
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    except OSError:
        return datetime.now(UTC)


def _load_pack_out(path: Path) -> JurisdictionConstraintPackOut | None:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    meta = data.get("meta")
    if not meta:
        # A pack yaml with no display metadata — real for the engine,
        # just not shown on this admin screen yet.
        return None
    pack_name = f"jurisdictions/{path.stem}"
    return JurisdictionConstraintPackOut(
        id=meta["code"],
        jurisdiction=meta["code"],
        state=meta["state"],
        version=config_pack.pack_version(pack=pack_name),
        updated_at=_updated_at(path),
        rules=[JurisdictionRuleOut(**r) for r in meta.get("rules", [])],
    )


@router.get("/jurisdictions", response_model=list[JurisdictionConstraintPackOut])
def list_jurisdictions(
    _user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> list[JurisdictionConstraintPackOut]:
    directory = _jurisdictions_dir()
    if not directory.is_dir():
        return []
    out = []
    for path in sorted(directory.glob("*.yaml")):
        pack_out = _load_pack_out(path)
        if pack_out is not None:
            out.append(pack_out)
    return out


@router.post("/admin/jurisdictions/{code}/publish", response_model=JurisdictionConstraintPackOut)
def publish_jurisdiction(
    code: str,
    session: Annotated[Session, Depends(get_session)],
    admin: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> JurisdictionConstraintPackOut:
    """Forces the fitness engine to pick up the pack's current on-disk
    state: config_pack.load_pack() is @lru_cache'd, so a yaml edit made
    outside the running process wouldn't otherwise be seen until the
    process restarts. This clears that cache — a real, if narrow, effect
    — and audit-logs the action; it does not modify the yaml itself
    (there is no in-app pack editor)."""
    pack_out = None
    for path in _jurisdictions_dir().glob("*.yaml"):
        candidate = _load_pack_out(path)
        if candidate is not None and candidate.id == code.upper():
            pack_out = candidate
            break
    if pack_out is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown jurisdiction")

    config_pack.load_pack.cache_clear()

    audit_repo.write_audit_log(
        session,
        actor=admin.email,
        action="jurisdiction.published",
        target=code.upper(),
        details=f"{admin.email} published jurisdiction pack {code.upper()}",
    )

    return pack_out
