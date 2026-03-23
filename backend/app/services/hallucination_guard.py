"""
Hallucination Guard — 3-Aşamalı Doğrulama Sistemi

Aşama 1: Pre-generation filtre
  → Confidence < 0.7 olan chunk'ları context'ten çıkar

Aşama 2: Post-generation cümle bazlı claim kontrolü
  → Her somut iddia (tarih, tutar, madde no, karar no) chunk'larda var mı?
  → Yoksa cümleyi "Bu bilgi dosya kapsamında tespit edilememiştir" ile değiştir

Aşama 3: Genel jaccard + karar numarası doğrulaması (önceki guard davranışı)
"""
import re
from dataclasses import dataclass, field
from typing import Literal

from app.core.config import settings
from app.core.logging import get_logger
from app.services.embedding_service import RetrievedChunk

logger = get_logger(__name__)

# ── Güven eşikleri ────────────────────────────────────────────────
CHUNK_MIN_CONFIDENCE = 0.70   # Bu altındaki chunk context'e alınmaz
JACCARD_THRESHOLD    = 0.80   # Genel örtüşme eşiği
NOT_FOUND_SENTENCE   = "Bu bilgi dosya kapsamında tespit edilememiştir."

# ── Hukuki somut iddia örüntüleri ─────────────────────────────────
CLAIM_PATTERNS: dict[str, re.Pattern] = {
    # TBK m.112, TTK madde 14 vb.
    "article_number": re.compile(
        r"\b(TBK|TTK|HMK|TMK|TCK|İK|KVKK)\s*(?:m\.|madde)?\s*(\d+(?:[/.-]\d+)?)",
        re.IGNORECASE,
    ),
    # Yargıtay karar: E.2023/1234 veya K.2023/5678
    "case_number": re.compile(
        r"\b([EeKk])\.\s*(\d{4}/\d+)",
    ),
    # Para tutarları: 50.000 TL, 1.500,00 ₺
    "amount": re.compile(
        r"\b(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?)\s*(?:TL|lira|₺)\b",
        re.IGNORECASE,
    ),
    # Tarihler: 15.03.2022, 2022/03/15
    "date": re.compile(
        r"\b(\d{1,2}[./\-]\d{1,2}[./\-]\d{4})\b",
    ),
    # Yüzdeler: %50, % 25
    "percentage": re.compile(
        r"%\s*(\d+(?:[.,]\d+)?)\b",
    ),
    # Yıl aralığı: 2019, 2023 (hukuki metinlerde kritik)
    "year": re.compile(
        r"\b(20\d{2})\b",
    ),
}


@dataclass
class ClaimVerification:
    claim_type: str
    claim_value: str
    sentence: str
    found_in_chunks: bool
    source_chunk_id: str | None = None


@dataclass
class GuardResult:
    passed: bool
    confidence_score: float
    hallucination_flag: bool
    # Orijinal yanıt
    original_answer: str
    # Doğrulanmış yanıt (sahte iddialar değiştirilmiş)
    cleaned_answer: str
    flagged_claims: list[str] = field(default_factory=list)
    unverified_case_numbers: list[str] = field(default_factory=list)
    replaced_sentences: list[str] = field(default_factory=list)
    claim_checks: list[ClaimVerification] = field(default_factory=list)
    chunks_filtered: int = 0
    verification_details: dict = field(default_factory=dict)


