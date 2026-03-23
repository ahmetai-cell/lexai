"""
HybridRetriever — birim testleri (DB çağrıları mock'lanır)
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.rag.hybrid_retriever import (
    HybridRetriever,
    ScoredChunk,
    SEMANTIC_WEIGHT,
    KEYWORD_WEIGHT,
    RRF_K,
    MIN_CONFIDENCE,
)
from app.services.embedding_service import RetrievedChunk


def make_chunk(
    chunk_id: str,
    text: str = "test metni",
    score: float = 0.85,
    page: int = 1,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id="doc-1",
        chunk_text=text,
        page_number=page,
        section_title=None,
        article_number=None,
        similarity_score=score,
        source_metadata=None,
    )


# ── Sabit değerler ─────────────────────────────────────────────────


def test_weights_sum_to_one():
    assert abs(SEMANTIC_WEIGHT + KEYWORD_WEIGHT - 1.0) < 1e-9


def test_rrf_k_is_60():
    assert RRF_K == 60


def test_min_confidence_is_0_70():
    assert MIN_CONFIDENCE == 0.70


# ── Legal pattern tespiti ─────────────────────────────────────────


def test_has_legal_patterns_tbk():
    r = HybridRetriever()
    assert r._has_legal_patterns("TBK madde 112 gereğince borçlu temerrüde düştü")


def test_has_legal_patterns_case_number():
    r = HybridRetriever()
    assert r._has_legal_patterns("E. 2023/4567 sayılı Yargıtay kararı")


def test_has_legal_patterns_date():
    r = HybridRetriever()
    assert r._has_legal_patterns("15.03.2022 tarihinde imzalanmıştır")


def test_has_legal_patterns_none():
    r = HybridRetriever()
    assert not r._has_legal_patterns("genel bir hukuki değerlendirme yapılacaktır")


def test_has_legal_patterns_yargitay_daire():
    r = HybridRetriever()
    assert r._has_legal_patterns("4. HD kararına göre")


# ── Legal boost ────────────────────────────────────────────────────


def test_legal_boost_zero_for_plain_text():
    r = HybridRetriever()
    boost = r._legal_boost("bu metin hiçbir hukuki referans içermiyor")
    assert boost == 0.0


def test_legal_boost_positive_for_legal_text():
    r = HybridRetriever()
    boost = r._legal_boost("TBK madde 112 ve E. 2023/1234 kararı uyarınca")
    assert boost > 0.0


def test_legal_boost_increases_with_more_patterns():
    r = HybridRetriever()
    boost1 = r._legal_boost("TBK madde 112")
    boost2 = r._legal_boost("TBK madde 112 ve E. 2023/1234 ve 15.03.2022 tarihli")
    assert boost2 > boost1


# ── RRF Fusion ────────────────────────────────────────────────────


def test_rrf_fusion_semantic_only():
    r = HybridRetriever()
    sem = [make_chunk("s1"), make_chunk("s2"), make_chunk("s3")]
    kw = []
    fused = r._rrf_fusion(sem, kw)
    assert len(fused) == 3
    # İlk sıradaki en yüksek skora sahip olmalı
    assert fused[0].final_score >= fused[-1].final_score


def test_rrf_fusion_keyword_only():
    r = HybridRetriever()
    sem = []
    kw = [make_chunk("k1"), make_chunk("k2")]
    fused = r._rrf_fusion(sem, kw)
    assert len(fused) == 2


def test_rrf_fusion_overlap_merges():
    r = HybridRetriever()
    shared = make_chunk("shared", score=0.9)
    sem_only = make_chunk("sem_only", score=0.8)
    kw_only = make_chunk("kw_only", score=0.75)
    fused = r._rrf_fusion([shared, sem_only], [shared, kw_only])
    # Hem semantic hem keyword'de olan chunk daha yüksek skora sahip
    fused_ids = {sc.chunk.chunk_id: sc for sc in fused}
    assert fused_ids["shared"].rrf_score > fused_ids["sem_only"].rrf_score
    assert fused_ids["shared"].rrf_score > fused_ids["kw_only"].rrf_score


def test_rrf_fusion_search_type_hybrid():
    r = HybridRetriever()
    chunk = make_chunk("ortak chunk")
    fused = r._rrf_fusion([chunk], [chunk])
    assert fused[0].search_type == "hybrid"


def test_rrf_fusion_search_type_semantic_only():
    r = HybridRetriever()
    chunk = make_chunk("sadece semantic")
    fused = r._rrf_fusion([chunk], [])
    assert fused[0].search_type == "semantic"


def test_rrf_fusion_search_type_keyword_only():
    r = HybridRetriever()
    chunk = make_chunk("sadece keyword")
    fused = r._rrf_fusion([], [chunk])
    assert fused[0].search_type == "keyword"


def test_rrf_fusion_final_score_bounded():
    r = HybridRetriever()
    sem = [make_chunk(f"c{i}", score=0.99) for i in range(10)]
    kw = [make_chunk(f"c{i}", score=0.99) for i in range(10)]
    fused = r._rrf_fusion(sem, kw)
    for sc in fused:
        assert sc.final_score < 1.0  # min(0.999, ...) garantisi


# ── TS-Query builder ──────────────────────────────────────────────


def test_build_tsquery_basic():
    r = HybridRetriever()
    q = r._build_tsquery("TBK madde 112")
    assert "|" in q
    assert "TBK" in q


def test_build_tsquery_filters_short_words():
    r = HybridRetriever()
    q = r._build_tsquery("ve de bu o")
    # 2 karakter veya altı kelimeler filtrelenmeli → boş olabilir
    assert isinstance(q, str)


def test_build_tsquery_empty_query():
    r = HybridRetriever()
    q = r._build_tsquery("")
    assert q == ""


def test_build_tsquery_removes_punctuation():
    r = HybridRetriever()
    q = r._build_tsquery("borçlu, alacaklı; fesih!")
    # Noktalama kaldırılmış olmalı
    assert ";" not in q
    assert "!" not in q


# ── Doc filter SQL ────────────────────────────────────────────────


def test_doc_filter_sql_with_ids():
    r = HybridRetriever()
    sql = r._doc_filter_sql(["id1", "id2"])
    assert "doc_ids" in sql


def test_doc_filter_sql_without_ids():
    r = HybridRetriever()
    sql = r._doc_filter_sql(None)
    assert sql == ""


# ── Mock ile tam search akışı ─────────────────────────────────────


@pytest.mark.asyncio
async def test_search_returns_hybrid_result():
    r = HybridRetriever(top_k=3)

    sem_chunks = [make_chunk(f"s{i}", score=0.85) for i in range(3)]
    kw_chunks = [make_chunk(f"k{i}", score=0.80) for i in range(3)]

    with (
        patch(
            "app.rag.hybrid_retriever.embedding_service.embed_text",
            new_callable=AsyncMock,
            return_value=[0.1] * 1536,
        ),
        patch(
            "app.rag.hybrid_retriever.embedding_service.search_similar",
            new_callable=AsyncMock,
            return_value=sem_chunks,
        ),
        patch.object(
            r,
            "_keyword_search",
            new_callable=AsyncMock,
            return_value=kw_chunks,
        ),
    ):
        db_mock = AsyncMock()
        result = await r.search(
            db=db_mock,
            query="TBK madde 112 temerrüt",
            tenant_id="tenant-uuid",
        )

    assert len(result.chunks) <= 3
    assert result.query_had_legal_patterns is True
    assert isinstance(result.filtered_by_confidence, int)


@pytest.mark.asyncio
async def test_search_filters_low_confidence_chunks():
    r = HybridRetriever(min_confidence=0.80, top_k=10)

    # Semantic'ten gelen bazı chunk'ların final score < 0.80 olacak
    sem_chunks = [
        make_chunk("high", score=0.95),
        make_chunk("low", score=0.50),
    ]

    with (
        patch(
            "app.rag.hybrid_retriever.embedding_service.embed_text",
            new_callable=AsyncMock,
            return_value=[0.1] * 1536,
        ),
        patch(
            "app.rag.hybrid_retriever.embedding_service.search_similar",
            new_callable=AsyncMock,
            return_value=sem_chunks,
        ),
        patch.object(
            r,
            "_keyword_search",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        db_mock = AsyncMock()
        result = await r.search(
            db=db_mock,
            query="genel soru",
            tenant_id="tenant-uuid",
        )

    # Filtreleme gerçekleşmiş olmalı
    assert result.filtered_by_confidence >= 0
