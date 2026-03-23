"""
AnomalyDetector — Redis tabanlı gerçek zamanlı güvenlik anomali tespiti

4 kural:
  RULE-1  rate_limit    — Tek kullanıcı 1 saatte 100+ sorgu
  RULE-2  off_hours     — Gece 02:00-06:00 (UTC) arası yoğun erişim
  RULE-3  cross_tenant  — Başka büronun belge ID'siyle sorgu girişimi
  RULE-4  duplicate     — Aynı sorgunun 10 saniye içinde 5+ tekrarı

Her kural pozitif tetiklendiğinde:
  1. AnomalyEvent listesine eklenir
  2. SlackNotifier üzerinden anlık Slack bildirimi gönderilir
  3. AuditLog'a SECURITY_ANOMALY eventi yazılır (caller sorumluluğu)
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import redis.asyncio as aioredis

from app.audit.slack_notifier import slack_notifier, SlackField
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Eşikler ────────────────────────────────────────────────────────
RATE_LIMIT_WINDOW_SEC  = 3600   # 1 saat
RATE_LIMIT_MAX_QUERIES = 100    # Pencerede maksimum sorgu
OFF_HOURS_START        = 2      # 02:00 UTC
OFF_HOURS_END          = 6      # 06:00 UTC
DUPLICATE_WINDOW_SEC   = 10     # Tekrar penceresi
DUPLICATE_MAX_COUNT    = 5      # Bu pencerede maksimum tekrar
CROSS_TENANT_TTL_SEC   = 300    # Cross-tenant probe'u 5 dk sakla

# ── Redis anahtar şablonları ────────────────────────────────────────
KEY_RATE   = "anomaly:rate:{user_id}"        # sorted set: üye=ts, puan=ts
KEY_DUPE   = "anomaly:dupe:{user_id}:{qhash}"  # string counter
KEY_CROSS  = "anomaly:cross:{tenant_id}:{doc_id}"  # string marker


@dataclass
class AnomalyEvent:
    rule_id: str
    severity: str          # "critical" | "high" | "medium" | "low"
    title: str
    description: str
    user_id: str
    tenant_id: str
    details: dict = field(default_factory=dict)

    @property
    def is_critical(self) -> bool:
        return self.severity == "critical"


@dataclass
class DetectionContext:
    """Her API isteği için anomali kontrol bağlamı."""
    user_id: str
    tenant_id: str
    query_text: str
    document_ids: list[str] | None = None
    # cross_tenant: True ise tenant'a ait olmayan doc_id ile erişim denemesi
    cross_tenant_probe: bool = False
    ip_address: str | None = None
    timestamp: datetime | None = None

    def __post_init__(self) -> None:
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)

    @property
    def query_hash(self) -> str:
        return hashlib.sha256(self.query_text.encode()).hexdigest()[:16]


class AnomalyDetector:
    def __init__(self, redis_client: aioredis.Redis | None = None) -> None:
        self._redis = redis_client  # None → lazy init (get_redis() çağrılır)

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            from app.core.redis import get_redis
            self._redis = await get_redis()
        return self._redis

    # ── Ana kontrol metodu ─────────────────────────────────────────

    async def check(self, ctx: DetectionContext) -> list[AnomalyEvent]:
        """
        Tüm anomali kurallarını çalıştır.
        Tespit edilen her olay için Slack bildirimi gönderir.
        """
        events: list[AnomalyEvent] = []

        try:
            redis = await self._get_redis()
        except Exception as e:
            logger.error("anomaly_redis_unavailable", error=str(e))
            return events  # Redis yoksa tespit atlanır, uygulama çalışmaya devam eder

        # Kuralları paralel çalıştır
        results = await _gather_safe(
            self._check_rate_limit(redis, ctx),
            self._check_off_hours(ctx),
            self._check_cross_tenant(redis, ctx),
            self._check_duplicate_query(redis, ctx),
        )

        for event in results:
            if event is not None:
                events.append(event)
                await self._notify(event)

        if events:
            logger.warning(
                "anomaly_detected",
                user_id=ctx.user_id,
                tenant_id=ctx.tenant_id,
                rule_count=len(events),
                rules=[e.rule_id for e in events],
            )

        return events

    # ── Kural 1: Rate Limit ────────────────────────────────────────

    async def _check_rate_limit(
        self,
        redis: aioredis.Redis,
        ctx: DetectionContext,
    ) -> AnomalyEvent | None:
        """
        Kullanıcı son 1 saatte 100+ sorgu yaptıysa uyar.
        Redis sorted set: üye=zaman damgası, puan=zaman damgası.
        """
        key = KEY_RATE.format(user_id=ctx.user_id)
        now = time.time()
        window_start = now - RATE_LIMIT_WINDOW_SEC

        pipe = redis.pipeline()
        # Eski girişleri temizle
        pipe.zremrangebyscore(key, 0, window_start)
        # Bu isteği ekle
        pipe.zadd(key, {str(now): now})
        # Penceredeki toplam sayıyı al
        pipe.zcard(key)
        # Anahtarın expire süresini güncelle
        pipe.expire(key, RATE_LIMIT_WINDOW_SEC + 60)
        results = await pipe.execute()

        current_count = results[2]

        if current_count > RATE_LIMIT_MAX_QUERIES:
            return AnomalyEvent(
                rule_id="RULE-1-RATE-LIMIT",
                severity="high",
                title="Yüksek Sorgu Hızı",
                description=(
                    f"Kullanıcı son 1 saatte {current_count} sorgu gönderdi "
                    f"(limit: {RATE_LIMIT_MAX_QUERIES})."
                ),
                user_id=ctx.user_id,
                tenant_id=ctx.tenant_id,
                details={
                    "query_count": current_count,
                    "window_seconds": RATE_LIMIT_WINDOW_SEC,
                    "threshold": RATE_LIMIT_MAX_QUERIES,
                },
            )
        return None

    # ── Kural 2: Gece Saati Erişimi ────────────────────────────────

    async def _check_off_hours(
        self,
        ctx: DetectionContext,
    ) -> AnomalyEvent | None:
        """
        02:00-06:00 UTC arası erişimde uyarı ver.
        """
        hour = ctx.timestamp.hour if ctx.timestamp else datetime.now(timezone.utc).hour

        if OFF_HOURS_START <= hour < OFF_HOURS_END:
            return AnomalyEvent(
                rule_id="RULE-2-OFF-HOURS",
                severity="medium",
                title="Mesai Dışı Erişim",
                description=(
                    f"Saat {hour:02d}:xx UTC'de (02:00-06:00 penceresi) "
                    f"API erişimi tespit edildi."
                ),
                user_id=ctx.user_id,
                tenant_id=ctx.tenant_id,
                details={
                    "hour_utc": hour,
                    "off_hours_window": f"{OFF_HOURS_START:02d}:00-{OFF_HOURS_END:02d}:00 UTC",
                },
            )
        return None

    # ── Kural 3: Cross-Tenant Belge Erişim Girişimi ────────────────

    async def _check_cross_tenant(
        self,
        redis: aioredis.Redis,
        ctx: DetectionContext,
    ) -> AnomalyEvent | None:
        """
        Başka büronun belge ID'siyle erişim denemesi.
        cross_tenant_probe=True: RAGService tarafından set edilir
        (belge_id verildi ama retrieval 0 chunk döndü → olası cross-tenant probe).
        """
        if not ctx.cross_tenant_probe or not ctx.document_ids:
            return None

        # Bu probe'u Redis'e kaydet (tekrar sayımı için)
        for doc_id in ctx.document_ids:
            key = KEY_CROSS.format(tenant_id=ctx.tenant_id, doc_id=doc_id)
            count = await redis.incr(key)
            await redis.expire(key, CROSS_TENANT_TTL_SEC)

            if count == 1:  # İlk denemede uyar
                return AnomalyEvent(
                    rule_id="RULE-3-CROSS-TENANT",
                    severity="critical",
                    title="Yabancı Belge Erişim Girişimi",
                    description=(
                        f"Belge '{doc_id}' bu büroye ait değil ya da erişim reddedildi. "
                        f"Olası cross-tenant veri erişim girişimi."
                    ),
                    user_id=ctx.user_id,
                    tenant_id=ctx.tenant_id,
                    details={
                        "document_ids": ctx.document_ids,
                        "probe_count": count,
                    },
                )
        return None

    # ── Kural 4: Tekrarlayan Sorgu ─────────────────────────────────

    async def _check_duplicate_query(
        self,
        redis: aioredis.Redis,
        ctx: DetectionContext,
    ) -> AnomalyEvent | None:
        """
        Aynı sorgunun 10 saniye içinde 5+ tekrarında uyarı ver.
        Redis string counter, TTL=10s.
        """
        key = KEY_DUPE.format(
            user_id=ctx.user_id,
            qhash=ctx.query_hash,
        )

        # SET NX yoksa oluştur, varsa artır
        pipe = redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, DUPLICATE_WINDOW_SEC)
        results = await pipe.execute()
        count = results[0]

        if count >= DUPLICATE_MAX_COUNT:
            return AnomalyEvent(
                rule_id="RULE-4-DUPLICATE-QUERY",
                severity="medium",
                title="Tekrarlayan Sorgu Tespit Edildi",
                description=(
                    f"Aynı sorgu (hash: {ctx.query_hash}) {DUPLICATE_WINDOW_SEC} saniye içinde "
                    f"{count} kez gönderildi (limit: {DUPLICATE_MAX_COUNT})."
                ),
                user_id=ctx.user_id,
                tenant_id=ctx.tenant_id,
                details={
                    "query_hash": ctx.query_hash,
                    "repeat_count": count,
                    "window_seconds": DUPLICATE_WINDOW_SEC,
                    "threshold": DUPLICATE_MAX_COUNT,
                },
            )
        return None

    # ── Slack bildirimi ────────────────────────────────────────────

    async def _notify(self, event: AnomalyEvent) -> None:
        fields = [
            SlackField("Kural Kodu",  event.rule_id, short=True),
            SlackField("Önem Derecesi", event.severity.upper(), short=True),
        ]
        for k, v in event.details.items():
            fields.append(SlackField(k, str(v), short=True))

        await slack_notifier.send_anomaly_alert(
            rule_id=event.rule_id,
            severity=event.severity,
            title=event.title,
            description=event.description,
            fields=fields,
            tenant_id=event.tenant_id,
            user_id=event.user_id,
        )


async def _gather_safe(*coros):
    """Tüm coroutine'leri çalıştır; birinin hatası diğerlerini etkilemesin."""
    import asyncio
    results = await asyncio.gather(*coros, return_exceptions=True)
    return [r if not isinstance(r, Exception) else None for r in results]


anomaly_detector = AnomalyDetector()
