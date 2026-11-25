"""Owner: keerthana (Vendor domain, customer-account admin, jurisdictions).

The time-bound lead engine's scheduler wiring — repositories/vendors.py::
sweep_vendor_job_sla() is the real logic; this is a thin Celery wrapper
around it, same "task is a thin wrapper around a plain, independently-
testable function" split routers/assessments.py::orchestrate_assessment()
+ workers/tasks_assessments.py::run_check_assessment() already
established. Scheduled via celery_app.py's beat_schedule; dispatch
manually for testing with:
    from solarfit.workers.tasks_vendors import sweep_vendor_sla
    sweep_vendor_sla.delay()
"""

import logging
from datetime import timedelta

from solarfit.db import session_scope
from solarfit.packs.config_pack import (
    get_vendor_lead_reassignment_extension_days,
    get_vendor_sla_at_risk_window_hours,
)
from solarfit.repositories import vendors as vendors_repo
from solarfit.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="solarfit.vendors.sweep_sla")
def sweep_vendor_sla() -> dict[str, int]:
    """Runs repositories/vendors.py::sweep_vendor_job_sla() against the
    real config-pack coefficients. Never raises past this point — one
    bad row inside the sweep is already isolated by the underlying
    function's own per-job loop; a failure at the session/config level
    here would just mean this run's sweep is skipped, picked up again
    at the next scheduled tick, same "a scheduled task missing one run
    is recoverable, a customer-facing request failing is not" tradeoff
    USN-06's purge job already accepts."""
    with session_scope() as session:
        result = vendors_repo.sweep_vendor_job_sla(
            session,
            at_risk_window=timedelta(hours=get_vendor_sla_at_risk_window_hours()),
            reassignment_extension=timedelta(days=get_vendor_lead_reassignment_extension_days()),
        )
        session.commit()
        logger.info(
            "Vendor SLA sweep: %d marked at-risk, %d marked overdue, %d leads reassigned",
            result["marked_at_risk"],
            result["marked_overdue"],
            result["reassigned"],
        )
        return result
