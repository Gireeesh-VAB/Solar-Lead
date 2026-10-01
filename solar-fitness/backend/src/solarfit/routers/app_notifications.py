"""Owner: karthik (App Platform & Foundation).

The read side of in-app notifications — repositories/notifications.py's
create_notification() is called from each triggering site (assessment
approval, SLA sweep, job submission, ...); this router is just
"show me my own notifications" + "mark one read", scoped to the caller
via current_user() the same way every other /app/* route is.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from solarfit.auth_users import AuthenticatedUser, current_user
from solarfit.db import get_session
from solarfit.repositories import notifications as repo
from solarfit.routers.common import CamelModel

router = APIRouter(prefix="/app/notifications", tags=["app-notifications"])


class NotificationOut(CamelModel):
    id: str
    kind: str
    title: str
    body: str | None = None
    read_at: datetime | None = None
    created_at: datetime


def _out(row: repo.NotificationRow) -> NotificationOut:
    return NotificationOut(
        id=str(row.id),
        kind=row.kind,
        title=row.title,
        body=row.body,
        read_at=row.read_at,
        created_at=row.created_at,
    )


@router.get("", response_model=list[NotificationOut])
def list_my_notifications(
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> list[NotificationOut]:
    return [_out(r) for r in repo.list_for_user(session, user.id)]


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_notification_read(
    notification_id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[AuthenticatedUser, Depends(current_user)],
) -> NotificationOut:
    row = repo.mark_read(session, notification_id, user.id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "notification not found")
    session.commit()
    return _out(row)
