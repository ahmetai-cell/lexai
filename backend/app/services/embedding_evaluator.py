"""
Embedding Model Kalite Değerlendirici

Türkçe hukuki terimler için semantic similarity testi.
Skor < 0.85 ise model yetersiz sayılır.

Kullanım:
    evaluator = EmbeddingEvaluator()
    report = await evaluator.run()
    print(report.summary())
"""
import math
from dataclasses import dataclass, field
from typing import Literal

from app.core.logging import get_logger

logger = get_logger(__name__)

# Eşik değeri – altında model yetersiz
QUALITY_THRESHOLD = 0.85

# ── 10 Türkçe Hukuki Terim Çifti ──────────────────────────────────────────
# (birincil_terim, semantik_yakın_terim, açıklama)
# Bu çiftlerin cosine benzerliği 0.85+ olmalı
LEGAL_TERM_PAIRS: list[tuple[str, str, str]] = [
    (
        "temerrüt",
        "borca aykırılık",
        "TBK 117–126: Borçlunun ifayı gecikmesi",
    ),
    (
        "hak düşürücü süre",
        "zamanaşımı",
        "Hakkın kullanılması için belirli süre – dava açılabilirlik",
    ),
    (
        "müstakil",
        "bağımsız",
        "Hukuki bağımsızlık – parça/bütün ilişkisi",
    ),
    (
        "menfi zarar",
        "sözleşmenin kurulmamasından doğan zarar",
        "TBK 36: Culpa in contrahendo",
    ),
    (
        "eda davası",
        "alacak davası",
        "HMK: Borçlunun bir şey yapması talep edilen dava",
    ),
    (
        "ihtiyati tedbir",
        "geçici hukuki koruma",
        "HMK 389: Dava süresince mevcut durumu koruma",
    ),
    (
        "fer'i müdahil",
        "davaya katılan üçüncü kişi",
        "HMK 66: Yan taraf olarak katılma",
    ),
    (
        "takas",
        "mahsup",
        "TBK 139: Karşılıklı borçların netleştirilmesi",
    ),
    (
        "istihkak davası",
        "mülkiyet iadesi",
        "TMK: Mülkiyetin kime ait olduğu davası",
    ),
    (
        "rücu hakkı",
        "başkasının borcunu ödeyen kişinin talep hakkı",
        "TBK 78: Halefiyet",
    ),
]


@dataclass
class TermPairResult:
    term_a: str
    term_b: str
    description: str
    similarity: float
    passed: bool
    threshold: float = QUALITY_THRESHOLD

    def status_icon(self) -> str:
        return "✅" if self.passed else "❌"


@dataclass
class EvaluationReport:
    model_id: str
    threshold: float
    results: list[TermPairResult]
    overall_score: float = 0.0
    passed_count: int = 0
    failed_count: int = 0
    verdict: Literal["UYGUN", "YETERSİZ", "SINIRDA"] = "YETERSİZ"
    failed_terms: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.passed_count = sum(1 for r in self.results if r.passed)
        self.failed_count = len(self.results) - self.passed_count
        self.overall_score = (
            sum(r.similarity for r in self.results) / len(self.results)
            if self.results else 0.0
        )
        self.failed_terms = [r.term_a for r in self.results if not r.passed]

        pass_rate = self.passed_count / len(self.results) if self.results else 0
        if pass_rate >= 0.9 and self.overall_score >= self.threshold:
            self.verdict = "UYGUN"
        elif pass_rate >= 0.7:
            self.verdict = "SINIRDA"
        else:
            self.verdict = "YETERSİZ"

    def summary(self) -> str:
        lines = [
            "═" * 60,
            f"  EMBEDDING MODEL KALİTE RAPORU",
            f"  Model: {self.model_id}",
            f"  Eşik: {self.threshold} | Genel Skor: {self.overall_score:.3f}",
            "═" * 60,
            "",
        ]
        for r in self.results:
            lines.append(
                f"  {r.status_icon()}  '{r.term_a}' ↔ '{r.term_b}'"
                f"\n      Benzerlik: {r.similarity:.3f}  |  {r.description}"
            )

        lines += [
            "",
            "─" * 60,
            f"  Geçen: {self.passed_count}/{len(self.results)}",
            f"  Genel Ortalama: {self.overall_score:.3f}",
            f"  SONUÇ: {'✅ MODEL UYGUN' if self.verdict == 'UYGUN' else '❌ MODEL YETERSİZ' if self.verdict == 'YETERSİZ' else '⚠️ SINIRDA – Manuel İnceleme'}",
        ]
        if self.failed_terms:
            lines.append(f"  Başarısız Terimler: {', '.join(self.failed_terms)}")
        lines.append("═" * 60)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "model_id": self.model_id,
            "threshold": self.threshold,
            "overall_score": round(self.overall_score, 4),
            "passed": self.passed_count,
            "failed": self.failed_count,
            "verdict": self.verdict,
            "failed_terms": self.failed_terms,
            "results": [
                {
                    "term_a": r.term_a,
                    "term_b": r.term_b,
                    "similarity": round(r.similarity, 4),
                    "passed": r.passed,
                    "description": r.description,
                }
                for r in self.results
            ],
        }


