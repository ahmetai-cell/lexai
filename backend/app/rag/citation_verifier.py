"""
Citation Verifier — [Sayfa: X] atıflarını otomatik doğrular

Akış:
  1. Yanıttaki tüm [Kaynak N: ..., Sayfa X] atıflarını parse et
  2. O sayfaya ait chunk'ı retrieved listesinden bul
  3. İddia edilen içeriğin o chunk'ta gerçekten geçip geçmediğini kontrol et
  4. Geçmiyorsa → "ATIF HATASI — Doğrulanamadı" uyarısı ekle
  5. Her hata audit log'a yazılır
"""
import re
from dataclasses import dataclass, field

from app.core.logging import get_logger
from app.services.embedding_service import RetrievedChunk

logger = get_logger(__name__)

# [Kaynak 1: Sözleşme.pdf, Sayfa 5]
CITATION_PATTERN = re.compile(
    r"\[Kaynak\s+(\d+)(?::\s*([^\],]+?))?(?:,\s*Sayfa\s*(\d+))?\]",
    re.IGNORECASE,
)

# Minimum token örtüşme oranı – atfın gerçek olduğunu kabul etmek için
MIN_OVERLAP_RATIO = 0.15

VERIFICATION_WARNING = "⚠️ **[ATIF HATASI — Doğrulanamadı: Kaynak {ref}]**"
AUDIT_EVENT = "citation_verification_failed"


@dataclass
class CitationCheckResult:
    ref_number: str
    page_claimed: int | None
    chunk_id: str | None
    verified: bool
    overlap_ratio: float
    warning_inserted: bool = False
    reason: str = ""


@dataclass
class VerificationReport:
    original_answer: str
    verified_answer: str
    checks: list[CitationCheckResult] = field(default_factory=list)
    error_count: int = 0
    total_citations: int = 0

    @property
    def has_errors(self) -> bool:
        return self.error_count > 0

    def audit_entries(self) -> list[dict]:
        """Audit log'a yazılacak kayıtlar."""
        return [
            {
                "event": AUDIT_EVENT,
                "ref_number": c.ref_number,
                "page_claimed": c.page_claimed,
                "chunk_id": c.chunk_id,
                "overlap_ratio": round(c.overlap_ratio, 3),
                "reason": c.reason,
            }
            for c in self.checks
            if not c.verified
        ]


class CitationVerifier:
    def __init__(self, min_overlap: float = MIN_OVERLAP_RATIO):
        self.min_overlap = min_overlap

    def verify(
        self,
        answer: str,
        retrieved_chunks: list[RetrievedChunk],
    ) -> VerificationReport:
        """
        Yanıttaki tüm kaynak atıflarını doğrula.
        Hatalı atıflara uyarı enjekte et.
        """
        # Chunk'ları index'le: (ref_number → chunk), (page → chunk)
        ref_map: dict[str, RetrievedChunk] = {
            str(i + 1): c for i, c in enumerate(retrieved_chunks)
        }
        page_map: dict[int, list[RetrievedChunk]] = {}
        for chunk in retrieved_chunks:
            if chunk.page_number:
                page_map.setdefault(chunk.page_number, []).append(chunk)

        citations = list(CITATION_PATTERN.finditer(answer))
        checks: list[CitationCheckResult] = []
        error_count = 0

        # Yanıt üzerinde çalışmak için kopyasını al
        verified_answer = answer

        # Tersine doğrula (string pozisyonları kaymasın diye sondan başa)
        for match in reversed(citations):
            ref_num    = match.group(1)
            page_str   = match.group(3)
            page_num   = int(page_str) if page_str else None
            ref_text   = match.group(0)

            # Context cümlesini bul (atıfın hemen öncesi)
            context_sentence = self._extract_context_sentence(answer, match.start())

            # Doğrulamayı yap
            result = self._verify_single(
                ref_num=ref_num,
                page_num=page_num,
                context_sentence=context_sentence,
                ref_map=ref_map,
                page_map=page_map,
            )
            checks.append(result)

            if not result.verified:
                error_count += 1
                # Uyarıyı atıf metninin yanına enjekte et
                warning = VERIFICATION_WARNING.format(ref=ref_num)
                verified_answer = (
                    verified_answer[: match.end()]
                    + f" {warning}"
                    + verified_answer[match.end() :]
                )
                result.warning_inserted = True
                logger.warning(
                    "citation_verification_failed",
                    ref=ref_num,
                    page=page_num,
                    overlap=result.overlap_ratio,
                    reason=result.reason,
                )

        return VerificationReport(
            original_answer=answer,
            verified_answer=verified_answer,
            checks=checks,
            error_count=error_count,
            total_citations=len(citations),
        )

    def _verify_single(
        self,
        ref_num: str,
        page_num: int | None,
        context_sentence: str,
        ref_map: dict[str, RetrievedChunk],
        page_map: dict[int, list[RetrievedChunk]],
    ) -> CitationCheckResult:
        """Tek bir atıfı doğrula."""

        # Önce ref_number ile bul
        chunk = ref_map.get(ref_num)

        # Sonra sayfa numarası ile dene
        if not chunk and page_num:
            page_chunks = page_map.get(page_num, [])
            if page_chunks:
                # En yüksek similarity'li chunk'ı seç
                chunk = max(page_chunks, key=lambda c: c.similarity_score)

        if not chunk:
            return CitationCheckResult(
                ref_number=ref_num,
                page_claimed=page_num,
                chunk_id=None,
                verified=False,
                overlap_ratio=0.0,
                reason="Atıf numarasına karşılık gelen kaynak bulunamadı",
            )

        # Sayfa numarası uyuşuyor mu?
        if page_num and chunk.page_number and chunk.page_number != page_num:
            return CitationCheckResult(
                ref_number=ref_num,
                page_claimed=page_num,
                chunk_id=chunk.chunk_id,
                verified=False,
                overlap_ratio=0.0,
                reason=f"Sayfa uyuşmazlığı: iddia={page_num}, gerçek={chunk.page_number}",
            )

        # İçerik örtüşmesini kontrol et
        overlap = self._compute_overlap(context_sentence, chunk.chunk_text)

        verified = overlap >= self.min_overlap
        return CitationCheckResult(
            ref_number=ref_num,
            page_claimed=page_num,
            chunk_id=chunk.chunk_id,
            verified=verified,
            overlap_ratio=overlap,
            reason="" if verified else f"İçerik örtüşmesi düşük: {overlap:.2%}",
        )

    def _extract_context_sentence(self, text: str, citation_pos: int) -> str:
        """Atıfın bulunduğu veya önceki cümleyi çıkar."""
        start = max(0, citation_pos - 300)
        fragment = text[start:citation_pos]

        # Son cümle sınırından itibaren al
        for sep in (". ", ".\n", "! ", "? "):
            idx = fragment.rfind(sep)
            if idx != -1:
                return fragment[idx + 2:].strip()

        return fragment.strip()

    def _compute_overlap(self, sentence: str, chunk_text: str) -> float:
        """
        Token-level Jaccard benzerliği.
        Türkçe için 3+ karakter kelimeler.
        """
        tokens_s = {w.lower() for w in sentence.split() if len(w) >= 3}
        tokens_c = {w.lower() for w in chunk_text.split() if len(w) >= 3}

        if not tokens_s:
            return 0.0

        intersection = tokens_s & tokens_c
        return len(intersection) / len(tokens_s)


citation_verifier = CitationVerifier()
