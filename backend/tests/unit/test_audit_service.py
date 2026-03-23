"""
AuditService — birim testleri (DB mock'lanır)
"""
import hashlib
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.audit.audit_service import AuditService, _hash_text, _count_tokens
from app.models.audit_log import AuditEventType


# ── Yardımcı fonksiyonlar ──────────────────────────────────────────


def test_hash_text_returns_sha256():
    result = _hash_text("test sorgu")
    expected = hashlib.sha256("test sorgu".encode()).hexdigest()
    assert result == expected


def test_hash_text_none_returns_none():
    assert _hash_text(None) is None


def test_hash_text_empty_returns_none():
    assert _hash_text("") is None


def test_count_tokens_approximate():
    text = "a" * 100  # 100 karakter ≈ 25 token
    assert _count_tokens(text) == 25


def test_count_tokens_none():
    assert _count_tokens(None) is None


def test_count_tokens_minimum_one():
    assert _count_tokens("ab") == 1  # max(1, 2//4) = max(1,0) = 1


# ── AuditService.log_api_request ──────────────────────────────────


@pytest.mark.asyncio
async def test_log_api_request_adds_to_session():
    service = AuditService()
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()

    tenant_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())

    entry = await service.log_api_request(
        db=db,
        tenant_id=tenant_id,
        user_id=user_id,
        event_type=AuditEventType.QUERY_RESPONSE,
        template_slug="contract_review",
        query_text="Sözleşme analizi yap",
        chunks_retrieved=5,
        response_generated=True,
        confidence_score=0.92,
        hallucination_flag=False,
    )

    db.add.assert_called_once_with(entry)
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_log_api_request_hashes_query():
    service = AuditService()
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()

    tenant_id = str(uuid.uuid4())
    raw_query = "Bu sözleşmeyi analiz et"

    entry = await service.log_api_request(
        db=db,
        tenant_id=tenant_id,
        user_id=None,
        event_type=AuditEventType.QUERY_SENT,
        query_text=raw_query,
    )

    # Ham metin saklanmamış olmalı
    assert entry.query_hash == hashlib.sha256(raw_query.encode()).hexdigest()
    assert raw_query not in str(entry.__dict__)


@pytest.mark.asyncio
async def test_log_api_request_extra_data_includes_chunks():
    service = AuditService()
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()

    tenant_id = str(uuid.uuid4())

    entry = await service.log_api_request(
        db=db,
        tenant_id=tenant_id,
        user_id=None,
        event_type=AuditEventType.QUERY_RESPONSE,
        chunks_retrieved=8,
        response_generated=True,
    )

    assert entry.extra_data["chunks_retrieved"] == 8
    assert entry.extra_data["response_generated"] is True


@pytest.mark.asyncio
async def test_log_api_request_invalid_uuid_raises():
    service = AuditService()
    db = AsyncMock()

    with pytest.raises(ValueError):
        await service.log_api_request(
            db=db,
            tenant_id="not-a-uuid",
            user_id=None,
            event_type=AuditEventType.QUERY_SENT,
        )


# ── AuditService.log_rag_query ─────────────────────────────────────


@pytest.mark.asyncio
async def test_log_rag_query_writes_response_event():
    service = AuditService()
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()

    tenant_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())

    entry = await service.log_rag_query(
        db=db,
        tenant_id=tenant_id,
        user_id=user_id,
        template_slug="case_law_analysis",
        document_ids=["doc-1", "doc-2"],
        query_text="Yargıtay kararını analiz et",
        chunks_retrieved=6,
        response_generated=True,
        confidence_score=0.88,
        hallucination_flag=False,
    )

    assert entry.event_type == AuditEventType.QUERY_RESPONSE
    assert entry.template_slug == "case_law_analysis"


@pytest.mark.asyncio
async def test_log_rag_query_writes_hallucination_event_when_flagged():
    service = AuditService()
    add_calls = []
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock(side_effect=lambda x: add_calls.append(x))

    tenant_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())

    await service.log_rag_query(
        db=db,
        tenant_id=tenant_id,
        user_id=user_id,
        template_slug="contract_review",
        document_ids=None,
        query_text="Sözleşme maddesini bul",
        chunks_retrieved=3,
        response_generated=True,
        confidence_score=0.55,
        hallucination_flag=True,
    )

    # İki kayıt: QUERY_RESPONSE + HALLUCINATION_FLAGGED
    assert db.add.call_count == 2
    event_types = [c.args[0].event_type for c in db.add.call_args_list]
    assert AuditEventType.HALLUCINATION_FLAGGED in event_types


@pytest.mark.asyncio
async def test_log_rag_query_includes_anomaly_rules():
    service = AuditService()
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()

    from app.audit.anomaly_detector import AnomalyEvent
    fake_event = AnomalyEvent(
        rule_id="RULE-1-RATE-LIMIT",
        severity="high",
        title="Yüksek hız",
        description="Test",
        user_id="u1",
        tenant_id="t1",
    )

    tenant_id = str(uuid.uuid4())
    entry = await service.log_rag_query(
        db=db,
        tenant_id=tenant_id,
        user_id=str(uuid.uuid4()),
        template_slug="test",
        document_ids=None,
        query_text="test",
        chunks_retrieved=0,
        response_generated=False,
        confidence_score=None,
        hallucination_flag=False,
        anomaly_events=[fake_event],
    )

    assert "RULE-1-RATE-LIMIT" in entry.extra_data.get("anomaly_rules", [])


# ── log_document_access ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_document_access_writes_correct_event():
    service = AuditService()
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()

    entry = await service.log_document_access(
        db=db,
        tenant_id=str(uuid.uuid4()),
        user_id=str(uuid.uuid4()),
        document_id="doc-abc-123",
    )

    assert entry.event_type == AuditEventType.DOCUMENT_ACCESS
    assert entry.document_id == "doc-abc-123"


# ── log_security_anomaly ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_log_security_anomaly_marks_in_extra_data():
    service = AuditService()
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()

    entry = await service.log_security_anomaly(
        db=db,
        tenant_id=str(uuid.uuid4()),
        user_id=str(uuid.uuid4()),
        rule_id="RULE-3-CROSS-TENANT",
        severity="critical",
        details={"document_ids": ["foreign-doc-id"]},
    )

    assert entry.extra_data["security_anomaly"] is True
    assert entry.extra_data["rule_id"] == "RULE-3-CROSS-TENANT"
    assert entry.extra_data["severity"] == "critical"
