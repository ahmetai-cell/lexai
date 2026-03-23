"""
Hybrid Retriever — Semantic (0.6) + BM25 Keyword (0.4) + Re-ranking

Akış:
  1. Semantic search  → pgvector cosine similarity
  2. BM25 search      → PostgreSQL ts_vector + ts_rank
  3. Legal boost      → Madde X / karar no / tarih pattern eşleşmeleri
  4. RRF fusion       → Reciprocal Rank Fusion ile birleştir
  5. Min-confidence   → 0.7 altı chunk'ları filtrele

Özellikle madde numaraları, karar numaraları ve tarihler için
keyword search öne çıkar.
"""
import re
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select

from app.core.config import settings
from app.core.logging import get_logger
from app.models.embedding import DocumentChunk
from app.services.embedding_service import RetrievedChunk, embedding_service

logger = get_logger(__name__)

# ── Ağırlıklar ────────────────────────────────────────────────────
SEMANTIC_WEIGHT = 0.6
KEYWORD_WEIGHT  = 0.4
RRF_K = 60  # RRF sabitesi – standart değer

# Chunk'ların context'e alınacağı minimum skor eşiği
MIN_CONFIDENCE = 0.70

# ── Hukuki örüntü tespiti ──────────────────────────────────────────
LEGAL_PATTERNS = [
    # Madde numaraları: TBK m.112, Madde 14, MADDE 3
    re.compile(r"\b(?:TBK|TTK|HMK|TMK|TCK|İK|KVKK)\s*(?:m\.|madde)?\s*\d+", re.I),
    # Karar numaraları: E.2023/1234, K.2023/5678
    re.compile(r"\b[EeKk]\.\s*\d{4}/\d+"),
    # Tarihler: 15.03.2022, 2022-03-15
    re.compile(r"\b\d{1,2}[./\-]\d{1,2}[./\-]\d{4}\b"),
    # Yıl: 2019-2025 arası
    re.compile(r"\b20\d{2}\b"),
    # Yargıtay daire: 4. HD, 11. CD
    re.compile(r"\b\d+\.\s*(?:HD|CD|HGK|CGK)\b"),
]


@dataclass
class ScoredChunk:
    chunk: RetrievedChunk
    semantic_rank: int | None = None
    keyword_rank: int | None = None
    semantic_score: float = 0.0
    keyword_score: float = 0.0
    legal_boost: float = 0.0
    rrf_score: float = 0.0
    final_score: float = 0.0
    search_type: Literal["semantic", "keyword", "hybrid"] = "hybrid"


@dataclass
class HybridSearchResult:
    chunks: list[RetrievedChunk]
    semantic_only: list[str]   # chunk_id listesi
    keyword_only: list[str]
    overlap: list[str]
    query_had_legal_patterns: bool
    filtered_by_confidence: int  # 0.7 altı filtrelen chunk sayısı


