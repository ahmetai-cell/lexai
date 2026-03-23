"""
AnomalyDetector — birim testleri (Redis ve Slack mock'lanır)
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.audit.anomaly_detector import (
    AnomalyDetector,
    AnomalyEvent,
    DetectionContext,
    RATE_LIMIT_MAX_QUERIES,
    RATE_LIMIT_WINDOW_SEC,
    OFF_HOURS_START,
    OFF_HOURS_END,
    DUPLICATE_MAX_COUNT,
    DUPLICATE_WINDOW_SEC,
)


def make_ctx(
    user_id: str | None = None,
    tenant_id: str | None = None,
    query: str = "test sorgu",
    document_ids: list | None = None,
    cross_tenant: bool = False,
    hour: int = 10,  # default: mesai saati
) -> DetectionContext:
    ts = datetime(2026, 1, 1, hour, 0, 0, tzinfo=timezone.utc)
    return DetectionContext(
        user_id=user_id or str(uuid.uuid4()),
        tenant_id=tenant_id or str(uuid.uuid4()),
        query_text=query,
        document_ids=document_ids,
        cross_tenant_probe=cross_tenant,
        timestamp=ts,
    )


def make_mock_redis() -> AsyncMock:
    """Pipeline sonuçlarıyla gerçekçi Redis mock'u."""
    pipe = AsyncMock()
    pipe.zremrangebyscore = AsyncMock()
    pipe.zadd = AsyncMock()
    pipe.zcard = AsyncMock()
    pipe.expire = AsyncMock()
    pipe.incr = AsyncMock()
    # default: eşik altı sonuçlar
    pipe.execute = AsyncMock(return_value=[None, None, 5, None])
    redis = AsyncMock()
    redis.pipeline = MagicMock(return_value=pipe)
    redis.incr = AsyncMock(return_value=1)
    redis.expire = AsyncMock()
    return redis


# ── DetectionContext ───────────────────────────────────────────────


def test_detection_context_query_hash_deterministic():
    ctx = make_ctx(query="TBK madde 112")
    h1 = ctx.query_hash
    h2 = ctx.query_hash
    assert h1 == h2
    assert len(h1) == 16  # İlk 16 karakter


def test_detection_context_different_queries_different_hashes():
    ctx1 = make_ctx(query="sorgu bir")
    ctx2 = make_ctx(query="sorgu iki")
    assert ctx1.query_hash != ctx2.query_hash


def test_detection_context_auto_timestamp():
    ctx = DetectionContext(user_id="u", tenant_id="t", query_text="x")
    assert ctx.timestamp is not None


# ── RULE-1: Rate Limit ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rate_limit_not_triggered_below_threshold():
    detector = AnomalyDetector()
    redis = make_mock_redis()
    # 50 sorgu — eşiğin altında
    redis.pipeline.return_value.execute = AsyncMock(return_value=[None, None, 50, None])

    ctx = make_ctx()
    event = await detector._check_rate_limit(redis, ctx)
    assert event is None


@pytest.mark.asyncio
async def test_rate_limit_triggered_above_threshold():
    detector = AnomalyDetector()
    redis = make_mock_redis()
    # 101 sorgu — eşiğin üstünde
    redis.pipeline.return_value.execute = AsyncMock(
        return_value=[None, None, RATE_LIMIT_MAX_QUERIES + 1, None]
    )

    ctx = make_ctx()
    event = await detector._check_rate_limit(redis, ctx)

    assert event is not None
    assert event.rule_id == "RULE-1-RATE-LIMIT"
    assert event.severity == "high"
    assert event.details["query_count"] == RATE_LIMIT_MAX_QUERIES + 1


@pytest.mark.asyncio
async def test_rate_limit_event_contains_correct_threshold():
    detector = AnomalyDetector()
    redis = make_mock_redis()
    redis.pipeline.return_value.execute = AsyncMock(
        return_value=[None, None, 150, None]
    )

    ctx = make_ctx()
    event = await detector._check_rate_limit(redis, ctx)
    assert event.details["threshold"] == RATE_LIMIT_MAX_QUERIES


# ── RULE-2: Off Hours ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_off_hours_triggered_at_3am():
    detector = AnomalyDetector()
    ctx = make_ctx(hour=3)  # 03:00 UTC
    event = await detector._check_off_hours(ctx)

    assert event is not None
    assert event.rule_id == "RULE-2-OFF-HOURS"
    assert event.severity == "medium"
    assert event.details["hour_utc"] == 3


@pytest.mark.asyncio
async def test_off_hours_not_triggered_at_9am():
    detector = AnomalyDetector()
    ctx = make_ctx(hour=9)  # 09:00 UTC — mesai saati
    event = await detector._check_off_hours(ctx)
    assert event is None


@pytest.mark.asyncio
async def test_off_hours_not_triggered_at_midnight():
    detector = AnomalyDetector()
    ctx = make_ctx(hour=0)  # 00:00 UTC — pencere dışı
    event = await detector._check_off_hours(ctx)
    assert event is None


@pytest.mark.asyncio
async def test_off_hours_triggered_at_boundary_start():
    detector = AnomalyDetector()
    ctx = make_ctx(hour=OFF_HOURS_START)  # 02:00 UTC — tam başlangıç
    event = await detector._check_off_hours(ctx)
    assert event is not None


