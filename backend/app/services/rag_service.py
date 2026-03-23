"""
RAG Orchestrator – Retrieval → Filter → Render → Generate → Guard → Verify → Return

Katman 3 entegrasyonu:
  1. HybridRetriever  — semantic 0.6 + BM25 0.4 + RRF
  2. HallucinationGuard.filter_chunks — confidence < 0.7 olanları context'ten çıkar
  3. HallucinationGuard.verify — cümle bazlı claim doğrulaması + Jaccard
  4. CitationVerifier — [Kaynak N, Sayfa X] atıflarını doğrula, hatalıya uyarı enjekte et
"""
from dataclasses import dataclass, field
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import RAGRetrievalError, HallucinationDetectedError
from app.core.logging import get_logger
from app.prompts.loader import prompt_registry
from app.prompts.renderer import PromptRenderer
from app.services.bedrock_service import bedrock_service
from app.services.embedding_service import embedding_service, RetrievedChunk
from app.services.hallucination_guard import hallucination_guard
from app.rag.citation_tracker import CitationTracker
from app.rag.hybrid_retriever import hybrid_retriever
from app.rag.citation_verifier import citation_verifier
from app.llm.system_prompt_builder import system_prompt_builder

logger = get_logger(__name__)


@dataclass
class RAGRequest:
    query: str
    tenant_id: str
    user_id: str
    template_slug: str
    document_ids: list[str] | None = None
    conversation_history: list[dict] | None = None
    extra_vars: dict = field(default_factory=dict)


@dataclass
class RAGResponse:
    answer: str
    sources: list[RetrievedChunk]
    citation_map: dict
    confidence_score: float
    hallucination_flag: bool
    flagged_claims: list[str]
    token_usage: dict
    template_slug: str
    # Katman 3 ek bilgiler
    original_answer: str = ""
    replaced_sentences: list[str] = field(default_factory=list)
    citation_errors: int = 0
    chunks_filtered: int = 0


class RAGService:
    def __init__(self):
        self.renderer = PromptRenderer()
        self.citation_tracker = CitationTracker()

    async def query(self, request: RAGRequest, db: AsyncSession) -> RAGResponse:
        """Tam RAG pipeline – Katman 3 entegreli."""
        template = prompt_registry.get(request.template_slug)

        # ── 1. Hybrid Retrieval ─────────────────────────────────────
        chunks: list[RetrievedChunk] = []
        chunks_filtered = 0

        if template.requires_rag:
            try:
                hybrid_result = await hybrid_retriever.search(
                    db=db,
                    query=request.query,
                    tenant_id=request.tenant_id,
                    document_ids=request.document_ids,
                    top_k=settings.RAG_TOP_K,
                )
                chunks = hybrid_result.chunks
                chunks_filtered = hybrid_result.filtered_by_confidence
            except Exception as e:
                raise RAGRetrievalError(f"Hybrid retrieval hatası: {e}")

        # ── 2. Pre-generation chunk filtresi (HallucinationGuard Aşama 1) ──
        # HybridRetriever zaten 0.7 altını filtreler; guard burada ikinci kontrol
        chunks, extra_filtered = hallucination_guard.filter_chunks(chunks)
        chunks_filtered += extra_filtered

        # ── 3. Prompt render ────────────────────────────────────────
        messages, template_system = self.renderer.render(
            template=template,
            query=request.query,
            chunks=chunks,
            extra_vars=request.extra_vars,
            conversation_history=request.conversation_history or [],
        )

        # Katman 4: Global LexAI system prompt + CoT (gerekirse) ekle
        system_prompt = system_prompt_builder.build(
            template=template,
            rendered_template_system=template_system or "",
        )

        # ── 4. Bedrock generation ───────────────────────────────────
        raw_answer = await bedrock_service.invoke(
            messages=messages,
            system_prompt=system_prompt,
            max_tokens=template.max_tokens,
            temperature=template.temperature,
        )

        # ── 5. Hallucination Guard (Aşama 2 + 3) ───────────────────
        guard_result = await hallucination_guard.verify(
            answer=raw_answer,
            source_chunks=chunks,
            template_sensitivity=getattr(template, "hallucination_sensitivity", None),
        )

        if template.citation_required and guard_result.hallucination_flag:
            if getattr(template, "hallucination_sensitivity", None) == "critical":
                raise HallucinationDetectedError(
                    "Yanıt doğrulanamadı – kaynakta bulunmayan iddialar tespit edildi.",
                    flagged_claims=guard_result.flagged_claims,
                )

        # ── 6. Citation Verification ────────────────────────────────
        # cleaned_answer üzerinde çalış (sahte iddialar zaten temizlendi)
        citation_report = citation_verifier.verify(
            answer=guard_result.cleaned_answer,
            retrieved_chunks=chunks,
        )

        # Audit log'a yaz
        for entry in citation_report.audit_entries():
            logger.warning("citation_audit", **entry)

        # ── 7. Citation extraction (legacy tracker) ─────────────────
        citation_map = self.citation_tracker.extract(
            citation_report.verified_answer, chunks
        )

        logger.info(
            "rag_complete",
            template=request.template_slug,
            chunks=len(chunks),
            chunks_filtered=chunks_filtered,
            confidence=guard_result.confidence_score,
            hallucination_flag=guard_result.hallucination_flag,
            replaced_sentences=len(guard_result.replaced_sentences),
            citation_errors=citation_report.error_count,
            total_citations=citation_report.total_citations,
        )

        return RAGResponse(
            # Nihai yanıt: hallucination temizlenmiş + citation uyarıları enjekte edilmiş
            answer=citation_report.verified_answer,
            sources=chunks,
            citation_map=citation_map,
            confidence_score=guard_result.confidence_score,
            hallucination_flag=guard_result.hallucination_flag,
            flagged_claims=guard_result.flagged_claims,
            token_usage={},
            template_slug=request.template_slug,
            original_answer=raw_answer,
            replaced_sentences=guard_result.replaced_sentences,
            citation_errors=citation_report.error_count,
            chunks_filtered=chunks_filtered,
        )

    async def stream(
        self,
        request: RAGRequest,
        db: AsyncSession,
    ) -> AsyncGenerator[str, None]:
        """Streaming RAG – SSE token akışı. (Guard post-processing streaming'de uygulanmaz.)"""
        template = prompt_registry.get(request.template_slug)

        chunks: list[RetrievedChunk] = []
        if template.requires_rag:
            try:
                hybrid_result = await hybrid_retriever.search(
                    db=db,
                    query=request.query,
                    tenant_id=request.tenant_id,
                    document_ids=request.document_ids,
                    top_k=settings.RAG_TOP_K,
                )
                chunks = hybrid_result.chunks
            except Exception:
                # Streaming'de retrieval hatası sessizce boş chunk ile devam eder
                chunks = []

        # Pre-generation filtresi
        chunks, _ = hallucination_guard.filter_chunks(chunks)

        messages, template_system = self.renderer.render(
            template=template,
            query=request.query,
            chunks=chunks,
            extra_vars=request.extra_vars,
            conversation_history=request.conversation_history or [],
        )

        system_prompt = system_prompt_builder.build(
            template=template,
            rendered_template_system=template_system or "",
        )

        async for token in bedrock_service.stream(
            messages=messages,
            system_prompt=system_prompt,
            max_tokens=template.max_tokens,
            temperature=template.temperature,
        ):
            yield token


rag_service = RAGService()
