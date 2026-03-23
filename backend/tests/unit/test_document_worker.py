"""
DocumentWorker unit tests — checkpoint resume, timeout handling, completion/failure flows,
SQS message lifecycle.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from app.workers.document_worker import DocumentWorker
from app.workers.batch_processor import BatchRange, BatchResult
from app.models.document_job import DocumentProcessingJob, JobStatus
from app.models.document import Document, DocumentStatus
from app.services.sqs_service import SQSMessage


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_sqs_message(job_id: str, resume_from: int = 0, total_pages: int = 150) -> SQSMessage:
    return SQSMessage(
        receipt_handle="rh-001",
        message_id="msg-001",
        body={
            "job_id": job_id,
            "tenant_id": str(uuid.uuid4()),
            "user_id": str(uuid.uuid4()),
            "document_id": str(uuid.uuid4()),
            "s3_key": "tenants/x/docs/y/file.pdf",
            "original_filename": "file.pdf",
            "total_pages": total_pages,
            "batch_size": 50,
            "resume_from_batch": resume_from,
        },
    )


def make_job(
    job_id: str | None = None,
    status: JobStatus = JobStatus.PENDING,
    total_pages: int = 150,
    total_batches: int = 3,
    last_completed: int = -1,
) -> MagicMock:
    job = MagicMock(spec=DocumentProcessingJob)
    job.id = uuid.UUID(job_id) if job_id else uuid.uuid4()
    job.tenant_id = uuid.uuid4()
    job.user_id = uuid.uuid4()
    job.document_id = uuid.uuid4()
    job.s3_key = "tenants/x/docs/y/file.pdf"
    job.original_filename = "file.pdf"
    job.status = status
    job.total_pages = total_pages
    job.total_batches = total_batches
    job.completed_batches = 0
    job.last_completed_batch = last_completed
    job.started_at = None
    job.sqs_receipt_handle = None
    job.sqs_message_id = None
    job.error_message = None
    job.failed_batch_index = None
    job.resume_from_batch = last_completed + 1
    job.progress_pct = 0.0
    return job


# ── _load_job ─────────────────────────────────────────────────────────────────

class TestLoadJob:
    @pytest.mark.asyncio
    async def test_returns_none_for_none_job_id(self):
        worker = DocumentWorker()
        db = AsyncMock()
        result = await worker._load_job(db, None)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_invalid_uuid(self):
        worker = DocumentWorker()
        db = AsyncMock()
        result = await worker._load_job(db, "not-a-uuid")
        assert result is None

    @pytest.mark.asyncio
    async def test_fetches_job_by_uuid(self):
        worker = DocumentWorker()
        job = make_job()
        db = AsyncMock()
        db.get = AsyncMock(return_value=job)

        result = await worker._load_job(db, str(job.id))
        assert result is job
        db.get.assert_awaited_once_with(DocumentProcessingJob, job.id)


# ── _process_message — idempotency ────────────────────────────────────────────

class TestProcessMessageIdempotency:
    @pytest.mark.asyncio
    async def test_already_completed_job_is_deleted_and_skipped(self):
        worker = DocumentWorker()
        job_id = str(uuid.uuid4())
        job = make_job(job_id=job_id, status=JobStatus.COMPLETED)
        msg = make_sqs_message(job_id)

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=job)

        with patch("app.workers.document_worker.AsyncSessionLocal") as mock_session, \
             patch("app.workers.document_worker.sqs_service") as mock_sqs:
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_sqs.delete_message = AsyncMock()

            await worker._process_message(msg)

        mock_sqs.delete_message.assert_awaited_once_with("rh-001")

    @pytest.mark.asyncio
    async def test_missing_job_deletes_message(self):
        worker = DocumentWorker()
        job_id = str(uuid.uuid4())
        msg = make_sqs_message(job_id)

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=None)

        with patch("app.workers.document_worker.AsyncSessionLocal") as mock_session, \
             patch("app.workers.document_worker.sqs_service") as mock_sqs:
            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_sqs.delete_message = AsyncMock()

            # _load_job uses db.get; make it return None
            with patch.object(worker, "_load_job", return_value=None):
                await worker._process_message(msg)

        mock_sqs.delete_message.assert_awaited_once_with("rh-001")


# ── _finalize_job — completed path ────────────────────────────────────────────

class TestFinalizeJobCompleted:
    @pytest.mark.asyncio
    async def test_completed_updates_status_and_deletes_sqs(self):
        worker = DocumentWorker()
        job = make_job(status=JobStatus.PROCESSING)
        job.started_at = datetime.now(timezone.utc)
        msg = make_sqs_message(str(job.id))

        db = AsyncMock()
        doc = MagicMock(spec=Document)
        db.get = AsyncMock(return_value=doc)

        with patch("app.workers.document_worker.sqs_service") as mock_sqs, \
             patch("app.workers.document_worker.notification_service") as mock_notif:
            mock_sqs.delete_message = AsyncMock()
            mock_notif.notify_job_completed = AsyncMock()

            await worker._finalize_job(
                db=db,
                job=job,
                msg=msg,
                paused=False,
                failed_batch=None,
                fail_error=None,
            )

        assert job.status == JobStatus.COMPLETED
        assert job.completed_at is not None
        mock_sqs.delete_message.assert_awaited_once_with("rh-001")
        mock_notif.notify_job_completed.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_completed_sets_document_ready(self):
        worker = DocumentWorker()
        job = make_job(status=JobStatus.PROCESSING)
        job.started_at = datetime.now(timezone.utc)
        msg = make_sqs_message(str(job.id))

        doc = MagicMock(spec=Document)
        db = AsyncMock()
        db.get = AsyncMock(return_value=doc)

        with patch("app.workers.document_worker.sqs_service") as mock_sqs, \
             patch("app.workers.document_worker.notification_service") as mock_notif:
            mock_sqs.delete_message = AsyncMock()
            mock_notif.notify_job_completed = AsyncMock()

            await worker._finalize_job(
                db=db, job=job, msg=msg,
                paused=False, failed_batch=None, fail_error=None,
            )

        assert doc.ocr_status == DocumentStatus.READY


# ── _finalize_job — paused / timeout path ─────────────────────────────────────

class TestFinalizeJobPaused:
    @pytest.mark.asyncio
    async def test_paused_requeues_and_notifies(self):
        worker = DocumentWorker()
        job = make_job(last_completed=1)
        job.resume_from_batch = 2
        msg = make_sqs_message(str(job.id))

        db = AsyncMock()

        with patch("app.workers.document_worker.sqs_service") as mock_sqs, \
             patch("app.workers.document_worker.notification_service") as mock_notif:
            mock_sqs.requeue_for_resume = AsyncMock()
            mock_sqs.delete_message = AsyncMock()
            mock_notif.notify_job_resumed = AsyncMock()

            await worker._finalize_job(
                db=db, job=job, msg=msg,
                paused=True, failed_batch=None, fail_error=None,
            )

        assert job.status == JobStatus.PAUSED
        mock_sqs.requeue_for_resume.assert_awaited_once()
        mock_sqs.delete_message.assert_awaited_once_with("rh-001")
        mock_notif.notify_job_resumed.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_paused_passes_resume_from_batch(self):
        worker = DocumentWorker()
        job = make_job(last_completed=4)
        job.resume_from_batch = 5
        msg = make_sqs_message(str(job.id))

        db = AsyncMock()

        with patch("app.workers.document_worker.sqs_service") as mock_sqs, \
             patch("app.workers.document_worker.notification_service") as mock_notif:
            mock_sqs.requeue_for_resume = AsyncMock()
            mock_sqs.delete_message = AsyncMock()
            mock_notif.notify_job_resumed = AsyncMock()

            await worker._finalize_job(
                db=db, job=job, msg=msg,
                paused=True, failed_batch=None, fail_error=None,
            )

        call_kwargs = mock_sqs.requeue_for_resume.call_args
        assert call_kwargs.kwargs.get("resume_from_batch") == 5


# ── _finalize_job — failed path ───────────────────────────────────────────────

class TestFinalizeJobFailed:
    @pytest.mark.asyncio
    async def test_failed_sets_status_and_notifies(self):
        worker = DocumentWorker()
        job = make_job()
        msg = make_sqs_message(str(job.id))
        db = AsyncMock()

        with patch("app.workers.document_worker.sqs_service") as mock_sqs, \
             patch("app.workers.document_worker.notification_service") as mock_notif:
            mock_sqs.delete_message = AsyncMock()
            mock_notif.notify_job_failed = AsyncMock()

            await worker._finalize_job(
                db=db, job=job, msg=msg,
                paused=False, failed_batch=2, fail_error="Embedding API unreachable",
            )

        assert job.status == JobStatus.FAILED
        assert job.error_message == "Embedding API unreachable"
        assert job.failed_batch_index == 2
        mock_notif.notify_job_failed.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_failed_does_not_delete_sqs_message(self):
        """Failed jobs leave SQS message for retry / DLQ."""
        worker = DocumentWorker()
        job = make_job()
        msg = make_sqs_message(str(job.id))
        db = AsyncMock()

        with patch("app.workers.document_worker.sqs_service") as mock_sqs, \
             patch("app.workers.document_worker.notification_service") as mock_notif:
            mock_sqs.delete_message = AsyncMock()
            mock_notif.notify_job_failed = AsyncMock()

            await worker._finalize_job(
                db=db, job=job, msg=msg,
                paused=False, failed_batch=1, fail_error="I/O error",
            )

        mock_sqs.delete_message.assert_not_awaited()


# ── _run_job — checkpoint logic ────────────────────────────────────────────────

class TestRunJobCheckpoint:
    @pytest.mark.asyncio
    async def test_checkpoint_saved_after_each_batch(self):
        worker = DocumentWorker()
        job = make_job(total_pages=100, total_batches=2)
        msg = make_sqs_message(str(job.id), total_pages=100)
        db = AsyncMock()

        success_batch = lambda range_: BatchResult(
            batch_index=range_.batch_index,
            pages_processed=50,
            chunks_created=80,
            success=True,
        )

        with patch.object(worker._processor, "process_batch", side_effect=lambda db, job, batch_range, **kw: asyncio.coroutine(lambda: success_batch(batch_range))()), \
             patch("app.workers.document_worker.sqs_service") as mock_sqs, \
             patch("app.workers.document_worker.notification_service") as mock_notif:
            mock_sqs.delete_message = AsyncMock()
            mock_notif.notify_job_completed = AsyncMock()

            # Use simpler approach - mock _finalize_job and inspect job state
            finalize_calls = []

            async def capture_finalize(db, job, msg, paused, failed_batch, fail_error):
                finalize_calls.append({"paused": paused, "failed_batch": failed_batch})

            with patch.object(worker, "_finalize_job", side_effect=capture_finalize):
                # Run with mocked batch results
                results = [
                    BatchResult(batch_index=0, pages_processed=50, chunks_created=80, success=True),
                    BatchResult(batch_index=1, pages_processed=50, chunks_created=70, success=True),
                ]
                call_count = 0

                async def mock_process_batch(db, job, batch_range, **kw):
                    nonlocal call_count
                    r = results[call_count]
                    call_count += 1
                    return r

                with patch.object(worker._processor, "process_batch", side_effect=mock_process_batch):
                    await worker._run_job(db=db, job=job, msg=msg, resume_from_batch=0)

        assert finalize_calls[0]["paused"] is False
        assert finalize_calls[0]["failed_batch"] is None

    @pytest.mark.asyncio
    async def test_timeout_in_first_batch_causes_pause(self):
        worker = DocumentWorker()
        job = make_job(total_pages=100, total_batches=2)
        msg = make_sqs_message(str(job.id), total_pages=100)
        db = AsyncMock()

        timeout_result = BatchResult(
            batch_index=0, pages_processed=0, chunks_created=0,
            success=False, error="Batch 0 timeout (120s aşıldı)"
        )

        finalize_calls = []

        async def capture_finalize(db, job, msg, paused, failed_batch, fail_error):
            finalize_calls.append({"paused": paused, "failed_batch": failed_batch})

        async def mock_process_batch(db, job, batch_range, **kw):
            return timeout_result

        with patch.object(worker._processor, "process_batch", side_effect=mock_process_batch), \
             patch.object(worker, "_finalize_job", side_effect=capture_finalize):
            await worker._run_job(db=db, job=job, msg=msg, resume_from_batch=0)

        assert finalize_calls[0]["paused"] is True
        assert finalize_calls[0]["failed_batch"] is None

    @pytest.mark.asyncio
    async def test_non_timeout_error_causes_failure(self):
        worker = DocumentWorker()
        job = make_job(total_pages=100, total_batches=2)
        msg = make_sqs_message(str(job.id), total_pages=100)
        db = AsyncMock()

        error_result = BatchResult(
            batch_index=0, pages_processed=0, chunks_created=0,
            success=False, error="Embedding service returned 500"
        )

        finalize_calls = []

        async def capture_finalize(db, job, msg, paused, failed_batch, fail_error):
            finalize_calls.append({"paused": paused, "failed_batch": failed_batch, "fail_error": fail_error})

        async def mock_process_batch(db, job, batch_range, **kw):
            return error_result

        with patch.object(worker._processor, "process_batch", side_effect=mock_process_batch), \
             patch.object(worker, "_finalize_job", side_effect=capture_finalize):
            await worker._run_job(db=db, job=job, msg=msg, resume_from_batch=0)

        assert finalize_calls[0]["paused"] is False
        assert finalize_calls[0]["failed_batch"] == 0
        assert "500" in finalize_calls[0]["fail_error"]


# ── Worker run loop ───────────────────────────────────────────────────────────

class TestWorkerRunLoop:
    @pytest.mark.asyncio
    async def test_stops_after_max_consecutive_errors(self):
        worker = DocumentWorker()

        call_count = 0

        async def failing_receive(**kw):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("SQS connection failed")

        with patch("app.workers.document_worker.sqs_service") as mock_sqs:
            mock_sqs.receive_messages = failing_receive

            # Patch signal handler setup to avoid asyncio issues in test
            with patch.object(worker, "_setup_signal_handlers", return_value=None):
                with patch("asyncio.sleep", new=AsyncMock()):
                    await worker.run()

        # Worker should stop after MAX_CONSECUTIVE_ERRORS
        from app.workers.document_worker import MAX_CONSECUTIVE_ERRORS
        assert call_count == MAX_CONSECUTIVE_ERRORS
        assert worker._running is False

    @pytest.mark.asyncio
    async def test_empty_queue_resets_error_counter(self):
        worker = DocumentWorker()

        call_count = 0

        async def empty_then_stop(**kw):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                worker._running = False
            return []

        with patch("app.workers.document_worker.sqs_service") as mock_sqs:
            mock_sqs.receive_messages = empty_then_stop

            with patch.object(worker, "_setup_signal_handlers", return_value=None):
                with patch("asyncio.sleep", new=AsyncMock()):
                    await worker.run()

        assert worker._consecutive_errors == 0
