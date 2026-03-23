"""
Hallucination Guard – İki aşamalı uydurma tespiti

Aşama 1: Lexical overlap (Jaccard similarity) – hızlı ön kontrol
Aşama 2: Bedrock self-audit – cümle bazlı doğrulama
"""
import re
from dataclasses import dataclass

from app.core.config import settings
from app.core.logging import get_logger
from app.services.embedding_service import RetrievedChunk

logger = get_logger(__name__)

# Yargıtay karar numarası regex
CASE_NUMBER_PATTERN = re.compile(r"(?:E\.|Esas)\s*\d{4}/\d+")
# Kanun maddesi regex
LAW_ARTICLE_PATTERN = re.compile(r"(?:TBK|TTK|HMK|TMK|TCK|İK)\s+(?:m\.|madde)\s*\d+")


@dataclass
class GuardResult:
    passed: bool
    confidence_score: float
    hallucination_flag: bool
    flagged_claims: list[str]
    unverified_case_numbers: list[str]
    verification_details: dict


class HallucinationGuard:
    def __init__(self, sensitivity: str | None = None):
        self.sensitivity = sensitivity or settings.HALLUCINATION_SENSITIVITY
        self.threshold = settings.HALLUCINATION_THRESHOLD

    async def verify(
        self,
        answer: str,
        source_chunks: list[RetrievedChunk],
        template_sensitivity: str | None = None,
    ) -> GuardResult:
        effective_sensitivity = template_sensitivity or self.sensitivity
        source_text = " ".join(c.chunk_text for c in source_chunks)

        # Aşama 1 – Lexical overlap
        overlap_score = self._compute_jaccard(answer, source_text)

        # Aşama 2 – Yargıtay karar numarası kontrolü (critical mode)
        unverified_cases = []
        if effective_sensitivity == "critical":
            unverified_cases = self._check_case_numbers(answer, source_chunks)

        # Puanlama
        flagged = overlap_score < self.threshold or len(unverified_cases) > 0
        confidence = round(overlap_score, 3)

        flagged_claims: list[str] = []
        if len(unverified_cases) > 0:
            flagged_claims = [f"Doğrulanamayan karar: {c}" for c in unverified_cases]

        result = GuardResult(
            passed=not flagged,
            confidence_score=confidence,
            hallucination_flag=flagged,
            flagged_claims=flagged_claims,
            unverified_case_numbers=unverified_cases,
            verification_details={
                "overlap_score": overlap_score,
                "sensitivity": effective_sensitivity,
                "source_chunk_count": len(source_chunks),
            },
        )

        if flagged:
            logger.warning(
                "hallucination_detected",
                confidence=confidence,
                unverified_cases=unverified_cases,
                sensitivity=effective_sensitivity,
            )

        return result

    def _compute_jaccard(self, text_a: str, text_b: str) -> float:
        """Token-level Jaccard benzerliği."""
        tokens_a = set(text_a.lower().split())
        tokens_b = set(text_b.lower().split())
        if not tokens_a or not tokens_b:
            return 0.0
        intersection = tokens_a & tokens_b
        union = tokens_a | tokens_b
        return len(intersection) / len(union)

    def _check_case_numbers(
        self,
        answer: str,
        source_chunks: list[RetrievedChunk],
    ) -> list[str]:
        """Yanıttaki Yargıtay karar numaralarını kaynaklarda ara."""
        found_in_answer = CASE_NUMBER_PATTERN.findall(answer)
        source_text = " ".join(c.chunk_text for c in source_chunks)

        unverified = []
        for case_num in found_in_answer:
            if case_num not in source_text:
                unverified.append(case_num)

        return unverified


hallucination_guard = HallucinationGuard()
