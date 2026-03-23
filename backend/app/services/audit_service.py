"""
Audit Trail Service – KVKK m.12 ve baro denetimi için erişim kayıt sistemi
Her kritik işlem fire-and-forget olarak loglanır (background task).
"""
import hashlib
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.core.logging import get_logger
from app.models.audit_log import AuditLog, AuditEventType

logger = get_logger(__name__)


class AuditService:
    async def log(
        self,
        db: AsyncSession,
        *,
        tenant_id: str,
        event_type: AuditEventType,
        user_id: str | None = None,
        document_id: str | None = None,
        conversation_id: str | None = None,
        message_id: str | None = None,
        template_slug: str | None = None,
        query_text: str | None = None,
        confidence_score: float | None = None,
        hallucination_flag: bool = False,
        ip_address: str | None = None,
        user_agent: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Audit kaydı oluştur. Hata olursa sessizce logla – asıl işlemi engelleme."""
        try:
            query_hash = (
                hashlib.sha256(query_text.encode()).hexdigest()
                if query_text
                else None
            )
            query_token_count = len(query_text.split()) if query_text else None

            entry = AuditLog(
                tenant_id=tenant_id,
                user_id=user_id,
                event_type=event_type,
                document_id=document_id,
                conversation_id=conversation_id,
                message_id=message_id,
                template_slug=template_slug,
                query_hash=query_hash,
                query_token_count=query_token_count,
                confidence_score=confidence_score,
                hallucination_flag=hallucination_flag,
                ip_address=ip_address,
                user_agent=user_agent,
                metadata=metadata,
            )
            db.add(entry)
            await db.flush()
        except Exception as e:
            logger.error("audit_log_failed", error=str(e), event_type=event_type)

    async def get_activity_summary(
        self,
        db: AsyncSession,
        tenant_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> dict:
        """Kullanım özeti – audit raporu için."""
        result = await db.execute(
            select(
                AuditLog.event_type,
                func.count(AuditLog.id).label("count"),
                func.count(func.distinct(AuditLog.user_id)).label("unique_users"),
            )
            .where(
                and_(
                    AuditLog.tenant_id == tenant_id,
                    AuditLog.created_at >= start_date,
                    AuditLog.created_at <= end_date,
                )
            )
            .group_by(AuditLog.event_type)
        )
        rows = result.all()

        hallucination_count = await db.execute(
            select(func.count(AuditLog.id)).where(
                and_(
                    AuditLog.tenant_id == tenant_id,
                    AuditLog.hallucination_flag == True,
                    AuditLog.created_at >= start_date,
                    AuditLog.created_at <= end_date,
                )
            )
        )

        return {
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "events": [
                {"type": row.event_type, "count": row.count, "unique_users": row.unique_users}
                for row in rows
            ],
            "hallucination_alerts": hallucination_count.scalar() or 0,
        }

    async def get_document_access_log(
        self,
        db: AsyncSession,
        tenant_id: str,
        document_id: str,
    ) -> list[dict]:
        """Belgeye kimin, ne zaman, ne amaçla eriştiği."""
        result = await db.execute(
            select(AuditLog)
            .where(
                and_(
                    AuditLog.tenant_id == tenant_id,
                    AuditLog.document_id == document_id,
                )
            )
            .order_by(AuditLog.created_at.desc())
            .limit(100)
        )
        logs = result.scalars().all()
        return [
            {
                "event_type": log.event_type,
                "user_id": str(log.user_id) if log.user_id else None,
                "template": log.template_slug,
                "created_at": log.created_at.isoformat(),
                "ip": log.ip_address,
            }
            for log in logs
        ]


audit_service = AuditService()
