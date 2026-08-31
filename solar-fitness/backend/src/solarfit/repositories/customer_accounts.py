"""Owner: keerthana (Vendor domain, customer-account admin, jurisdictions).

The admin "Tenants" screen — per the roadmap's ground rules, there is no
tenant table: a customer account is one row in karthik's `users` table,
and a "tenant" is just every user sharing one owner_org string. This
module reads/writes UserRow directly (imported from repositories/users,
not duplicated) rather than adding tenant-shaped functions to karthik's
file — his file stays untouched, this one owns the aggregation.

The "primary" account for a tenant — the one whose tier/status/
billing_contact_email represents the org as a whole — is the
earliest-created user in that owner_org (list_by_owner_org already
orders by created_at). suspend/reinstate/update-tier apply to every
user sharing the org, so nobody in it is left on a stale tier after an
admin changes it.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from solarfit.repositories.users import UserRow, list_by_owner_org

__all__ = ["get_tenant", "list_tenants", "reinstate_tenant", "suspend_tenant", "update_tenant_tier"]


def _tenant_from_users(owner_org: str, users: list[UserRow]) -> dict[str, Any]:
    # list_by_owner_org orders by created_at, but Postgres's now() resolves
    # to one fixed value for the whole transaction — two signups created in
    # the same transaction (e.g. a bulk-seed script, or this module's own
    # tests) tie on created_at, making "first in the list" ambiguous. id is
    # unique and stable, so it breaks the tie deterministically without
    # depending on statement-level ordering karthik's server_default=now()
    # doesn't actually provide.
    primary = min(users, key=lambda u: (u.created_at, str(u.id)))
    return {
        "id": owner_org,
        "name": owner_org,
        "tier": primary.tier,
        "status": primary.status,
        "seat_count": len(users),
        # No assessments table exists yet in this pass (that's omkar's
        # separate, not-yet-landed workstream) — an honest 0, not a
        # fabricated count, same discipline as api_calls_this_month below.
        "sites_assessed_this_month": 0,
        "api_calls_this_month": 0,
        "created_at": primary.created_at,
        "billing_contact_email": primary.billing_contact_email,
        "users": [{"name": u.name, "role": u.role, "email": u.email} for u in users],
    }


def list_tenants(
    session: Session, *, q: str | None = None, tier: str | None = None, status: str | None = None
) -> list[dict[str, Any]]:
    """One row per distinct owner_org among customer users, matching the
    frontend's flat Tenant[] shape. Filtered in Python after grouping —
    the customer base is small enough (per-deployment tenant list, not a
    consumer-scale table) that a GROUP BY round trip isn't worth the
    added query complexity here."""
    stmt = (
        select(UserRow)
        .where(UserRow.role == "customer", UserRow.owner_org.is_not(None))
        .order_by(UserRow.owner_org, UserRow.created_at)
    )
    by_org: dict[str, list[UserRow]] = {}
    for row in session.scalars(stmt):
        by_org.setdefault(row.owner_org, []).append(row)

    tenants = [_tenant_from_users(org, users) for org, users in by_org.items()]

    if q:
        needle = q.lower()
        tenants = [t for t in tenants if needle in t["name"].lower()]
    if tier:
        tenants = [t for t in tenants if t["tier"] == tier]
    if status:
        tenants = [t for t in tenants if t["status"] == status]
    return tenants


def get_tenant(session: Session, owner_org: str) -> dict[str, Any] | None:
    users = list_by_owner_org(session, owner_org)
    if not users:
        return None
    return _tenant_from_users(owner_org, users)


def update_tenant_tier(session: Session, owner_org: str, tier: str) -> dict[str, Any] | None:
    users = list_by_owner_org(session, owner_org)
    if not users:
        return None
    for user in users:
        user.tier = tier
    session.flush()
    return _tenant_from_users(owner_org, users)


def suspend_tenant(session: Session, owner_org: str) -> dict[str, Any] | None:
    return _set_status(session, owner_org, "suspended")


def reinstate_tenant(session: Session, owner_org: str) -> dict[str, Any] | None:
    return _set_status(session, owner_org, "active")


def _set_status(session: Session, owner_org: str, status: str) -> dict[str, Any] | None:
    users = list_by_owner_org(session, owner_org)
    if not users:
        return None
    for user in users:
        user.status = status
    session.flush()
    return _tenant_from_users(owner_org, users)
