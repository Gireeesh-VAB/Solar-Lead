"""Owner: Person 1 (Site & Geometry).

API-09 — assessment-completion webhook emitter.

Lives in workers/ rather than in a request handler because an outbound
POST to a customer's endpoint is exactly the kind of latency the caller
must not wait on: a tenant whose receiver is down would otherwise slow
or fail Person 4's assessment response. Registered here, dispatched from
routers/assessments.py (Person 4) with:

    from solarfit.workers.webhooks import emit_assessment_completed
    emit_assessment_completed.delay(tenant_webhook_url, payload, secret)

Delivery discipline
-------------------
* Retries with exponential backoff on network errors and 5xx.
* A 4xx is NOT retried — the receiver rejected the payload, and sending
  it again unchanged will be rejected again.
* Payloads are signed with an HMAC-SHA256 header so the receiver can
  verify the call actually came from us. The secret is per-tenant and
  never travels in the body.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import httpx
from celery.utils.log import get_task_logger

from solarfit.workers.celery_app import celery_app

logger = get_task_logger(__name__)

SIGNATURE_HEADER = "X-Solarfit-Signature"
EVENT_HEADER = "X-Solarfit-Event"
TIMEOUT_SECONDS = 10.0

__all__ = ["build_payload", "emit_assessment_completed", "sign_payload"]


def sign_payload(body: bytes, secret: str) -> str:
    """HMAC-SHA256 of the exact bytes sent, hex-encoded.

    Signed over the serialised body rather than a dict, so the receiver
    verifies precisely what arrived — re-serialising before hashing is
    how signature checks quietly break on key ordering.
    """
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def build_payload(
    *, event: str, site_id: str, assessment_id: str | None = None, data: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "event": event,
        "site_id": site_id,
        "assessment_id": assessment_id,
        "data": data or {},
    }


@celery_app.task(
    name="solarfit.webhooks.emit_assessment_completed",
    bind=True,
    max_retries=5,
    autoretry_for=(httpx.TransportError,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def emit_assessment_completed(
    self, url: str, payload: dict[str, Any], secret: str | None = None
) -> dict[str, Any]:
    """API-09. POST a completion event to a tenant's webhook URL.

    Returns a small delivery record rather than raising on a 4xx, so a
    permanently-bad receiver shows up as a failed delivery in the logs
    instead of an endlessly retrying task.
    """
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        EVENT_HEADER: str(payload.get("event", "assessment.completed")),
    }
    if secret:
        headers[SIGNATURE_HEADER] = sign_payload(body, secret)

    try:
        response = httpx.post(url, content=body, headers=headers, timeout=TIMEOUT_SECONDS)
    except httpx.TransportError:
        logger.warning("webhook transport error for %s, will retry", url)
        raise

    if response.status_code >= 500:
        logger.warning("webhook %s returned %s, will retry", url, response.status_code)
        raise self.retry(countdown=min(600, 2**self.request.retries))

    delivered = 200 <= response.status_code < 300
    if not delivered:
        # 4xx: the receiver understood and refused. Retrying the same
        # payload cannot change that, so record it and stop.
        logger.error("webhook %s rejected with %s (not retried)", url, response.status_code)

    return {"url": url, "status_code": response.status_code, "delivered": delivered}
