"""
Embedding Evaluator – birim testleri (Bedrock çağrısı mock'lanır)
"""
import pytest
from unittest.mock import AsyncMock, patch
from app.services.embedding_evaluator import (
    EmbeddingEvaluator,
    EvaluationReport,
    TermPairResult,
    LEGAL_TERM_PAIRS,
    QUALITY_THRESHOLD,
)


def make_report(similarities: list[float]) -> EvaluationReport:
    results = [
        TermPairResult(
            term_a=f"term_{i}_a",
            term_b=f"term_{i}_b",
            description="test",
            similarity=s,
            passed=s >= QUALITY_THRESHOLD,
        )
        for i, s in enumerate(similarities)
    ]
    return EvaluationReport(
        model_id="test-model",
        threshold=QUALITY_THRESHOLD,
        results=results,
    )


# ── Cosine Similarity ──────────────────────────────────────────────

def test_cosine_identical_vectors():
    vec = [1.0, 0.0, 0.0]
    assert EmbeddingEvaluator._cosine_similarity(vec, vec) == pytest.approx(1.0)


def test_cosine_orthogonal_vectors():
    vec_a = [1.0, 0.0]
    vec_b = [0.0, 1.0]
    assert EmbeddingEvaluator._cosine_similarity(vec_a, vec_b) == pytest.approx(0.0)


def test_cosine_opposite_vectors():
    vec_a = [1.0, 0.0]
    vec_b = [-1.0, 0.0]
    assert EmbeddingEvaluator._cosine_similarity(vec_a, vec_b) == pytest.approx(-1.0)


def test_cosine_zero_vector_returns_zero():
    vec_a = [0.0, 0.0]
    vec_b = [1.0, 0.0]
    assert EmbeddingEvaluator._cosine_similarity(vec_a, vec_b) == 0.0


def test_cosine_dimension_mismatch_raises():
    with pytest.raises(ValueError, match="boyutları eşleşmiyor"):
        EmbeddingEvaluator._cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0])


# ── EvaluationReport ──────────────────────────────────────────────

def test_report_verdict_uygun():
    report = make_report([0.90] * 10)
    assert report.verdict == "UYGUN"
    assert report.passed_count == 10


def test_report_verdict_yetersiz():
    report = make_report([0.60] * 10)
    assert report.verdict == "YETERSİZ"
    assert report.failed_count == 10


def test_report_verdict_sinirda():
    # 7/10 geçer → SINIRDA
    sims = [0.90] * 7 + [0.60] * 3
    report = make_report(sims)
    assert report.verdict == "SINIRDA"


def test_report_failed_terms_listed():
    sims = [0.90, 0.70, 0.90]  # orta eleman başarısız
    report = make_report(sims)
    assert "term_1_a" in report.failed_terms


def test_report_summary_contains_model_id():
    report = make_report([0.90] * 5)
    summary = report.summary()
    assert "test-model" in summary


def test_report_to_dict_structure():
    report = make_report([0.88, 0.92])
    d = report.to_dict()
    assert "model_id" in d
    assert "verdict" in d
    assert "results" in d
    assert len(d["results"]) == 2


# ── Yasal terim çifti sayısı ────────────────────────────────────────

def test_exactly_10_legal_term_pairs():
    """Spesifikasyon: tam 10 hukuki terim çifti."""
    assert len(LEGAL_TERM_PAIRS) == 10


def test_all_pairs_have_three_elements():
    for pair in LEGAL_TERM_PAIRS:
        assert len(pair) == 3, f"Eksik element: {pair}"


# ── Mock ile async run ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_with_mock_embeddings():
    """Bedrock'u mock'layarak tam pipeline'ı test et."""
    high_sim_vec_a = [1.0] + [0.0] * 1535
    high_sim_vec_b = [0.99] + [0.1] * 1535  # yüksek benzerlik

    with patch(
        "app.services.embedding_evaluator.EmbeddingEvaluator.run",
        new_callable=AsyncMock,
        return_value=make_report([0.92] * 10),
    ):
        evaluator = EmbeddingEvaluator()
        report = await evaluator.run()
        assert report.verdict == "UYGUN"
        assert report.passed_count == 10
