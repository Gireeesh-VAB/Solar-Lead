"""Tests for providers/usn_ocr.py + repositories/usn_uploads.py —
§9.15 USN Capture (USN-01..06).

DB-touching tests run against an in-memory SQLite database (via the
sqlite_engine fixture) rather than a live Postgres — usn_ocr_uploads has
no PostGIS columns, so this is a faithful substitute and doesn't depend
on docker-compose being up. OCR and object-storage calls are always
monkeypatched — no real GCP/S3 credentials or network access needed.
"""

import pytest
from sqlalchemy.orm import sessionmaker

from solarfit.providers import usn_ocr
from solarfit.repositories.usn_uploads import (
    UsnOcrUpload,
    finalize_purge,
    find_expired,
    save_upload,
)


@pytest.fixture
def usn_session_factory(sqlite_engine, monkeypatch):
    """Creates the usn_ocr_uploads table on the shared in-memory engine
    and points both providers.usn_ocr.session_scope and
    workers.tasks_usn.session_scope at it (each module imported its own
    `session_scope` name via `from solarfit.db import session_scope`, so
    both bindings need patching independently) — so extract_from_bill()
    and the purge task write to this SQLite DB instead of the real
    Postgres one."""
    from solarfit.workers import tasks_usn

    UsnOcrUpload.metadata.create_all(sqlite_engine, tables=[UsnOcrUpload.__table__])
    session_local = sessionmaker(bind=sqlite_engine)
    monkeypatch.setattr(usn_ocr, "session_scope", lambda: session_local())
    monkeypatch.setattr(tasks_usn, "session_scope", lambda: session_local())
    return session_local


@pytest.fixture
def no_op_storage(monkeypatch):
    """Prevents any real S3 call — captures (key, data) pairs passed to
    _upload_to_object_storage for assertions."""
    calls = []
    monkeypatch.setattr(
        usn_ocr, "_upload_to_object_storage", lambda key, data: calls.append((key, data))
    )
    return calls


# ---------------------------------------------------------------------------
# USN-06 — evidence encrypted at rest
# ---------------------------------------------------------------------------


