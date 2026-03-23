"""
SQSService — Belge işleme kuyruk yönetimi

Mesaj formatı:
{
  "job_id":            "uuid",
  "tenant_id":         "uuid",
  "user_id":           "uuid",
  "document_id":       "uuid",
  "s3_key":            "tenants/.../file.pdf",
  "original_filename": "sozlesme.pdf",
  "total_pages":       3500,
  "batch_size":        50,
  "resume_from_batch": 0        ← timeout sonrası resume noktası
}

Visibility Timeout: Worker bir mesajı aldığında SQS onu diğer worker'lardan
gizler (WORKER_VISIBILITY_TIMEOUT saniye). Worker tamamlayamazsa mesaj
tekrar görünür hale gelir → otomatik retry.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from functools import partial

import boto3
from botocore.exceptions import ClientError

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

LARGE_FILE_PAGE_THRESHOLD = 3000   # Bu üzeri belge async pipeline'a girer
BATCH_SIZE = 50                    # Her batch'te işlenecek sayfa sayısı


@dataclass
class SQSMessage:
    receipt_handle: str
    message_id: str
    body: dict


class SQSService:
    def __init__(self) -> None:
        self._client = boto3.client(
            "sqs",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        self._queue_url: str = getattr(settings, "SQS_QUEUE_URL", "")

    # ── Enqueue ───────────────────────────────────────────────────

    async def enqueue_document_job(
        self,
        job_id: str,
        tenant_id: str,
        user_id: str,
        document_id: str,
        s3_key: str,
        original_filename: str,
        total_pages: int,
        resume_from_batch: int = 0,
        batch_size: int = BATCH_SIZE,
    ) -> str:
        """
        Belge işleme işini SQS kuyruğuna ekle.
        Returns: SQS message ID
        """
        body = {
            "job_id":            job_id,
            "tenant_id":         tenant_id,
            "user_id":           user_id,
            "document_id":       document_id,
            "s3_key":            s3_key,
            "original_filename": original_filename,
            "total_pages":       total_pages,
            "batch_size":        batch_size,
            "resume_from_batch": resume_from_batch,
        }

        response = await asyncio.get_event_loop().run_in_executor(
            None,
            partial(
                self._client.send_message,
                QueueUrl=self._queue_url,
                MessageBody=json.dumps(body),
                MessageAttributes={
                    "job_id": {
                        "StringValue": job_id,
                        "DataType": "String",
                    },
                    "tenant_id": {
                        "StringValue": tenant_id,
                        "DataType": "String",
                    },
                },
            ),
        )

        msg_id = response["MessageId"]
        logger.info(
            "sqs_enqueued",
            job_id=job_id,
            message_id=msg_id,
            total_pages=total_pages,
            resume_from=resume_from_batch,
        )
        return msg_id

    # ── Receive ───────────────────────────────────────────────────

    async def receive_messages(
        self,
        max_messages: int = 1,
        wait_seconds: int = 20,          # Long-polling
        visibility_timeout: int | None = None,
    ) -> list[SQSMessage]:
        """
        SQS'ten mesaj al (long-polling).
        visibility_timeout=None → kuyruk varsayılanı kullanılır.
        """
        kwargs: dict = {
            "QueueUrl": self._queue_url,
            "MaxNumberOfMessages": max_messages,
            "WaitTimeSeconds": wait_seconds,
            "MessageAttributeNames": ["All"],
        }
        if visibility_timeout is not None:
            kwargs["VisibilityTimeout"] = visibility_timeout

        response = await asyncio.get_event_loop().run_in_executor(
            None,
            partial(self._client.receive_message, **kwargs),
        )

        messages = []
        for raw in response.get("Messages", []):
            try:
                body = json.loads(raw["Body"])
                messages.append(SQSMessage(
                    receipt_handle=raw["ReceiptHandle"],
                    message_id=raw["MessageId"],
                    body=body,
                ))
            except json.JSONDecodeError:
                logger.error("sqs_invalid_json", message_id=raw.get("MessageId"))

        return messages

    # ── Delete (başarılı tamamlama) ───────────────────────────────

    async def delete_message(self, receipt_handle: str) -> None:
        """Başarıyla işlenen mesajı kuyruktan sil."""
        await asyncio.get_event_loop().run_in_executor(
            None,
            partial(
                self._client.delete_message,
                QueueUrl=self._queue_url,
                ReceiptHandle=receipt_handle,
            ),
        )
        logger.debug("sqs_message_deleted", receipt_handle=receipt_handle[:20])

    # ── Visibility timeout uzat (uzun işlemler için) ───────────────

    async def extend_visibility(
        self,
        receipt_handle: str,
        additional_seconds: int,
    ) -> None:
        """
        İşlem süresince mesajın visibility timeout'unu uzat.
        Her batch'te çağrılarak timeout'dan kaçınılır.
        """
        await asyncio.get_event_loop().run_in_executor(
            None,
            partial(
                self._client.change_message_visibility,
                QueueUrl=self._queue_url,
                ReceiptHandle=receipt_handle,
                VisibilityTimeout=additional_seconds,
            ),
        )

    # ── Re-queue (paused job resume) ──────────────────────────────

    async def requeue_for_resume(
        self,
        original_body: dict,
        resume_from_batch: int,
        delay_seconds: int = 5,
    ) -> str:
        """
        Timeout/pause durumunda işi yeni bir SQS mesajı olarak
        kaldığı batch'ten tekrar kuyruğa ekle.
        """
        new_body = {**original_body, "resume_from_batch": resume_from_batch}
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            partial(
                self._client.send_message,
                QueueUrl=self._queue_url,
                MessageBody=json.dumps(new_body),
                DelaySeconds=delay_seconds,
            ),
        )
        msg_id = response["MessageId"]
        logger.info(
            "sqs_requeued_for_resume",
            job_id=original_body.get("job_id"),
            resume_from_batch=resume_from_batch,
            new_message_id=msg_id,
        )
        return msg_id

    @staticmethod
    def needs_async_pipeline(page_count: int) -> bool:
        """3000 sayfa üzeri belgeler async pipeline'a girer."""
        return page_count > LARGE_FILE_PAGE_THRESHOLD


sqs_service = SQSService()
