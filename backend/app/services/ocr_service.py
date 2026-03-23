"""
OCR Service – AWS Textract entegrasyonu

Özellikler:
- Confidence score tabanlı "Manuel İnceleme Gerekli" işaretleme
- Damgalı belge / el yazısı tespiti
- Tablo yapısı bozulmadan JSON'a aktarım
- Sayfa bazlı kalite raporu
"""
import json
import time
from dataclasses import dataclass, field
from enum import Enum

import boto3
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.exceptions import OCRFailureError
from app.core.logging import get_logger

logger = get_logger(__name__)

# Confidence eşikleri
HIGH_CONFIDENCE = 90.0      # Güvenilir metin
LOW_CONFIDENCE = 70.0       # Manuel inceleme gerekli
CRITICAL_CONFIDENCE = 50.0  # Kritik – mutlaka incelenmeli


class PageReviewStatus(str, Enum):
    OK = "ok"
    MANUAL_REVIEW = "manual_review"       # 70-90 arası
    CRITICAL_REVIEW = "critical_review"  # 50-70 arası
    UNREADABLE = "unreadable"            # 50 altı


@dataclass
class TableCell:
    row: int
    col: int
    text: str
    confidence: float
    row_span: int = 1
    col_span: int = 1


@dataclass
class ExtractedTable:
    page_number: int
    rows: int
    cols: int
    cells: list[TableCell]

    def to_json(self) -> dict:
        """Tablo yapısını matrix formatında JSON'a aktar."""
        matrix: list[list[str]] = [
            [""] * self.cols for _ in range(self.rows)
        ]
        for cell in self.cells:
            if cell.row < self.rows and cell.col < self.cols:
                matrix[cell.row][cell.col] = cell.text
        return {
            "page": self.page_number,
            "rows": self.rows,
            "cols": self.cols,
            "matrix": matrix,
            "cells_with_low_confidence": [
                {"row": c.row, "col": c.col, "text": c.text, "confidence": c.confidence}
                for c in self.cells
                if c.confidence < LOW_CONFIDENCE
            ],
        }


@dataclass
class PageOCRResult:
    page_number: int
    text: str
    avg_confidence: float
    min_confidence: float
    low_confidence_blocks: list[dict]
    tables: list[ExtractedTable]
    review_status: PageReviewStatus
    review_reason: str | None = None
    word_count: int = 0

    @property
    def needs_review(self) -> bool:
        return self.review_status in (
            PageReviewStatus.MANUAL_REVIEW,
            PageReviewStatus.CRITICAL_REVIEW,
            PageReviewStatus.UNREADABLE,
        )


@dataclass
class OCRResult:
    document_id: str
    total_pages: int
    full_text: str
    pages: list[PageOCRResult]
    tables: list[dict] = field(default_factory=list)
    pages_needing_review: list[int] = field(default_factory=list)
    overall_confidence: float = 0.0
    processing_time_ms: int = 0

    def to_summary(self) -> dict:
        return {
            "total_pages": self.total_pages,
            "overall_confidence": round(self.overall_confidence, 2),
            "pages_needing_review": self.pages_needing_review,
            "review_count": len(self.pages_needing_review),
            "tables_found": len(self.tables),
            "word_count": sum(p.word_count for p in self.pages),
        }


