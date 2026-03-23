"""
BatchProcessor — 50 Sayfalık Batch İşleme Motoru

Akış (tek batch için):
  1. S3'ten PDF içeriğini indir (zaten bellekte ise cache'den al)
  2. PyPDF2 ile sayfaları ayır
  3. OCR → metin çıkar (Textract veya doğrudan metin katmanı)
  4. LegalChunker ile hukuki parçalara böl
  5. Embedding hesapla (Titan Embeddings)
  6. DocumentChunk'ları DB'ye yaz
  7. Progress checkpoint'i güncelle

Her batch başarıyla tamamlanınca last_completed_batch güncellenir.
Timeout oluşursa işlenmemiş batch'ler için re-queue yapılır.
"""
from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.document_job import DocumentProcessingJob, JobStatus
from app.services.s3_service import s3_service

logger = get_logger(__name__)

# Bir batch'in işlenme için maksimum süresi (saniye)
BATCH_TIMEOUT_SEC = 120
# SQS visibility timeout uzatma aralığı (her batch işleminde)
VISIBILITY_EXTEND_SEC = 180


@dataclass
class BatchResult:
    batch_index: int
    pages_processed: int
    chunks_created: int
    success: bool
    error: str | None = None


@dataclass
class BatchRange:
    start_page: int   # dahil
    end_page: int     # dahil
    batch_index: int


