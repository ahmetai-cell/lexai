"""
NotificationService — İş tamamlanma bildirimleri

Kanallar:
  1. Slack webhook (varsa SLACK_WEBHOOK_URL)
  2. Genişletilebilir: e-posta, push bildirimi

Her bildirim iş ID'si, belge adı, süre ve sonuç içerir.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class NotificationService:

    async def notify_job_completed(
        self,
        *,
        job_id: str,
        tenant_id: str,
        user_id: str,
        original_filename: str,
        total_pages: int,
        total_batches: int,
        duration_seconds: float,
        document_id: str | None = None,
    ) -> None:
        """Belge işleme tamamlandığında kullanıcıya bildirim gönder."""
        await self._send_slack_notification(
            title="✅ Belge İşleme Tamamlandı",
            color="#36A64F",
            fields=[
                ("Dosya Adı",    original_filename,            False),
                ("Toplam Sayfa", str(total_pages),             True),
                ("Batch Sayısı", str(total_batches),           True),
                ("Süre",         _format_duration(duration_seconds), True),
                ("İş ID",        job_id,                       True),
                ("Büro ID",      tenant_id,                    True),
            ],
        )
        logger.info(
            "job_completion_notified",
            job_id=job_id,
            filename=original_filename,
            duration_sec=round(duration_seconds, 1),
        )

    async def notify_job_failed(
        self,
        *,
        job_id: str,
        tenant_id: str,
        user_id: str,
        original_filename: str,
        failed_batch: int,
        error_message: str,
    ) -> None:
        """İş başarısız olduğunda bildirim gönder."""
        await self._send_slack_notification(
            title="❌ Belge İşleme Başarısız",
            color="#FF0000",
            fields=[
                ("Dosya Adı",   original_filename,         False),
                ("Başarısız Batch", str(failed_batch),     True),
                ("Hata",        error_message[:200],       False),
                ("İş ID",       job_id,                   True),
                ("Büro ID",     tenant_id,                True),
            ],
        )
        logger.error(
            "job_failure_notified",
            job_id=job_id,
            batch=failed_batch,
            error=error_message[:200],
        )

    async def notify_job_resumed(
        self,
        *,
        job_id: str,
        tenant_id: str,
        original_filename: str,
        resume_from_batch: int,
        total_batches: int,
    ) -> None:
        """Timeout sonrası iş kaldığı yerden devam ettiğinde bildirim."""
        await self._send_slack_notification(
            title="🔄 Belge İşleme Devam Ediyor",
            color="#FFCC00",
            fields=[
                ("Dosya Adı",   original_filename,    False),
                ("Devam Noktası", f"Batch {resume_from_batch}/{total_batches}", True),
                ("İş ID",       job_id,              True),
            ],
        )

    async def _send_slack_notification(
        self,
        title: str,
        color: str,
        fields: list[tuple[str, str, bool]],
    ) -> None:
        webhook_url = getattr(settings, "SLACK_WEBHOOK_URL", None)
        if not webhook_url:
            logger.debug("slack_notification_skipped_no_webhook")
            return

        ts = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
        payload = {
            "attachments": [
                {
                    "color": color,
                    "title": f"LexAI — {title}",
                    "fields": [
                        {"title": f[0], "value": f[1], "short": f[2]}
                        for f in fields
                    ] + [{"title": "Zaman", "value": ts, "short": True}],
                    "footer": "LexAI Document Pipeline",
                }
            ]
        }

        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    webhook_url,
                    content=json.dumps(payload),
                    headers={"Content-Type": "application/json"},
                )
                if resp.status_code != 200:
                    logger.warning("slack_notification_failed", status=resp.status_code)
        except Exception as e:
            logger.error("slack_notification_error", error=str(e))


def _format_duration(seconds: float) -> str:
    """İnsan okunabilir süre formatı."""
    if seconds < 60:
        return f"{seconds:.0f} saniye"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.1f} dakika"
    hours = minutes / 60
    return f"{hours:.1f} saat"


notification_service = NotificationService()