@pytest.mark.asyncio
async def test_off_hours_not_triggered_at_boundary_end():
    detector = AnomalyDetector()
    ctx = make_ctx(hour=OFF_HOURS_END)  # 06:00 UTC — pencere dışı (< değil <=)
    event = await detector._check_off_hours(ctx)
    assert event is None


# ── RULE-3: Cross-Tenant ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_cross_tenant_triggered_when_probe_flag_set():
    detector = AnomalyDetector()
    redis = make_mock_redis()
    redis.incr = AsyncMock(return_value=1)

    ctx = make_ctx(document_ids=["foreign-doc-abc"], cross_tenant=True)
    event = await detector._check_cross_tenant(redis, ctx)

    assert event is not None
    assert event.rule_id == "RULE-3-CROSS-TENANT"
    assert event.severity == "critical"
    assert "foreign-doc-abc" in event.details["document_ids"]


@pytest.mark.asyncio
async def test_cross_tenant_not_triggered_without_probe_flag():
    detector = AnomalyDetector()
    redis = make_mock_redis()

    ctx = make_ctx(document_ids=["my-doc"], cross_tenant=False)
    event = await detector._check_cross_tenant(redis, ctx)
    assert event is None


@pytest.mark.asyncio
async def test_cross_tenant_not_triggered_without_document_ids():
    detector = AnomalyDetector()
    redis = make_mock_redis()

    ctx = make_ctx(document_ids=None, cross_tenant=True)
    event = await detector._check_cross_tenant(redis, ctx)
    assert event is None


# ── RULE-4: Duplicate Query ───────────────────────────────────────


@pytest.mark.asyncio
async def test_duplicate_query_triggered_at_threshold():
    detector = AnomalyDetector()
    redis = make_mock_redis()
    redis.pipeline.return_value.execute = AsyncMock(
        return_value=[DUPLICATE_MAX_COUNT, None]
    )

    ctx = make_ctx(query="tekrarlayan sorgu")
    event = await detector._check_duplicate_query(redis, ctx)

    assert event is not None
    assert event.rule_id == "RULE-4-DUPLICATE-QUERY"
    assert event.severity == "medium"
    assert event.details["repeat_count"] == DUPLICATE_MAX_COUNT


@pytest.mark.asyncio
async def test_duplicate_query_not_triggered_below_threshold():
    detector = AnomalyDetector()
    redis = make_mock_redis()
    redis.pipeline.return_value.execute = AsyncMock(return_value=[2, None])

    ctx = make_ctx()
    event = await detector._check_duplicate_query(redis, ctx)
    assert event is None


@pytest.mark.asyncio
async def test_duplicate_query_event_contains_hash():
    detector = AnomalyDetector()
    redis = make_mock_redis()
    redis.pipeline.return_value.execute = AsyncMock(return_value=[10, None])

    ctx = make_ctx(query="özel sorgu metni")
    event = await detector._check_duplicate_query(redis, ctx)

    assert event is not None
    assert event.details["query_hash"] == ctx.query_hash


# ── Ana check() metodu ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_returns_empty_when_no_anomalies():
    detector = AnomalyDetector()
    redis = make_mock_redis()
    # Tüm sayaçlar eşiğin altında
    redis.pipeline.return_value.execute = AsyncMock(return_value=[None, None, 5, None])

    detector._redis = redis

    ctx = make_ctx(hour=10)  # mesai saati, düşük sayaç

    with patch.object(detector, "_notify", new_callable=AsyncMock):
        events = await detector.check(ctx)

    assert events == []


@pytest.mark.asyncio
async def test_check_notifies_on_anomaly():
    detector = AnomalyDetector()
    redis = make_mock_redis()
    # Rate limit aşıldı
    redis.pipeline.return_value.execute = AsyncMock(
        return_value=[None, None, 150, None]
    )
    detector._redis = redis

    ctx = make_ctx(hour=10)

    notify_mock = AsyncMock()
    with patch.object(detector, "_notify", notify_mock):
        events = await detector.check(ctx)

    # En az rate-limit eventi var
    rate_events = [e for e in events if e.rule_id == "RULE-1-RATE-LIMIT"]
    assert len(rate_events) >= 1
    notify_mock.assert_awaited()


@pytest.mark.asyncio
async def test_check_returns_empty_on_redis_unavailable():
    detector = AnomalyDetector(redis_client=None)

    with patch(
        "app.audit.anomaly_detector.AnomalyDetector._get_redis",
        side_effect=Exception("Redis bağlantısı yok"),
    ):
        ctx = make_ctx()
        events = await detector.check(ctx)

    assert events == []  # Redis yoksa tespit atlanır, uygulama çalışmaya devam eder


# ── AnomalyEvent ──────────────────────────────────────────────────


def test_anomaly_event_is_critical():
    event = AnomalyEvent(
        rule_id="RULE-3-CROSS-TENANT",
        severity="critical",
        title="T",
        description="D",
        user_id="u",
        tenant_id="t",
    )
    assert event.is_critical is True


def test_anomaly_event_not_critical_for_medium():
    event = AnomalyEvent(
        rule_id="RULE-2-OFF-HOURS",
        severity="medium",
        title="T",
        description="D",
        user_id="u",
        tenant_id="t",
    )
    assert event.is_critical is False
