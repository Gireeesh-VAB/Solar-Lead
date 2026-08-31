"""Owner: keerthana (Vendor domain, customer-account admin, jurisdictions).

The admin "Tenants" screen. Per the roadmap's ground rules there is no
tenant table — a customer account is one row in karthik's `users`
table, and a "tenant" is every user sharing one owner_org string. `id`
in every route below IS the owner_org string; there is no separate
numeric/UUID tenant id to look one up by.

tier/status apply to every user in the org together (suspend/reinstate/
update-tier write all of them), so nobody in an org is left on a stale
value after an admin changes it — see repositories/customer_accounts.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from solarfit.auth_users import AuthenticatedUser, require_role
from solarfit.db import get_session
from solarfit.repositories import customer_accounts as repo
from solarfit.routers.common import CamelModel

router = APIRouter(prefix="/app/admin/customers", tags=["app-admin-customers"])


# --------------------------------------------------------------------- #
# schemas
# --------------------------------------------------------------------- #


class TenantUserOut(CamelModel):
    name: str
    role: str
    email: str


class TenantOut(CamelModel):
    id: str
    name: str
    tier: str | None
    status: str | None
    seat_count: int
    sites_assessed_this_month: int
    api_calls_this_month: int
    created_at: datetime
    billing_contact_email: str | None
    users: list[TenantUserOut]


class UpdateTierRequest(CamelModel):
    tier: str


def _tenant_out(data: dict) -> TenantOut:
    return TenantOut(
        id=data["id"],
        name=data["name"],
        tier=data["tier"],
        status=data["status"],
        seat_count=data["seat_count"],
        sites_assessed_this_month=data["sites_assessed_this_month"],
        api_calls_this_month=data["api_calls_this_month"],
        created_at=data["created_at"],
        billing_contact_email=data["billing_contact_email"],
        users=[TenantUserOut(**u) for u in data["users"]],
    )


def _tenant_or_404(data: dict | None) -> TenantOut:
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "customer account not found")
    return _tenant_out(data)


# --------------------------------------------------------------------- #
# endpoints
# --------------------------------------------------------------------- #


@router.get("", response_model=list[TenantOut])
def list_customers(
    session: Annotated[Session, Depends(get_session)],
    _user: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
    q: Annotated[str | None, Query()] = None,
    tier: Annotated[str | None, Query()] = None,
    account_status: Annotated[str | None, Query(alias="status")] = None,
) -> list[TenantOut]:
    tenants = repo.list_tenants(session, q=q, tier=tier, status=account_status)
    return [_tenant_out(t) for t in tenants]


@router.get("/{customer_id}", response_model=TenantOut)
def get_customer(
    customer_id: str,
    session: Annotated[Session, Depends(get_session)],
    _user: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> TenantOut:
    return _tenant_or_404(repo.get_tenant(session, customer_id))


@router.patch("/{customer_id}/tier", response_model=TenantOut)
def update_customer_tier(
    customer_id: str,
    payload: UpdateTierRequest,
    session: Annotated[Session, Depends(get_session)],
    _user: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> TenantOut:
    return _tenant_or_404(repo.update_tenant_tier(session, customer_id, payload.tier))


@router.post("/{customer_id}/suspend", response_model=TenantOut)
def suspend_customer(
    customer_id: str,
    session: Annotated[Session, Depends(get_session)],
    _user: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> TenantOut:
    return _tenant_or_404(repo.suspend_tenant(session, customer_id))


@router.post("/{customer_id}/reinstate", response_model=TenantOut)
def reinstate_customer(
    customer_id: str,
    session: Annotated[Session, Depends(get_session)],
    _user: Annotated[AuthenticatedUser, Depends(require_role("admin"))],
) -> TenantOut:
    return _tenant_or_404(repo.reinstate_tenant(session, customer_id))