class HallucinationGuard:
    def __init__(self, sensitivity: str | None = None):
        self.sensitivity = sensitivity or settings.HALLUCINATION_SENSITIVITY
        self.jaccard_threshold = JACCARD_THRESHOLD
        self.chunk_min_confidence = CHUNK_MIN_CONFIDENCE

    # ── Aşama 1: Pre-generation chunk filtresi ─────────────────────

    def filter_chunks(
        self,
        chunks: list[RetrievedChunk],
    ) -> tuple[list[RetrievedChunk], int]:
        """
        Confidence < 0.7 olan chunk'ları context'ten çıkar.
        Returns: (filtered_chunks, removed_count)
        """
        before = len(chunks)
        filtered = [c for c in chunks if c.similarity_score >= self.chunk_min_confidence]
        removed = before - len(filtered)

        if removed > 0:
            logger.info(
                "chunks_filtered_by_confidence",
                removed=removed,
                threshold=self.chunk_min_confidence,
            )

        return filtered, removed

    # ── Aşama 2: Post-generation cümle doğrulaması ─────────────────

    def clean_answer(
        self,
        answer: str,
        source_chunks: list[RetrievedChunk],
    ) -> tuple[str, list[str], list[ClaimVerification]]:
        """
        Yanıttaki her cümleyi tara:
        - Somut iddialar çıkar (tarih, tutar, madde no, karar no)
        - Her iddia chunk'larda var mı?
        - Yoksa cümleyi NOT_FOUND_SENTENCE ile değiştir

        Returns: (cleaned_answer, replaced_sentences, claim_checks)
        """
        source_text = "\n".join(c.chunk_text for c in source_chunks)
        sentences = self._split_sentences(answer)
        cleaned_parts: list[str] = []
        replaced: list[str] = []
        all_checks: list[ClaimVerification] = []

        for sentence in sentences:
            claims = self._extract_claims(sentence)

            if not claims:
                # Somut iddia yok → cümleyi koru
                cleaned_parts.append(sentence)
                continue

            # Her iddia için doğrulama yap
            checks = [
                self._verify_claim(claim_type, claim_val, sentence, source_chunks)
                for claim_type, claim_val in claims
            ]
            all_checks.extend(checks)

            unverified = [c for c in checks if not c.found_in_chunks]

            if unverified:
                # En az bir iddia doğrulanamadı → cümleyi değiştir
                replaced.append(sentence)
                cleaned_parts.append(NOT_FOUND_SENTENCE)
                logger.debug(
                    "sentence_replaced",
                    sentence=sentence[:80],
                    unverified_count=len(unverified),
                    claim_types=[c.claim_type for c in unverified],
                )
            else:
                cleaned_parts.append(sentence)

        cleaned_answer = " ".join(cleaned_parts)
        return cleaned_answer, replaced, all_checks

    # ── Aşama 3: Genel Jaccard + Karar Numarası ────────────────────

    async def verify(
        self,
        answer: str,
        source_chunks: list[RetrievedChunk],
        template_sensitivity: str | None = None,
    ) -> GuardResult:
        """
        Tam 3-aşamalı doğrulama.
        RAGService tarafından her yanıt üretiminin ardından çağrılır.
        """
        effective_sensitivity = template_sensitivity or self.sensitivity

        # Aşama 1: Chunk'lar zaten filter_chunks() ile filtrelenmiş olmalı
        # Burada sadece dokümante ediyoruz
        source_text = " ".join(c.chunk_text for c in source_chunks)

        # Aşama 2: Cümle bazlı claim temizleme
        cleaned_answer, replaced_sentences, claim_checks = self.clean_answer(
            answer, source_chunks
        )

        # Aşama 3a: Genel Jaccard
        overlap_score = self._compute_jaccard(cleaned_answer, source_text)

        # Aşama 3b: Karar numarası doğrulaması (critical mod)
        unverified_cases: list[str] = []
        if effective_sensitivity == "critical":
            unverified_cases = self._check_case_numbers(cleaned_answer, source_chunks)

        # Sonuç karar
        has_replacements   = len(replaced_sentences) > 0
        has_unverified_cases = len(unverified_cases) > 0
        low_jaccard        = overlap_score < self.jaccard_threshold

        flagged = has_replacements or has_unverified_cases or low_jaccard
        confidence = round(overlap_score, 3)

        flagged_claims: list[str] = []
        if has_unverified_cases:
            flagged_claims += [f"Doğrulanamayan karar: {c}" for c in unverified_cases]
        if has_replacements:
            flagged_claims += [f"Değiştirilen iddia: {s[:60]}…" for s in replaced_sentences[:3]]

        logger.info(
            "hallucination_guard_complete",
            jaccard=overlap_score,
            replaced_sentences=len(replaced_sentences),
            unverified_cases=len(unverified_cases),
            flagged=flagged,
            sensitivity=effective_sensitivity,
        )

        return GuardResult(
            passed=not flagged,
            confidence_score=confidence,
            hallucination_flag=flagged,
            original_answer=answer,
            cleaned_answer=cleaned_answer,
            flagged_claims=flagged_claims,
            unverified_case_numbers=unverified_cases,
            replaced_sentences=replaced_sentences,
            claim_checks=claim_checks,
            verification_details={
                "jaccard_score": overlap_score,
                "jaccard_threshold": self.jaccard_threshold,
                "sensitivity": effective_sensitivity,
                "source_chunk_count": len(source_chunks),
                "replaced_sentence_count": len(replaced_sentences),
                "total_claims_checked": len(claim_checks),
                "failed_claims": len([c for c in claim_checks if not c.found_in_chunks]),
            },
        )

    # ── Yardımcı metodlar ───────────────────────────────────────────

    def _extract_claims(
        self, sentence: str
    ) -> list[tuple[str, str]]:
        """Cümledeki somut iddiaları çıkar: [(type, value), ...]"""
        claims: list[tuple[str, str]] = []
        for claim_type, pattern in CLAIM_PATTERNS.items():
            for match in pattern.finditer(sentence):
                claims.append((claim_type, match.group(0)))
        return claims

    def _verify_claim(
        self,
        claim_type: str,
        claim_value: str,
        sentence: str,
        source_chunks: list[RetrievedChunk],
    ) -> ClaimVerification:
        """İddiayı kaynak chunk'larda ara."""
        # Yıl ve yüzde: çok yaygın, daha esnek kontrol
        if claim_type in ("year", "percentage"):
            found = any(claim_value in c.chunk_text for c in source_chunks)
            return ClaimVerification(
                claim_type=claim_type,
                claim_value=claim_value,
                sentence=sentence[:100],
                found_in_chunks=found,
                source_chunk_id=next(
                    (c.chunk_id for c in source_chunks if claim_value in c.chunk_text),
                    None,
                ),
            )

        # Diğer claim'ler: tam eşleşme gerekli
        for chunk in source_chunks:
            if claim_value.lower() in chunk.chunk_text.lower():
                return ClaimVerification(
                    claim_type=claim_type,
                    claim_value=claim_value,
                    sentence=sentence[:100],
                    found_in_chunks=True,
                    source_chunk_id=chunk.chunk_id,
                )

        return ClaimVerification(
            claim_type=claim_type,
            claim_value=claim_value,
            sentence=sentence[:100],
            found_in_chunks=False,
        )

    def _split_sentences(self, text: str) -> list[str]:
        """Metni cümlelere böl. Hukuki liste formatlarını koru."""
        # Madde işaretlerini ve liste öğelerini koruyarak böl
        parts = re.split(r"(?<=[.!?])\s+(?=[A-ZÇĞİÖŞÜa-zçğışöüA-Z])", text)
        result: list[str] = []
        for part in parts:
            stripped = part.strip()
            if stripped:
                result.append(stripped)
        return result if result else [text]

    def _compute_jaccard(self, text_a: str, text_b: str) -> float:
        tokens_a = set(text_a.lower().split())
        tokens_b = set(text_b.lower().split())
        if not tokens_a or not tokens_b:
            return 0.0
        return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)

    def _check_case_numbers(
        self,
        answer: str,
        source_chunks: list[RetrievedChunk],
    ) -> list[str]:
        """Critical mod: Yanıttaki karar numaralarını kaynaklarda doğrula."""
        case_pattern = re.compile(r"\b[EeKk]\.\s*\d{4}/\d+")
        found_in_answer = case_pattern.findall(answer)
        source_text = " ".join(c.chunk_text for c in source_chunks)
        return [c for c in found_in_answer if c not in source_text]


hallucination_guard = HallucinationGuard()