class HybridRetriever:
    def __init__(
        self,
        semantic_weight: float = SEMANTIC_WEIGHT,
        keyword_weight: float = KEYWORD_WEIGHT,
        min_confidence: float = MIN_CONFIDENCE,
        top_k: int | None = None,
    ):
        self.semantic_weight = semantic_weight
        self.keyword_weight = keyword_weight
        self.min_confidence = min_confidence
        self.top_k = top_k or settings.RAG_TOP_K

    async def search(
        self,
        db: AsyncSession,
        query: str,
        tenant_id: str,
        document_ids: list[str] | None = None,
        top_k: int | None = None,
    ) -> HybridSearchResult:
        """
        Hybrid arama yap ve sonuçları birleştir.
        """
        k = top_k or self.top_k
        has_legal = self._has_legal_patterns(query)

        # 1. Semantic search
        query_vector = await embedding_service.embed_text(query)
        semantic_chunks = await embedding_service.search_similar(
            db=db,
            query_vector=query_vector,
            tenant_id=tenant_id,
            top_k=k * 2,           # Daha geniş al, fusion'da kısalt
            min_similarity=0.0,    # Filtremeyi biz yapacağız
            document_ids=document_ids,
        )

        # 2. BM25 keyword search
        keyword_chunks = await self._keyword_search(
            db=db,
            query=query,
            tenant_id=tenant_id,
            top_k=k * 2,
            document_ids=document_ids,
            boost_legal=has_legal,
        )

        # 3. RRF Fusion
        fused = self._rrf_fusion(semantic_chunks, keyword_chunks)

        # 4. Confidence filtresi (0.7 altı → context'e alma)
        before_filter = len(fused)
        fused = [sc for sc in fused if sc.final_score >= self.min_confidence]
        filtered_count = before_filter - len(fused)

        # 5. En iyi k sonucu al
        top_chunks = [sc.chunk for sc in fused[:k]]

        # Overlap analizi
        sem_ids = {c.chunk_id for c in semantic_chunks}
        kw_ids  = {c.chunk_id for c in keyword_chunks}

        logger.info(
            "hybrid_search_complete",
            query_len=len(query),
            legal_patterns=has_legal,
            semantic=len(semantic_chunks),
            keyword=len(keyword_chunks),
            fused=len(fused),
            filtered=filtered_count,
            returned=len(top_chunks),
        )

        return HybridSearchResult(
            chunks=top_chunks,
            semantic_only=list(sem_ids - kw_ids),
            keyword_only=list(kw_ids - sem_ids),
            overlap=list(sem_ids & kw_ids),
            query_had_legal_patterns=has_legal,
            filtered_by_confidence=filtered_count,
        )

    async def _keyword_search(
        self,
        db: AsyncSession,
        query: str,
        tenant_id: str,
        top_k: int,
        document_ids: list[str] | None,
        boost_legal: bool,
    ) -> list[RetrievedChunk]:
        """
        PostgreSQL full-text search (ts_vector + ts_rank).
        Hukuki pattern içeriyorsa trigram benzerliği de ekle.
        """
        # Türkçe için unaccent + simple config (turkish stemmer daha iyi olur,
        # ama çoğu kurulumda 'simple' güvenli)
        ts_query = self._build_tsquery(query)
        if not ts_query:
            return []

        # Legal boost: madde/karar numarası eşleşmesinde ek puan
        legal_boost_sql = ""
        if boost_legal:
            # Trigram similarity ile exact string match boost
            legal_boost_sql = """
                + (similarity(chunk_text, :raw_query) * 0.3)
            """

        sql = text(f"""
            SELECT
                id::text         AS chunk_id,
                document_id::text,
                chunk_text,
                chunk_index,
                page_number,
                section_title,
                article_number,
                source_metadata,
                (
                    ts_rank_cd(
                        to_tsvector('simple', chunk_text),
                        to_tsquery('simple', :ts_query),
                        32
                    ) {legal_boost_sql}
                ) AS keyword_score
            FROM document_chunks
            WHERE
                tenant_id = :tenant_id::uuid
                AND to_tsvector('simple', chunk_text) @@ to_tsquery('simple', :ts_query)
                {self._doc_filter_sql(document_ids)}
            ORDER BY keyword_score DESC
            LIMIT :top_k
        """)

        params: dict = {
            "ts_query": ts_query,
            "tenant_id": tenant_id,
            "top_k": top_k,
            "raw_query": query,
        }
        if document_ids:
            params["doc_ids"] = document_ids

        try:
            result = await db.execute(sql, params)
            rows = result.fetchall()
        except Exception as e:
            logger.warning("keyword_search_failed", error=str(e))
            return []

        chunks = []
        for row in rows:
            chunks.append(RetrievedChunk(
                chunk_id=row.chunk_id,
                document_id=row.document_id,
                chunk_text=row.chunk_text,
                page_number=row.page_number,
                section_title=row.section_title,
                article_number=row.article_number,
                similarity_score=float(row.keyword_score),
                source_metadata=row.source_metadata,
            ))
        return chunks

    def _rrf_fusion(
        self,
        semantic: list[RetrievedChunk],
        keyword: list[RetrievedChunk],
    ) -> list[ScoredChunk]:
        """
        Reciprocal Rank Fusion:
            score(d) = Σ 1 / (k + rank_i)

        Ağırlıklı versiyon:
            score(d) = w_sem × (1/(k + sem_rank)) + w_kw × (1/(k + kw_rank))
        """
        scored: dict[str, ScoredChunk] = {}

        # Semantic skorları
        for rank, chunk in enumerate(semantic, 1):
            cid = chunk.chunk_id
            if cid not in scored:
                scored[cid] = ScoredChunk(chunk=chunk)
            scored[cid].semantic_rank = rank
            scored[cid].semantic_score = chunk.similarity_score
            scored[cid].legal_boost = self._legal_boost(chunk.chunk_text)

        # Keyword skorları
        for rank, chunk in enumerate(keyword, 1):
            cid = chunk.chunk_id
            if cid not in scored:
                scored[cid] = ScoredChunk(chunk=chunk)
            scored[cid].keyword_rank = rank
            scored[cid].keyword_score = chunk.similarity_score

        # RRF hesapla
        for sc in scored.values():
            sem_rrf = (
                self.semantic_weight * (1.0 / (RRF_K + sc.semantic_rank))
                if sc.semantic_rank
                else 0.0
            )
            kw_rrf = (
                self.keyword_weight * (1.0 / (RRF_K + sc.keyword_rank))
                if sc.keyword_rank
                else 0.0
            )
            sc.rrf_score = sem_rrf + kw_rrf + sc.legal_boost

            # Normalize: orijinal semantic score ile ağırlıklı final skor
            # Yüksek semantic score varsa onu da dikkate al
            sc.final_score = min(
                0.999,
                sc.rrf_score * 100 + sc.semantic_score * 0.3
            )

            # Hangi kaynaktan geldiğini işaretle
            if sc.semantic_rank and sc.keyword_rank:
                sc.search_type = "hybrid"
            elif sc.semantic_rank:
                sc.search_type = "semantic"
            else:
                sc.search_type = "keyword"

        return sorted(scored.values(), key=lambda x: x.final_score, reverse=True)

    def _build_tsquery(self, query: str) -> str:
        """
        Sorguyu PostgreSQL tsquery formatına dönüştür.
        Hukuki terimler için özel işlem.
        """
        # Noktalama temizle (tsquery için)
        clean = re.sub(r"[^\w\s]", " ", query)
        words = [w.strip() for w in clean.split() if len(w.strip()) > 2]
        if not words:
            return ""
        # OR mantığı kullan (AND çok kısıtlayıcı olur)
        return " | ".join(words)

    def _doc_filter_sql(self, document_ids: list[str] | None) -> str:
        if not document_ids:
            return ""
        return "AND document_id = ANY(:doc_ids::uuid[])"

    def _has_legal_patterns(self, query: str) -> bool:
        """Sorguda hukuki örüntü var mı?"""
        return any(p.search(query) for p in LEGAL_PATTERNS)

    def _legal_boost(self, chunk_text: str) -> float:
        """
        Chunk hukuki örüntü içeriyorsa bonus puan ver.
        Madde no, karar no, tarih içeren chunk'lar öne çıksın.
        """
        match_count = sum(
            1 for p in LEGAL_PATTERNS if p.search(chunk_text)
        )
        return match_count * 0.005  # Küçük ama belirleyici bonus


hybrid_retriever = HybridRetriever()
