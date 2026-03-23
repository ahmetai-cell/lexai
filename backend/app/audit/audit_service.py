"""
AuditService — Immutable Audit Log Yazıcısı (Katman 5)

KVKK Uyumluluğu:
  - Ham sorgu metni saklanmaz; yalnızca SHA-256 hash'i yazılır
  - Kayıtlar silinemez / değiştirilemez (PostgreSQL RULE ile DB seviyesinde korunur)
  - Her kayıt: Büro ID, Kullanıcı ID, Zaman, Belge, Prompt, Chunk sayısı, Yanıt durumu

Immutability:
  - Python tarafında UPDATE/DELETE metodu hiç tanımlanmamıştır
  - DB tarafında: infrastructure/postgres/audit_immutability.sql
    → ON UPDATE / ON DELETE kuralları ile INSTEAD NOTHING uygulanır
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.audit_log import AuditLog, AuditEventType

logger = get_logger(__name__)


def _hash_text(text: str | None) -> str | None:
    """SHA-256 hash (KVKK: ham metin saklanmaz)."""
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _count_tokens(text: str | None) -> int | None:
    """Yaklaşık token sayısı (4 karakter ≈ 1 token)."""
    if not text:
        return None
    return max(1, len(text) // 4)


class AuditService:
    """
    INSERT-only audit log servisi.
    Tüm metodlar yeni kayıt ekler; güncelleme/silme metodu yoktur.
    """

    async def log_api_request(
        self,
        db: AsyncSession,
        *,
        tenant_id: str,
        user_id: str | None,
        event_type: AuditEventType,
        document_id: str | None = None,
        conversation_id: str | None = None,
        message_id: str | None = None,
        template_slug: str | None = None,
        query_text: str | None = None,
        chunks_retrieved: int = 0,
        response_generated: bool = False,
        confidence_score: float | None = None,
        hallucination_flag: bool = False,
        ip_address: str | None = None,
        user_agent: str | None = None,
        extra_data: dict | None = None,
    ) -> AuditLog:
        """
        Immutable API isteği kaydı oluştur.

        Zorunlu alanlar: tenant_id, event_type
        Tüm diğer alanlar KVKK minimization ilkesiyle seçici saklanır.
        """
        try:
            tenant_uuid = uuid.UUID(tenant_id) if tenant_id else None
            user_uuid = uuid.UUID(user_id) if user_id else None
        except ValueError:
            logger.error("audit_invalid_uuid", tenant_id=tenant_id, user_id=user_id)
            raise

        entry = AuditLog(
            tenant_id=tenant_uuid,
            user_id=user_uuid,
            event_type=event_type,
            document_id=document_id,
            conversation_id=conversation_id,
            message_id=message_id,
            template_slug=template_slug,
            query_hash=_hash_text(query_text),
            query_token_count=_count_tokens(query_text),
            confidence_score=confidence_score,
            hallucination_flag=hallucination_flag,
            ip_address=ip_address,
            user_agent=user_agent,
            extra_data={
                **(extra_data or {}),
                "chunks_retrieved": chunks_retrieved,
                "response_generated": response_generated,
            },
            created_at=datetime.now(timezone.utc),
        )

        db.add(entry)
        await db.flush()   # ID üret ama commit etme (caller commit eder)

        logger.info(
            "audit_log_written",
            event_type=event_type.value,
            tenant_id=str(tenant_uuid),
            chunks=chunks_retrieved,
            response_generated=response_generated,
            hallucination=hallucination_flag,
            entry_id=str(entry.id),
        )

        return entry

    async def log_rag_query(
        self,
        db: AsyncSession,
        *,
        tenant_id: str,
        user_id: str | None,
        template_slug: str,
        document_ids: list[str] | None,
        query_text: str,
        chunks_retrieved: int,
        response_generated: bool,
        confidence_score: float | None,
        hallucination_flag: bool,
        conversation_id: str | None = None,
        ip_address: str | None = None,
        anomaly_events: list | None = None,
    ) -> AuditLog:
        """
        RAG pipeline tamamlandıktan sonra çağrılacak özelleşmiş log metodu.
        İki event yazar: QUERY_SENT + (opsiyonel) HALLUCINATION_FLAGGED.
        """
        extra: dict = {
            "document_ids": document_ids or [],
        }
        if anomaly_events:
            extra["anomaly_rules"] = [e.rule_id for e in anomaly_events]

        # Ana sorgu logu
        entry = await self.log_api_request(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            event_type=AuditEventType.QUERY_RESPONSE,
            template_slug=template_slug,
            query_text=query_text,
            chunks_retrieved=chunks_retrieved,
            response_generated=response_generated,
            confidence_score=confidence_score,
            hallucination_flag=hallucination_flag,
            conversation_id=conversation_id,
            ip_address=ip_address,
            extra_data=extra,
        )

        # Hallucination tespit edildiyse ayrı kayıt
        if hallucination_flag:
            await self.log_api_request(
                db=db,
                tenant_id=tenant_id,
                user_id=user_id,
                event_type=AuditEventType.HALLUCINATION_FLAGGED,
                template_slug=template_slug,
                confidence_score=confidence_score,
                hallucination_flag=True,
                extra_data={"parent_log_id": str(entry.id)},
            )

        return entry

    async def log_document_access(
        self,
        db: AsyncSession,
        *,
        tenant_id: str,
        user_id: str,
        document_id: str,
        ip_address: str | None = None,
    ) -> AuditLog:
        return await self.log_api_request(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            event_type=AuditEventType.DOCUMENT_ACCESS,
            document_id=document_id,
            ip_address=ip_address,
        )

    async def log_security_anomaly(
        self,
        db: AsyncSession,
        *,
        tenant_id: str,
        user_id: str,
        rule_id: str,
        severity: str,
        details: dict,
        ip_address: str | None = None,
    ) -> AuditLog:
        """Güvenlik anomalisi audit kaydı."""
        return await self.log_api_request(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            event_type=AuditEventType.QUERY_SENT,  # genel event; details'te rule_id var
            ip_address=ip_address,
            extra_data={
                "security_anomaly": True,
                "rule_id": rule_id,
                "severity": severity,
                **details,
            },
        )


audit_service = AuditService()
