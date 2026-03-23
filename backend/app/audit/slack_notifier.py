"""
SlackNotifier — Güvenlik uyarılarını anında Slack'e gönderir.

Webhook URL .env'den okunur (SLACK_WEBHOOK_URL).
URL tanımsızsa bildirim sessizce atlanır (production'da mutlaka set edilmeli).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Severity → Slack rengi eşleşmesi
SEVERITY_COLORS = {
    "critical": "#FF0000",
    "high":     "#FF6600",
    "medium":   "#FFCC00",
    "low":      "#36A64F",
}


@dataclass
class SlackField:
    title: str
    value: str
    short: bool = True


class SlackNotifier:
    def __init__(self) -> None:
        self._webhook_url: str | None = getattr(settings, "SLACK_WEBHOOK_URL", None)

    async def send_anomaly_alert(
        self,
        rule_id: str,
        severity: str,
        title: str,
        description: str,
        fields: list[SlackField] | None = None,
        tenant_id: str = "",
        user_id: str = "",
    ) -> bool:
        """
        Slack'e anomali uyarısı gönder.
        Returns True iff mesaj başarıyla gönderildi.
        """
        if not self._webhook_url:
            logger.warning(
                "slack_webhook_not_configured",
                rule_id=rule_id,
                severity=severity,
            )
            return False

        payload = self._build_payload(
            rule_id=rule_id,
            severity=severity,
            title=title,
            description=description,
            fields=fields or [],
            tenant_id=tenant_id,
            user_id=user_id,
        )

        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    self._webhook_url,
                    content=json.dumps(payload),
                    headers={"Content-Type": "application/json"},
                )
                if resp.status_code == 200:
                    logger.info(
                        "slack_alert_sent",
                        rule_id=rule_id,
                        severity=severity,
                    )
                    return True
                else:
                    logger.error(
                        "slack_alert_failed",
                        status=resp.status_code,
                        body=resp.text[:200],
                    )
                    return False
        except Exception as e:
            logger.error("slack_send_error", error=str(e), rule_id=rule_id)
            return False

    def _build_payload(
        self,
        rule_id: str,
        severity: str,
        title: str,
        description: str,
        fields: list[SlackField],
        tenant_id: str,
        user_id: str,
    ) -> dict:
        color = SEVERITY_COLORS.get(severity, "#CCCCCC")
        ts = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M:%S UTC")

        attachment_fields = [
            {"title": f.title, "value": f.value, "short": f.short}
            for f in fields
        ] + [
            {"title": "Büro ID",      "value": tenant_id or "-", "short": True},
            {"title": "Kullanıcı ID", "value": user_id or "-",   "short": True},
            {"title": "Kural",        "value": rule_id,           "short": True},
            {"title": "Zaman",        "value": ts,                "short": True},
        ]

        return {
            "attachments": [
                {
                    "color": color,
                    "title": f"🚨 LexAI Güvenlik Uyarısı — {title}",
                    "text": description,
                    "fields": attachment_fields,
                    "footer": "LexAI Security Monitor",
                    "ts": int(datetime.now(timezone.utc).timestamp()),
                }
            ]
        }


slack_notifier = SlackNotifier()