class OCRService:
    def __init__(self):
        self._textract = boto3.client(
            "textract",
            region_name=settings.TEXTRACT_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

    async def process_document(self, s3_bucket: str, s3_key: str, document_id: str) -> OCRResult:
        """Ana OCR işlemi – async job başlat ve bekle."""
        start_ms = int(time.time() * 1000)

        job_id = self._start_job(s3_bucket, s3_key)
        logger.info("textract_job_started", job_id=job_id, document_id=document_id)

        raw_blocks = self._wait_for_job(job_id)
        result = self._parse_blocks(raw_blocks, document_id)
        result.processing_time_ms = int(time.time() * 1000) - start_ms

        logger.info(
            "ocr_complete",
            document_id=document_id,
            pages=result.total_pages,
            confidence=result.overall_confidence,
            needs_review=len(result.pages_needing_review),
        )
        return result

    def _start_job(self, bucket: str, key: str) -> str:
        """Textract async job başlat (TABLES + FORMS özellikli)."""
        try:
            response = self._textract.start_document_analysis(
                DocumentLocation={"S3Object": {"Bucket": bucket, "Name": key}},
                FeatureTypes=["TABLES", "FORMS"],
            )
            return response["JobId"]
        except Exception as e:
            raise OCRFailureError(f"Textract job başlatılamadı: {e}")

    @retry(stop=stop_after_attempt(30), wait=wait_exponential(min=5, max=30))
    def _wait_for_job(self, job_id: str) -> list[dict]:
        """Job tamamlanana kadar poll et – tüm sayfaları topla."""
        all_blocks: list[dict] = []
        next_token = None

        while True:
            kwargs: dict = {"JobId": job_id}
            if next_token:
                kwargs["NextToken"] = next_token

            response = self._textract.get_document_analysis(**kwargs)
            status = response["JobStatus"]

            if status == "FAILED":
                raise OCRFailureError(f"Textract job başarısız: {response.get('StatusMessage')}")
            if status == "IN_PROGRESS":
                raise Exception("Job henüz tamamlanmadı")  # retry tetikler

            all_blocks.extend(response.get("Blocks", []))
            next_token = response.get("NextToken")
            if not next_token:
                break

        return all_blocks

    def _parse_blocks(self, blocks: list[dict], document_id: str) -> OCRResult:
        """Block listesini sayfa bazlı OCRResult'a dönüştür."""
        # Sayfalara göre grupla
        pages_text: dict[int, list[str]] = {}
        pages_confidence: dict[int, list[float]] = {}
        pages_low_conf: dict[int, list[dict]] = {}

        for block in blocks:
            if block["BlockType"] not in ("LINE", "WORD"):
                continue
            page = block.get("Page", 1)
            text = block.get("Text", "")
            confidence = block.get("Confidence", 0.0)

            if block["BlockType"] == "LINE":
                pages_text.setdefault(page, []).append(text)

            pages_confidence.setdefault(page, []).append(confidence)

            if confidence < LOW_CONFIDENCE and block["BlockType"] == "WORD":
                pages_low_conf.setdefault(page, []).append({
                    "text": text,
                    "confidence": round(confidence, 2),
                    "bbox": block.get("Geometry", {}).get("BoundingBox", {}),
                })

        # Tabloları çıkar
        tables = self._extract_tables(blocks)

        # Sayfa sonuçları
        page_results: list[PageOCRResult] = []
        all_confidences: list[float] = []

        for page_num in sorted(pages_text.keys()):
            page_text = "\n".join(pages_text.get(page_num, []))
            confs = pages_confidence.get(page_num, [100.0])
            avg_conf = sum(confs) / len(confs)
            min_conf = min(confs)
            all_confidences.extend(confs)

            review_status, review_reason = self._determine_review_status(
                avg_conf, min_conf, pages_low_conf.get(page_num, [])
            )

            page_tables = [t for t in tables if t.page_number == page_num]

            page_results.append(PageOCRResult(
                page_number=page_num,
                text=page_text,
                avg_confidence=round(avg_conf, 2),
                min_confidence=round(min_conf, 2),
                low_confidence_blocks=pages_low_conf.get(page_num, []),
                tables=page_tables,
                review_status=review_status,
                review_reason=review_reason,
                word_count=len(page_text.split()),
            ))

        pages_needing_review = [p.page_number for p in page_results if p.needs_review]
        overall_conf = sum(all_confidences) / len(all_confidences) if all_confidences else 0.0
        full_text = "\n\n".join(
            f"[SAYFA {p.page_number}]\n{p.text}" for p in page_results
        )

        # Manuel inceleme gereken sayfalar için marker ekle
        for p in page_results:
            if p.needs_review:
                marker = (
                    f"\n⚠️ [MANUEL İNCELEME GEREKLİ – Sayfa {p.page_number}: "
                    f"Güven: %{p.avg_confidence:.0f} – {p.review_reason}]\n"
                )
                full_text = full_text.replace(
                    f"[SAYFA {p.page_number}]",
                    f"[SAYFA {p.page_number}]{marker}"
                )

        return OCRResult(
            document_id=document_id,
            total_pages=len(page_results),
            full_text=full_text,
            pages=page_results,
            tables=[t.to_json() for t in tables],
            pages_needing_review=pages_needing_review,
            overall_confidence=round(overall_conf, 2),
        )

    def _determine_review_status(
        self,
        avg_confidence: float,
        min_confidence: float,
        low_conf_blocks: list[dict],
    ) -> tuple[PageReviewStatus, str | None]:
        """Sayfanın inceleme durumunu belirle."""
        if avg_confidence < CRITICAL_CONFIDENCE:
            return PageReviewStatus.UNREADABLE, "Ortalama güven çok düşük – okunamıyor"
        if min_confidence < CRITICAL_CONFIDENCE:
            return PageReviewStatus.CRITICAL_REVIEW, "Kritik düşük güvenli metin bloğu"
        if avg_confidence < LOW_CONFIDENCE:
            return PageReviewStatus.MANUAL_REVIEW, (
                f"Ortalama güven %{avg_confidence:.0f} – "
                "damgalı/el yazısı/bozuk tarama olabilir"
            )
        if len(low_conf_blocks) >= 5:
            return PageReviewStatus.MANUAL_REVIEW, (
                f"{len(low_conf_blocks)} düşük güvenli kelime – "
                "kısmi el yazısı veya mürekkep sorunu"
            )
        return PageReviewStatus.OK, None

    def _extract_tables(self, blocks: list[dict]) -> list[ExtractedTable]:
        """Textract TABLE bloklarını yapılandırılmış ExtractedTable'a dönüştür."""
        block_map = {b["Id"]: b for b in blocks}
        tables: list[ExtractedTable] = []

        for block in blocks:
            if block["BlockType"] != "TABLE":
                continue

            page = block.get("Page", 1)
            cells: list[TableCell] = []
            max_row = max_col = 0

            for rel in block.get("Relationships", []):
                if rel["Type"] != "CHILD":
                    continue
                for cell_id in rel["Ids"]:
                    cell_block = block_map.get(cell_id)
                    if not cell_block or cell_block["BlockType"] != "CELL":
                        continue

                    row = cell_block.get("RowIndex", 1) - 1
                    col = cell_block.get("ColumnIndex", 1) - 1
                    max_row = max(max_row, row + 1)
                    max_col = max(max_col, col + 1)

                    # Hücre metnini topla
                    cell_text_parts = []
                    cell_confidence = cell_block.get("Confidence", 100.0)

                    for child_rel in cell_block.get("Relationships", []):
                        if child_rel["Type"] != "CHILD":
                            continue
                        for word_id in child_rel["Ids"]:
                            word = block_map.get(word_id)
                            if word and word["BlockType"] == "WORD":
                                cell_text_parts.append(word.get("Text", ""))
                                cell_confidence = min(
                                    cell_confidence, word.get("Confidence", 100.0)
                                )

                    cells.append(TableCell(
                        row=row,
                        col=col,
                        text=" ".join(cell_text_parts),
                        confidence=round(cell_confidence, 2),
                        row_span=cell_block.get("RowSpan", 1),
                        col_span=cell_block.get("ColumnSpan", 1),
                    ))

            if cells:
                tables.append(ExtractedTable(
                    page_number=page,
                    rows=max_row,
                    cols=max_col,
                    cells=cells,
                ))

        return tables


ocr_service = OCRService()
