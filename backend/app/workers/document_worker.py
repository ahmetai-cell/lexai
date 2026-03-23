"""
DocumentWorker — SQS Tüketici + Checkpoint-Aware Büyük Belge İşleyici

Akış:
  1. SQS'ten mesaj al (long-polling, 20s)
  2. DB'den işi yükle, durumu PROCESSING yap
  3. BatchProcessor ile 50'şer sayfalık batch'leri işle
     - Her batch sonrası: last_completed_batch DB'ye yaz
     - Her batch öncesi: SQS visibility timeout uzat
  4. Tümü tamamlansa: SQS mesajını sil, COMPLETED, bildirim gönder
  5. Timeout / hata:
     a. Kaldığı batch index'i DB'ye yaz (PAUSED)
     b. Yeni SQS mesajı ile kaldığı yerden re-queue et
     c. Orijinal mesajı sil (yeni mesaj zaten kuyruğa girdi)
  6. Kurtarılamaz hata: FAILED, bildirim gönder

Ayrı process olarak çalışır: python scripts/run_worker.py
"""
from __future__ import annotations

import asyncio
import signal
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.models.document_job import DocumentProcessingJob, JobStatus
from app.models.document import Document, DocumentStatus
from app.services.sqs_service import sqs_service, SQSMessage
from app.services.notification_service import notification_service
from app.workers.batch_processor import BatchProcessor, BatchRange

logger = get_logger(__name__)

# Worker ayarları
POLL_INTERVAL_SEC       = 1     # Mesaj gelmediyse bekle (SQS long-poll zaten 20s bekler)
MAX_CONSECUTIVE_ERRORS  = 5     # Üst üste bu kadar hata olursa worker durur
VISIBILITY_TIMEOUT_SEC  = 300   # SQS mesajının varsayılan visibility timeout'u


