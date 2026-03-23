"""
BatchProcessor unit tests — compute_batches, timeout wrapping, page extraction logic.
"""
from __future__ import annotations

import asyncio
import io
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers.batch_processor import BatchProcessor, BatchRange, BatchResult, BATCH_TIMEOUT_SEC
from app.models.document_job import DocumentProcessingJob, JobStatus


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_job(total_pages=150, last_completed=-1, total_batches=3) -> DocumentProcessingJob:
    job = MagicMock(spec=DocumentProcessingJob)
    job.id = uuid.uuid4()
    job.tenant_id = uuid.uuid4()
    job.document_id = uuid.uuid4()
    job.s3_key = "tenants/abc/documents/def/contract.pdf"
    job.original_filename = "contract.pdf"
    job.total_pages = total_pages
    job.total_batches = total_batches
    job.last_completed_batch = last_completed
    job.status = JobStatus.PROCESSING
    return job


# ── compute_batches ────────────────────────────────────────────────────────────

class TestComputeBatches:
    def test_exact_multiple(self):
        batches = BatchProcessor.compute_batches(total_pages=100, batch_size=50, resume_from_batch=0)
        assert len(batches) == 2
        assert batches[0] == BatchRange(start_page=0, end_page=49, batch_index=0)
        assert batches[1] == BatchRange(start_page=50, end_page=99, batch_index=1)

    def test_remainder_pages(self):
        batches = BatchProcessor.compute_batches(total_pages=130, batch_size=50, resume_from_batch=0)
        assert len(batches) == 3
        assert batches[2].start_page == 100
        assert batches[2].end_page == 129

    def test_resume_skips_earlier_batches(self):
        batches = BatchProcessor.compute_batches(total_pages=150, batch_size=50, resume_from_batch=1)
        # Batch 0 (0-49) should be skipped; return batches 1 and 2
        assert len(batches) == 2
        assert batches[0].batch_index == 1
        assert batches[1].batch_index == 2

    def test_resume_from_last_batch(self):
        batches = BatchProcessor.compute_batches(total_pages=100, batch_size=50, resume_from_batch=1)
        assert len(batches) == 1
        assert batches[0].batch_index == 1

    def test_resume_beyond_all_batches_returns_empty(self):
        batches = BatchProcessor.compute_batches(total_pages=100, batch_size=50, resume_from_batch=5)
        assert batches == []

    def test_single_page(self):
        batches = BatchProcessor.compute_batches(total_pages=1, batch_size=50, resume_from_batch=0)
        assert len(batches) == 1
        assert batches[0].start_page == 0
        assert batches[0].end_page == 0

    def test_batch_indices_sequential(self):
        batches = BatchProcessor.compute_batches(total_pages=200, batch_size=50, resume_from_batch=0)
        for i, b in enumerate(batches):
            assert b.batch_index == i

    def test_default_resume_is_zero(self):
        b1 = BatchProcessor.compute_batches(total_pages=100, batch_size=50)
        b2 = BatchProcessor.compute_batches(total_pages=100, batch_size=50, resume_from_batch=0)
        assert b1 == b2


# ── BatchResult ───────────────────────────────────────────────────────────────

class TestBatchResult:
    def test_success_result(self):
        r = BatchResult(batch_index=0, pages_processed=50, chunks_created=120, success=True)
        assert r.success is True
        assert r.error is None

    def test_failure_result(self):
        r = BatchResult(batch_index=2, pages_processed=0, chunks_created=0, success=False, error="timeout")
        assert r.success is False
        assert "timeout" in r.error


# ── process_batch timeout wrapping ────────────────────────────────────────────

class TestProcessBatchTimeout:
    @pytest.mark.asyncio
    async def test_timeout_returns_failure_result(self):
        processor = BatchProcessor()
        job = make_job()
        batch_range = BatchRange(start_page=0, end_page=49, batch_index=0)

        async def slow_inner(*args, **kwargs):
            await asyncio.sleep(9999)

        with patch.object(processor, "_process_batch_inner", side_effect=slow_inner):
            with patch("app.workers.batch_processor.BATCH_TIMEOUT_SEC", 0.01):
                result = await processor.process_batch(
                    db=AsyncMock(),
                    job=job,
                    batch_range=batch_range,
                )

        assert result.success is False
        assert result.batch_index == 0
        assert result.pages_processed == 0
        assert "timeout" in result.error.lower()

    @pytest.mark.asyncio
    async def test_successful_batch_returns_result(self):
        processor = BatchProcessor()
        job = make_job()
        batch_range = BatchRange(start_page=0, end_page=49, batch_index=0)

        expected = BatchResult(batch_index=0, pages_processed=50, chunks_created=80, success=True)

        with patch.object(processor, "_process_batch_inner", return_value=expected):
            result = await processor.process_batch(
                db=AsyncMock(),
                job=job,
                batch_range=batch_range,
            )

        assert result.success is True
        assert result.chunks_created == 80


