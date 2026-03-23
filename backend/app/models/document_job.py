"""
DocumentProcessingJob — Büyük belge async işleme iş takibi

Her iş için:
  - Hangi batch'te kaldığı (last_completed_batch) → timeout sonrası resume
  - Toplam / tamamlanan batch sayısı → progress %
  - Hata mesajı (başarısız batch'ler için)
  - Durum geçişleri: pending → processing → completed | failed | paused
"""
import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, Float, Enum as SAEnum, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.db.base import Base


class JobStatus(str, Enum):
    PENDING    = "pending"      # SQS'e gönderildi, henüz alınmadı
    PROCESSING = "processing"   # Worker işliyor
    PAUSED     = "paused"       # Timeout — kaldığı yerden devam edecek
    COMPLETED  = "completed"    # Tüm batch'ler tamam
    FAILED     = "failed"       # Kurtarılamayan hata


class DocumentProcessingJob(Base):
    __tablename__ = "document_processing_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    # S3 konumu
    s3_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)

    # İş durumu
    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus), default=JobStatus.PENDING, nullable=False, index=True
    )

    # Batch ilerleme — checkpoint
    total_pages: Mapped[int] = mapped_column(Integer, default=0)
    total_batches: Mapped[int] = mapped_column(Integer, default=0)
    completed_batches: Mapped[int] = mapped_column(Integer, default=0)
    last_completed_batch: Mapped[int] = mapped_column(Integer, default=-1)
    # -1 → hiç batch tamamlanmadı; N → batch[0..N] tamamlandı

    # SQS takibi
    sqs_message_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    sqs_receipt_handle: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Hata bilgisi
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    failed_batch_index: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Zaman damgaları
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Ek meta (bildirim tercihleri vs.)
    job_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    @property
    def progress_pct(self) -> float:
        """Tamamlanma yüzdesi (0.0 – 100.0)."""
        if self.total_batches == 0:
            return 0.0
        return round(self.completed_batches / self.total_batches * 100, 1)

    @property
    def resume_from_batch(self) -> int:
        """Sonraki işlenecek batch index'i."""
        return self.last_completed_batch + 1

    def __repr__(self) -> str:
        return (
            f"<DocumentProcessingJob id={self.id} "
            f"status={self.status} "
            f"progress={self.progress_pct}%>"
        )
