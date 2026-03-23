import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import String, Text, DateTime, ForeignKey, Float, Boolean, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.db.base import Base


class AuditEventType(str, Enum):
    DOCUMENT_UPLOAD = "document_upload"
    DOCUMENT_ACCESS = "document_access"
    DOCUMENT_DELETE = "document_delete"
    QUERY_SENT = "query_sent"
    QUERY_RESPONSE = "query_response"
    HALLUCINATION_FLAGGED = "hallucination_flagged"
    LOGIN = "login"
    LOGIN_FAILED = "login_failed"
    API_KEY_USED = "api_key_used"
    EXPORT_GENERATED = "export_generated"


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    event_type: Mapped[AuditEventType] = mapped_column(
        SAEnum(AuditEventType), nullable=False, index=True
    )
    # İlgili kaynak referansları
    document_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    template_slug: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Sorgu ve yanıt özeti (tam metin saklanmaz – KVKK minimization)
    query_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)  # SHA-256
    query_token_count: Mapped[int | None] = mapped_column(nullable=True)

    # AI güven metrikleri
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    hallucination_flag: Mapped[bool] = mapped_column(Boolean, default=False)

    # Ağ bilgisi
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Ekstra yapılandırılmış veri
    extra_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