def test_upload_to_object_storage_requests_server_side_encryption(monkeypatch):
    """Regression: USN-06 says evidence must be "encrypted at rest," but
    that was previously only asserted in a docstring — the put_object
    call itself never actually requested it."""
    calls = []

    class _FakeClient:
        def put_object(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(usn_ocr, "_object_storage_client", lambda: _FakeClient())

    usn_ocr._upload_to_object_storage("some/key.png", b"fake-bytes")

    assert len(calls) == 1
    assert calls[0]["ServerSideEncryption"] == "AES256"
    assert calls[0]["Key"] == "some/key.png"
    assert calls[0]["Body"] == b"fake-bytes"


# ---------------------------------------------------------------------------
# USN-01 — manual entry
# ---------------------------------------------------------------------------


def test_capture_manual_valid_format_accepted():
    result = usn_ocr.capture_manual("AP-1234567890")
    assert result.usn == "AP-1234567890"
    assert result.usn_source == "manual"


def test_capture_manual_invalid_format_rejected():
    with pytest.raises(ValueError, match="format"):
        usn_ocr.capture_manual("ab")  # too short


def test_capture_manual_normalizes_case_and_whitespace():
    result = usn_ocr.capture_manual("  ap1234567  ")
    assert result.usn == "AP1234567"


# ---------------------------------------------------------------------------
# USN-02/03 — OCR extraction
# ---------------------------------------------------------------------------


def test_extract_from_bill_finds_usn_via_usn_pattern(usn_session_factory, no_op_storage, monkeypatch):
    monkeypatch.setattr(usn_ocr, "_run_text_detection", lambda image: "Bill details\nUSN: AP123456789\n")

    preview = usn_ocr.extract_from_bill(b"fake-image-bytes", site_id="site-1")

    assert preview.usn == "AP123456789"
    assert preview.usn_source == "bill_ocr"
    assert preview.extraction_status == "extracted"
    assert preview.upload_id


def test_extract_from_bill_finds_usn_via_service_number_pattern(
    usn_session_factory, no_op_storage, monkeypatch
):
    monkeypatch.setattr(usn_ocr, "_run_text_detection", lambda image: "Service Number: TN-9988776655")

    preview = usn_ocr.extract_from_bill(b"img", site_id="site-1")

    assert preview.usn == "TN-9988776655"


def test_extract_from_payment_proof_finds_usn_via_consumer_number_pattern(
    usn_session_factory, no_op_storage, monkeypatch
):
    monkeypatch.setattr(usn_ocr, "_run_text_detection", lambda image: "Consumer No. KA5566778899")

    preview = usn_ocr.extract_from_payment_proof(b"img", site_id="site-1")

    assert preview.usn == "KA5566778899"
    assert preview.usn_source == "payment_proof_ocr"
    assert preview.extraction_status == "extracted"


def test_extract_no_match_returns_none_not_a_guess(usn_session_factory, no_op_storage, monkeypatch):
    monkeypatch.setattr(usn_ocr, "_run_text_detection", lambda image: "This bill has no identifiers on it.")

    preview = usn_ocr.extract_from_bill(b"img", site_id="site-1")

    assert preview.usn is None
    assert preview.extraction_status == "not_found"


def test_extract_ocr_failure_handled_gracefully(usn_session_factory, no_op_storage, monkeypatch):
    def _raise(image):
        raise RuntimeError("Vision API is down")

    monkeypatch.setattr(usn_ocr, "_run_text_detection", _raise)

    preview = usn_ocr.extract_from_bill(b"img", site_id="site-1")

    assert preview.usn is None
    assert preview.extraction_status == "failed"


def test_extract_uploads_image_to_object_storage(usn_session_factory, no_op_storage, monkeypatch):
    monkeypatch.setattr(usn_ocr, "_run_text_detection", lambda image: "USN: AP123456789")

    usn_ocr.extract_from_bill(b"raw-bytes", site_id="site-42")

    assert len(no_op_storage) == 1
    key, data = no_op_storage[0]
    assert key.startswith("usn-ocr/site-42/bill/")
    assert data == b"raw-bytes"


def test_extract_persists_evidence_with_retention_window(usn_session_factory, no_op_storage, monkeypatch):
    monkeypatch.setattr(usn_ocr, "_run_text_detection", lambda image: "USN: AP123456789")

    preview = usn_ocr.extract_from_bill(b"img", site_id="site-1")

    with usn_session_factory() as session:
        row = session.get(UsnOcrUpload, preview.upload_id)
        assert row is not None
        assert row.never_use_for_training is True
        assert row.purge_after > row.uploaded_at
        assert (row.purge_after - row.uploaded_at).days == 90  # rooftop_v1.yaml placeholder


# ---------------------------------------------------------------------------
# USN-04 — confirm-before-store, converging all paths
# ---------------------------------------------------------------------------


def test_confirm_and_finalize_returns_correct_usn_capture(usn_session_factory, no_op_storage, monkeypatch):
    monkeypatch.setattr(usn_ocr, "_run_text_detection", lambda image: "USN: AP123456789")
    preview = usn_ocr.extract_from_bill(b"img", site_id="site-1")

    capture = usn_ocr.confirm_and_finalize(preview.upload_id, "AP123456789", confirmed_by="operator-1")

    assert capture.usn == "AP123456789"
    assert capture.usn_source == "bill_ocr"


def test_confirm_and_finalize_uses_corrected_value(usn_session_factory, no_op_storage, monkeypatch):
    monkeypatch.setattr(usn_ocr, "_run_text_detection", lambda image: "USN: AP123456789")
    preview = usn_ocr.extract_from_bill(b"img", site_id="site-1")

    # Operator corrects a misread character before confirming.
    capture = usn_ocr.confirm_and_finalize(preview.upload_id, "AP123456780", confirmed_by="operator-1")

    assert capture.usn == "AP123456780"


def test_confirm_and_finalize_marks_upload_confirmed(usn_session_factory, no_op_storage, monkeypatch):
    monkeypatch.setattr(usn_ocr, "_run_text_detection", lambda image: "USN: AP123456789")
    preview = usn_ocr.extract_from_bill(b"img", site_id="site-1")

    usn_ocr.confirm_and_finalize(preview.upload_id, "AP123456789", confirmed_by="operator-1")

    with usn_session_factory() as session:
        row = session.get(UsnOcrUpload, preview.upload_id)
        assert row.extraction_status == "confirmed"


def test_confirm_and_finalize_invalid_format_raises(usn_session_factory, no_op_storage, monkeypatch):
    monkeypatch.setattr(usn_ocr, "_run_text_detection", lambda image: "USN: AP123456789")
    preview = usn_ocr.extract_from_bill(b"img", site_id="site-1")

    with pytest.raises(ValueError, match="format"):
        usn_ocr.confirm_and_finalize(preview.upload_id, "x", confirmed_by="operator-1")


def test_confirm_and_finalize_unknown_upload_id_raises(usn_session_factory):
    with pytest.raises(ValueError, match="No usn_ocr_uploads row"):
        usn_ocr.confirm_and_finalize("does-not-exist", "AP123456789", confirmed_by="operator-1")


def test_all_three_paths_converge_on_same_shape(usn_session_factory, no_op_storage, monkeypatch):
    """USN-04: manual, bill OCR, and payment-proof OCR all produce the
    same UsnCapture shape (usn + usn_source), never separate fields."""
    manual = usn_ocr.capture_manual("AP123456789")

    monkeypatch.setattr(usn_ocr, "_run_text_detection", lambda image: "USN: AP123456789")
    bill_preview = usn_ocr.extract_from_bill(b"img", site_id="site-1")
    bill = usn_ocr.confirm_and_finalize(bill_preview.upload_id, "AP123456789", confirmed_by="op")

    proof_preview = usn_ocr.extract_from_payment_proof(b"img", site_id="site-1")
    proof = usn_ocr.confirm_and_finalize(proof_preview.upload_id, "AP123456789", confirmed_by="op")

    for capture, expected_source in [(manual, "manual"), (bill, "bill_ocr"), (proof, "payment_proof_ocr")]:
        assert capture.usn == "AP123456789"
        assert capture.usn_source == expected_source


# ---------------------------------------------------------------------------
# USN-06 — evidence retention / purge (repositories/usn_uploads.py directly)
# ---------------------------------------------------------------------------


def test_find_expired_only_returns_rows_past_purge_after(sqlite_engine):
    from datetime import UTC, datetime, timedelta

    UsnOcrUpload.metadata.create_all(sqlite_engine, tables=[UsnOcrUpload.__table__])
    session_local = sessionmaker(bind=sqlite_engine)

    with session_local() as session:
        now = datetime.now(UTC)
        expired = UsnOcrUpload(
            id="expired-1",
            site_id="site-1",
            document_type="bill",
            object_storage_key="k1",
            uploaded_at=now - timedelta(days=100),
            purge_after=now - timedelta(days=1),
            extraction_status="extracted",
            ocr_raw_text="some raw text",
            never_use_for_training=True,
        )
        not_expired = UsnOcrUpload(
            id="fresh-1",
            site_id="site-1",
            document_type="bill",
            object_storage_key="k2",
            uploaded_at=now,
            purge_after=now + timedelta(days=89),
            extraction_status="extracted",
            ocr_raw_text="some other raw text",
            never_use_for_training=True,
        )
        session.add_all([expired, not_expired])
        session.commit()

        results = find_expired(session)
        assert [r.id for r in results] == ["expired-1"]


def test_finalize_purge_nulls_evidence(sqlite_engine):
    UsnOcrUpload.metadata.create_all(sqlite_engine, tables=[UsnOcrUpload.__table__])
    session_local = sessionmaker(bind=sqlite_engine)

    with session_local() as session:
        row = save_upload(
            session,
            site_id="site-1",
            document_type="bill",
            object_storage_key="k1",
            extraction_status="extracted",
            ocr_raw_text="sensitive text",
        )
        session.commit()
        upload_id = row.id

        finalize_purge(session, upload_id)
        session.commit()

        purged = session.get(UsnOcrUpload, upload_id)
        assert purged.ocr_raw_text is None
        assert purged.object_storage_key is None


def test_purge_task_deletes_storage_and_finalizes(usn_session_factory, no_op_storage, monkeypatch):
    from datetime import UTC, datetime, timedelta

    from solarfit.workers import tasks_usn
    from solarfit.workers.tasks_usn import purge_expired_uploads

    deleted_keys = []
    # tasks_usn.py imported delete_from_object_storage directly (`from
    # ...usn_ocr import delete_from_object_storage`), which binds its
    # own name in tasks_usn's namespace — patching usn_ocr's copy alone
    # wouldn't intercept the call made from inside tasks_usn.
    monkeypatch.setattr(tasks_usn, "delete_from_object_storage", lambda key: deleted_keys.append(key))

    with usn_session_factory() as session:
        now = datetime.now(UTC)
        row = save_upload(
            session,
            site_id="site-1",
            document_type="bill",
            object_storage_key="stale-key",
            extraction_status="extracted",
            ocr_raw_text="stale text",
        )
        row.purge_after = now - timedelta(days=1)
        session.commit()
        upload_id = row.id

    count = purge_expired_uploads.run()

    assert count == 1
    assert deleted_keys == ["stale-key"]

    with usn_session_factory() as session:
        purged = session.get(UsnOcrUpload, upload_id)
        assert purged.ocr_raw_text is None


# ---------------------------------------------------------------------------
# USN-06 — structural exclusion from ML training
# ---------------------------------------------------------------------------


def test_ml_score_module_never_imports_usn_modules():
    """USN-06's 'hard-excluded from ML/vision training' clause, checked
    structurally: engine/ml_score.py must have no import path to either
    USN module. (A raw-text 'usn' substring search would false-positive
    on this file's own module docstring header, which names every
    Person-4 file it's the sibling of — so this checks actual imports.)"""
    import ast
    import inspect

    from solarfit.engine import ml_score

    tree = ast.parse(inspect.getsource(ml_score))
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    forbidden = {"solarfit.repositories.usn_uploads", "solarfit.providers.usn_ocr"}
    hit = imported_modules & forbidden
    assert not hit, f"engine/ml_score.py must never import USN-related modules — found: {hit}"