class EmbeddingEvaluator:
    """
    Embedding modelini Türkçe hukuki terimler üzerinde değerlendirir.
    Bağımlılık: EmbeddingService (Bedrock Titan veya alternatif).
    """

    def __init__(self, threshold: float = QUALITY_THRESHOLD):
        self.threshold = threshold

    async def run(
        self,
        term_pairs: list[tuple[str, str, str]] | None = None,
        model_id: str | None = None,
    ) -> EvaluationReport:
        """
        10 terim çiftini embed et, cosine benzerliği hesapla, rapor üret.
        """
        from app.services.embedding_service import embedding_service
        from app.core.config import settings

        pairs = term_pairs or LEGAL_TERM_PAIRS
        used_model = model_id or settings.BEDROCK_EMBEDDING_MODEL_ID

        logger.info("embedding_eval_start", model=used_model, pair_count=len(pairs))

        results: list[TermPairResult] = []
        for term_a, term_b, description in pairs:
            try:
                vec_a = await embedding_service.embed_text(term_a)
                vec_b = await embedding_service.embed_text(term_b)
                similarity = self._cosine_similarity(vec_a, vec_b)
                passed = similarity >= self.threshold
                results.append(TermPairResult(
                    term_a=term_a,
                    term_b=term_b,
                    description=description,
                    similarity=similarity,
                    passed=passed,
                    threshold=self.threshold,
                ))
                logger.info(
                    "pair_evaluated",
                    term_a=term_a,
                    term_b=term_b,
                    similarity=round(similarity, 4),
                    passed=passed,
                )
            except Exception as e:
                logger.error("pair_eval_error", term_a=term_a, error=str(e))
                results.append(TermPairResult(
                    term_a=term_a,
                    term_b=term_b,
                    description=description,
                    similarity=0.0,
                    passed=False,
                    threshold=self.threshold,
                ))

        report = EvaluationReport(
            model_id=used_model,
            threshold=self.threshold,
            results=results,
        )
        logger.info(
            "embedding_eval_complete",
            verdict=report.verdict,
            score=report.overall_score,
        )
        return report

    @staticmethod
    def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
        """İki vektör arasındaki cosine benzerliği."""
        if len(vec_a) != len(vec_b):
            raise ValueError(f"Vektör boyutları eşleşmiyor: {len(vec_a)} vs {len(vec_b)}")

        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))

        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    async def compare_models(
        self,
        model_ids: list[str],
    ) -> dict[str, EvaluationReport]:
        """Birden fazla modeli karşılaştır – en iyi olanı seç."""
        reports: dict[str, EvaluationReport] = {}
        for model_id in model_ids:
            report = await self.run(model_id=model_id)
            reports[model_id] = report
        return reports


embedding_evaluator = EmbeddingEvaluator()