class BatchProcessor:

    def __init__(self) -> None:
        # Büyük PDF'ler için batch'ler arasında S3 içeriğini cache'le
        self._pdf_cache: dict[str, bytes] = {}

    # ── Ana batch işleme ─────────────────────────────────────────

    async def process_batch(
        self,
        db: AsyncSession,
        job: DocumentProcessingJob,
        batch_range: BatchRange,
        sqs_receipt_handle: str | None = None,
    ) -> BatchResult:
        """
        Tek bir batch'i işle: S3 indir → ayır → chunk → embed → DB yaz.
        Timeout aşılırsa BatchResult(success=False) döner.
        """
        try:
            result = await asyncio.wait_for(
                self._process_batch_inner(db, job, batch_range, sqs_receipt_handle),
                timeout=BATCH_TIMEOUT_SEC,
            )
            return result
        except asyncio.TimeoutError:
            logger.warning(
                "batch_timeout",
                job_id=str(job.id),
                batch_index=batch_range.batch_index,
                timeout_sec=BATCH_TIMEOUT_SEC,
            )
            return BatchResult(
                batch_index=batch_range.batch_index,
                pages_processed=0,
                chunks_created=0,
                success=False,
                error=f"Batch {batch_range.batch_index} timeout ({BATCH_TIMEOUT_SEC}s aşıldı)",
            )

    async def _process_batch_inner(
        self,
        db: AsyncSession,
        job: DocumentProcessingJob,
        batch_range: BatchRange,
        sqs_receipt_handle: str | None,
    ) -> BatchResult:
        """Gerçek batch işleme mantığı."""

        # SQS visibility timeout uzat (uzun işlem için)
        if sqs_receipt_handle:
            try:
                from app.services.sqs_service import sqs_service
                await sqs_service.extend_visibility(
                    receipt_handle=sqs_receipt_handle,
                    additional_seconds=VISIBILITY_EXTEND_SEC,
                )
            except Exception as e:
                logger.warning("sqs_visibility_extend_failed", error=str(e))

        # 1. PDF içeriğini al (cache'de varsa S3'e gitmez)
        pdf_bytes = await self._get_pdf_bytes(job.s3_key)

        # 2. Sayfaları çıkar
        pages = self._extract_pages(pdf_bytes, batch_range)
        if not pages:
            return BatchResult(
                batch_index=batch_range.batch_index,
                pages_processed=0,
                chunks_created=0,
                success=True,
                error=None,
            )

        # 3-5. Metin çıkar → chunk → embed → DB yaz
        chunks_created = await self._text_to_chunks(
            db=db,
            job=job,
            pages=pages,
            batch_range=batch_range,
        )

        logger.info(
            "batch_processed",
            job_id=str(job.id),
            batch_index=batch_range.batch_index,
            pages=len(pages),
            chunks=chunks_created,
        )

        return BatchResult(
            batch_index=batch_range.batch_index,
            pages_processed=len(pages),
            chunks_created=chunks_created,
            success=True,
        )

    # ── PDF yardımcıları ─────────────────────────────────────────

    async def _get_pdf_bytes(self, s3_key: str) -> bytes:
        if s3_key not in self._pdf_cache:
            self._pdf_cache[s3_key] = await s3_service.download(s3_key)
        return self._pdf_cache[s3_key]

    def _extract_pages(
        self,
        pdf_bytes: bytes,
        batch_range: BatchRange,
    ) -> list[tuple[int, str]]:
        """
        PDF'ten belirtilen sayfa aralığındaki metinleri çıkar.
        Returns: [(page_number, page_text), ...]
        """
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        except ImportError:
            # pypdf yoksa PyPDF2 dene
            try:
                import PyPDF2
                reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
            except ImportError:
                logger.error("no_pdf_library", message="pypdf veya PyPDF2 gerekli")
                return []

        pages = []
        for page_num in range(batch_range.start_page, min(batch_range.end_page + 1, len(reader.pages))):
            try:
                text = reader.pages[page_num].extract_text() or ""
                if text.strip():
                    pages.append((page_num + 1, text))  # 1-indexed page number
            except Exception as e:
                logger.warning(
                    "page_extraction_failed",
                    page=page_num,
                    error=str(e)[:100],
                )
        return pages

    async def _text_to_chunks(
        self,
        db: AsyncSession,
        job: DocumentProcessingJob,
        pages: list[tuple[int, str]],
        batch_range: BatchRange,
    ) -> int:
        """
        Sayfa metinlerini hukuki chunk'lara böl, embed et, DB'ye yaz.
        Returns: oluşturulan chunk sayısı
        """
        from app.rag.chunker import LegalChunker
        from app.services.embedding_service import embedding_service
        from app.models.embedding import DocumentChunk

        chunker = LegalChunker(
            doc_name=job.original_filename,
        )
        chunks_created = 0

        for page_number, page_text in pages:
            text_chunks = chunker.chunk(
                text=page_text,
                page_number=page_number,
            )

            for i, tc in enumerate(text_chunks):
                try:
                    # Embedding al
                    vector = await embedding_service.embed_text(tc.text)

                    chunk = DocumentChunk(
                        document_id=job.document_id,
                        tenant_id=job.tenant_id,
                        chunk_text=tc.text,
                        chunk_index=batch_range.batch_index * 1000 + i,
                        page_number=tc.page_number,
                        section_title=None,
                        article_number=None,
                        embedding=vector,
                        source_metadata={
                            "batch_index": batch_range.batch_index,
                            "label": tc.label,
                        },
                    )
                    db.add(chunk)
                    chunks_created += 1
                except Exception as e:
                    logger.error(
                        "chunk_embedding_failed",
                        page=page_number,
                        chunk_idx=i,
                        error=str(e)[:200],
                    )

        await db.flush()
        return chunks_created

    def clear_cache(self, s3_key: str | None = None) -> None:
        """PDF önbelleğini temizle (job tamamlandıktan sonra belleği boşalt)."""
        if s3_key:
            self._pdf_cache.pop(s3_key, None)
        else:
            self._pdf_cache.clear()

    @staticmethod
    def compute_batches(
        total_pages: int,
        batch_size: int = 50,
        resume_from_batch: int = 0,
    ) -> list[BatchRange]:
        """
        Tüm batch aralıklarını hesapla.
        resume_from_batch > 0 ise önceki batch'ler atlanır.
        """
        batches = []
        batch_idx = 0
        for start in range(0, total_pages, batch_size):
            end = min(start + batch_size - 1, total_pages - 1)
            if batch_idx >= resume_from_batch:
                batches.append(BatchRange(
                    start_page=start,
                    end_page=end,
                    batch_index=batch_idx,
                ))
            batch_idx += 1
        return batches