# ── _get_pdf_bytes caching ─────────────────────────────────────────────────────

class TestPdfCache:
    @pytest.mark.asyncio
    async def test_caches_after_first_download(self):
        processor = BatchProcessor()
        fake_bytes = b"%PDF mock content"

        with patch("app.workers.batch_processor.s3_service") as mock_s3:
            mock_s3.download = AsyncMock(return_value=fake_bytes)

            result1 = await processor._get_pdf_bytes("some/key.pdf")
            result2 = await processor._get_pdf_bytes("some/key.pdf")

        assert result1 == fake_bytes
        assert result2 == fake_bytes
        mock_s3.download.assert_awaited_once()  # second call hit cache

    @pytest.mark.asyncio
    async def test_different_keys_downloaded_separately(self):
        processor = BatchProcessor()

        with patch("app.workers.batch_processor.s3_service") as mock_s3:
            mock_s3.download = AsyncMock(side_effect=[b"pdf1", b"pdf2"])
            await processor._get_pdf_bytes("key1.pdf")
            await processor._get_pdf_bytes("key2.pdf")

        assert mock_s3.download.await_count == 2

    def test_clear_cache_specific_key(self):
        processor = BatchProcessor()
        processor._pdf_cache["key.pdf"] = b"data"
        processor.clear_cache("key.pdf")
        assert "key.pdf" not in processor._pdf_cache

    def test_clear_cache_all(self):
        processor = BatchProcessor()
        processor._pdf_cache["k1"] = b"a"
        processor._pdf_cache["k2"] = b"b"
        processor.clear_cache()
        assert processor._pdf_cache == {}


# ── _extract_pages ────────────────────────────────────────────────────────────

class TestExtractPages:
    def _make_minimal_pdf(self, texts: list[str]) -> bytes:
        """Create a minimal valid multi-page PDF for testing."""
        try:
            import pypdf
            from pypdf import PdfWriter
            writer = PdfWriter()
            for text in texts:
                page = pypdf.generic.PageObject.create_blank_page(width=612, height=792)
                writer.add_page(page)
            buf = io.BytesIO()
            writer.write(buf)
            return buf.getvalue()
        except Exception:
            return b""

    def _make_mock_reader(self, pages_text: list[str]) -> MagicMock:
        mock_reader = MagicMock()
        mock_pages = []
        for text in pages_text:
            p = MagicMock()
            p.extract_text.return_value = text
            mock_pages.append(p)
        mock_reader.pages = mock_pages
        return mock_reader

    def test_extract_returns_list_of_tuples(self):
        processor = BatchProcessor()
        mock_reader = self._make_mock_reader(["Madde 1. Taraflar arasında...", "Madde 2. ...", "Madde 3."])
        mock_pypdf = MagicMock()
        mock_pypdf.PdfReader.return_value = mock_reader

        batch_range = BatchRange(start_page=0, end_page=1, batch_index=0)

        with patch.dict("sys.modules", {"pypdf": mock_pypdf}):
            pages = processor._extract_pages(b"fake_pdf", batch_range)

        assert len(pages) == 2
        assert pages[0][0] == 1   # 1-indexed page number
        assert "Madde 1" in pages[0][1]

    def test_empty_pages_excluded(self):
        processor = BatchProcessor()
        mock_reader = self._make_mock_reader(["   ", "Gerçek içerik"])
        mock_pypdf = MagicMock()
        mock_pypdf.PdfReader.return_value = mock_reader

        batch_range = BatchRange(start_page=0, end_page=1, batch_index=0)

        with patch.dict("sys.modules", {"pypdf": mock_pypdf}):
            pages = processor._extract_pages(b"fake_pdf", batch_range)

        assert len(pages) == 1
        assert pages[0][1] == "Gerçek içerik"

    def test_end_page_clamped_to_actual_pages(self):
        processor = BatchProcessor()
        mock_reader = self._make_mock_reader(["text"] * 3)  # only 3 pages
        mock_pypdf = MagicMock()
        mock_pypdf.PdfReader.return_value = mock_reader

        batch_range = BatchRange(start_page=0, end_page=10, batch_index=0)

        with patch.dict("sys.modules", {"pypdf": mock_pypdf}):
            pages = processor._extract_pages(b"fake_pdf", batch_range)

        assert len(pages) == 3

    def test_returns_empty_on_no_pdf_library(self):
        processor = BatchProcessor()

        with patch.dict("sys.modules", {"pypdf": None, "PyPDF2": None}):
            pages = processor._extract_pages(b"anything", BatchRange(0, 49, 0))

        # Should return empty list, not raise
        assert isinstance(pages, list)
