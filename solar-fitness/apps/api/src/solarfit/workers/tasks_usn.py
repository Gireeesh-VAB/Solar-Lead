"""Owner: Person 4 (Scoring, USN & Assessment API).

USN-06's purge job — deletes the object-storage blob for any
usn_ocr_uploads row past its retention deadline, then nulls the
remaining evidence in the database. Scheduled via celery_app.py's
beat_schedule; dispatch manually for testing with:
    from solarfit.workers.tasks_usn import purge_expired_uploads
    purge_expired_uploads.delay()
"""

from solarfit.db import get_session
from solarfit.providers.usn_ocr import delete_from_object_storage
from solarfit.repositories import usn_uploads as usn_uploads_repo
from solarfit.workers.celery_app import celery_app


@celery_app.task(name="solarfit.usn.purge_expired_uploads")
def purge_expired_uploads() -> int:
    """USN-06. Returns the count of rows purged."""
    with get_session() as session:
        expired = usn_uploads_repo.find_expired(session)
        for upload in expired:
            if upload.object_storage_key:
                delete_from_object_storage(upload.object_storage_key)
            usn_uploads_repo.finalize_purge(session, upload.id)
        session.commit()
        return len(expired)