class DocumentWorker:
    def __init__(self) -> None:
        self._processor = BatchProcessor()
        self._running = False
        self._consecutive_errors = 0

    # ── Worker döngüsü ────────────────────────────────────────────

    async def run(self) -> None:
        """Ana worker döngüsü — SIGTERM gelene kadar çalışır."""
        self._running = True
        self._setup_signal_handlers()

        logger.info("document_worker_started")

        while self._running:
            try:
                messages = await sqs_service.receive_messages(
                    max_messages=1,
                    wait_seconds=20,
                    visibility_timeout=VISIBILITY_TIMEOUT_SEC,
                )

                if not messages:
                    self._consecutive_errors = 0
                    await asyncio.sleep(POLL_INTERVAL_SEC)
                    continue

                msg = messages[0]
                await self._process_message(msg)
                self._consecutive_errors = 0

            except Exception as e:
                self._consecutive_errors += 1
                logger.error(
                    "worker_loop_error",
                    error=str(e),
                    consecutive=self._consecutive_errors,
                )
                if self._consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    logger.critical("worker_too_many_errors_stopping")
                    self._running = False
                else:
                    await asyncio.sleep(min(30, 2 ** self._consecutive_errors))

        logger.info("document_worker_stopped")

    # ── Mesaj işleme ──────────────────────────────────────────────

    async def _process_message(self, msg: SQSMessage) -> None:
        body = msg.body
        job_id          = body.get("job_id")
        resume_from     = int(body.get("resume_from_batch", 0))

        logger.info(
            "worker_processing_message",
            job_id=job_id,
            message_id=msg.message_id,
            resume_from=resume_from,
        )

        async with AsyncSessionLocal() as db:
            job = await self._load_job(db, job_id)
            if not job:
                # İş DB'de yok — bozuk mesaj, sil
                await sqs_service.delete_message(msg.receipt_handle)
                return

            # Zaten tamamlandıysa tekrar işleme (idempotent)
            if job.status == JobStatus.COMPLETED:
                await sqs_service.delete_message(msg.receipt_handle)
                return

            await self._run_job(db, job, msg, resume_from)

    async def _run_job(
        self,
        db: AsyncSession,
        job: DocumentProcessingJob,
        msg: SQSMessage,
        resume_from_batch: int,
    ) -> None:
        """İşi batch'ler halinde yürüt. Checkpoint + hata yönetimi."""
        # İşi PROCESSING yap
        job.status = JobStatus.PROCESSING
        job.started_at = job.started_at or datetime.now(timezone.utc)
        job.sqs_receipt_handle = msg.receipt_handle
        job.sqs_message_id = msg.message_id
        await db.commit()

        total_pages   = job.total_pages or int(msg.body.get("total_pages", 0))
        batch_size    = int(msg.body.get("batch_size", 50))
        all_batches   = BatchProcessor.compute_batches(
            total_pages=total_pages,
            batch_size=batch_size,
            resume_from_batch=resume_from_batch,
        )

        if not job.total_batches:
            job.total_batches = (total_pages + batch_size - 1) // batch_size
            await db.commit()

        paused = False
        failed_batch = None
        fail_error   = None

        for batch_range in all_batches:
            result = await self._processor.process_batch(
                db=db,
                job=job,
                batch_range=batch_range,
                sqs_receipt_handle=msg.receipt_handle,
            )

            if result.success:
                # Checkpoint kaydet
                job.last_completed_batch = batch_range.batch_index
                job.completed_batches    = batch_range.batch_index + 1
                await db.commit()

                logger.info(
                    "batch_checkpoint_saved",
                    job_id=str(job.id),
                    batch=batch_range.batch_index,
                    progress=job.progress_pct,
                )
            else:
                # Timeout mu, başka hata mı?
                is_timeout = result.error and "timeout" in result.error.lower()
                if is_timeout:
                    paused = True
                else:
                    failed_batch = batch_range.batch_index
                    fail_error   = result.error
                break

        # İş durumunu güncelle ve bildir
        await self._finalize_job(
            db=db,
            job=job,
            msg=msg,
            paused=paused,
            failed_batch=failed_batch,
            fail_error=fail_error,
        )

    async def _finalize_job(
        self,
        db: AsyncSession,
        job: DocumentProcessingJob,
        msg: SQSMessage,
        paused: bool,
        failed_batch: int | None,
        fail_error: str | None,
    ) -> None:
        """Tamamlanma / pause / hata durumlarını yönet."""

        if paused:
            # Kaldığı yerden devam et
            resume_from = job.resume_from_batch
            job.status = JobStatus.PAUSED
            await db.commit()

            # Yeni SQS mesajı ile re-queue
            await sqs_service.requeue_for_resume(
                original_body=msg.body,
                resume_from_batch=resume_from,
                delay_seconds=10,
            )
            # Orijinal mesajı sil (yeni mesaj kuyruğa girdi)
            await sqs_service.delete_message(msg.receipt_handle)

            await notification_service.notify_job_resumed(
                job_id=str(job.id),
                tenant_id=str(job.tenant_id),
                original_filename=job.original_filename,
                resume_from_batch=resume_from,
                total_batches=job.total_batches,
            )
            logger.info(
                "job_paused_and_requeued",
                job_id=str(job.id),
                resume_from=resume_from,
            )

        elif failed_batch is not None:
            # Kurtarılamaz hata
            job.status = JobStatus.FAILED
            job.error_message = fail_error
            job.failed_batch_index = failed_batch
            await db.commit()

            # Mesajı SILME — SQS retry / DLQ işlesin
            await notification_service.notify_job_failed(
                job_id=str(job.id),
                tenant_id=str(job.tenant_id),
                user_id=str(job.user_id),
                original_filename=job.original_filename,
                failed_batch=failed_batch,
                error_message=fail_error or "Bilinmeyen hata",
            )
            logger.error(
                "job_failed",
                job_id=str(job.id),
                batch=failed_batch,
                error=fail_error,
            )

        else:
            # Tüm batch'ler başarılı → COMPLETED
            started  = job.started_at or datetime.now(timezone.utc)
            duration = (datetime.now(timezone.utc) - started).total_seconds()

            job.status       = JobStatus.COMPLETED
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()

            # Document tablosunu READY yap
            if job.document_id:
                doc = await db.get(Document, job.document_id)
                if doc:
                    doc.ocr_status = DocumentStatus.READY
                    await db.commit()

            # SQS mesajını sil (başarılı tamamlama)
            await sqs_service.delete_message(msg.receipt_handle)

            # PDF önbelleğini boşalt
            self._processor.clear_cache(job.s3_key)

            await notification_service.notify_job_completed(
                job_id=str(job.id),
                tenant_id=str(job.tenant_id),
                user_id=str(job.user_id),
                original_filename=job.original_filename,
                total_pages=job.total_pages,
                total_batches=job.total_batches,
                duration_seconds=duration,
                document_id=str(job.document_id) if job.document_id else None,
            )
            logger.info(
                "job_completed",
                job_id=str(job.id),
                duration_sec=round(duration, 1),
                batches=job.total_batches,
            )

    # ── DB yardımcıları ───────────────────────────────────────────

    async def _load_job(
        self,
        db: AsyncSession,
        job_id: str | None,
    ) -> DocumentProcessingJob | None:
        if not job_id:
            return None
        try:
            import uuid
            return await db.get(DocumentProcessingJob, uuid.UUID(job_id))
        except Exception as e:
            logger.error("job_load_failed", job_id=job_id, error=str(e))
            return None

    # ── Signal handling ───────────────────────────────────────────

    def _setup_signal_handlers(self) -> None:
        loop = asyncio.get_event_loop()

        def _stop(signame: str) -> None:
            logger.info("worker_shutdown_signal", signal=signame)
            self._running = False

        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, lambda s=sig.name: _stop(s))
            except NotImplementedError:
                pass  # Windows


