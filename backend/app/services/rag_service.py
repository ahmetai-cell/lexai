"""
RAG Orchestrator – Retrieval → Render → Generate → Guard → Return
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


class RAGService:
    def __init__(self):
        self.renderer = PromptRenderer()
        self.citation_tracker = CitationTracker()

    async def query(self, request: RAGRequest, db: AsyncSession) -> RAGResponse:
        """Tam RAG pipeline – sync."""
        template = prompt_registry.get(request.template_slug)

        # 1. Query embedding
        query_vector = await embedding_service.embed_text(request.query)

        # 2. Retrieval
        chunks: list[RetrievedChunk] = []
        if template.requires_rag:
            try:
                chunks = await embedding_service.search_similar(
                    db=db,
                    query_vector=query_vector,
                    tenant_id=request.tenant_id,
                    top_k=settings.RAG_TOP_K,
                    min_similarity=settings.RAG_MIN_SIMILARITY,
                    document_ids=request.document_ids,
                )
            except Exception as e:
                raise RAGRetrievalError(f"Retrieval hatası: {e}")

        # 3. Prompt render
        messages, system_prompt = self.renderer.render(
            template=template,
            query=request.query,
            chunks=chunks,
            extra_vars=request.extra_vars,
            conversation_history=request.conversation_history or [],
        )

        # 4. Bedrock generation
        answer = await bedrock_service.invoke(
            messages=messages,
            system_prompt=system_prompt,
            max_tokens=template.max_tokens,
            temperature=template.temperature,
        )

        # 5. Hallucination guard
        guard_result = await hallucination_guard.verify(
            answer=answer,
            source_chunks=chunks,
            template_sensitivity=getattr(template, "hallucination_sensitivity", None),
        )

        if template.citation_required and guard_result.hallucination_flag:
            if getattr(template, "hallucination_sensitivity", None) == "critical":
                raise HallucinationDetectedError(
                    "Yanıt doğrulanamadı – kaynakta bulunmayan iddialar tespit edildi.",
                    flagged_claims=guard_result.flagged_claims,
                )

        # 6. Citation extraction
        citation_map = self.citation_tracker.extract(answer, chunks)

        logger.info(
            "rag_complete",
            template=request.template_slug,
            chunks=len(chunks),
            confidence=guard_result.confidence_score,
            flagged=guard_result.hallucination_flag,
        )

        return RAGResponse(
            answer=answer,
            sources=chunks,
            citation_map=citation_map,
            confidence_score=guard_result.confidence_score,
            hallucination_flag=guard_result.hallucination_flag,
            flagged_claims=guard_result.flagged_claims,
            token_usage={},
            template_slug=request.template_slug,
        )

    async def stream(
        self,
        request: RAGRequest,
        db: AsyncSession,
    ) -> AsyncGenerator[str, None]:
        """Streaming RAG – SSE token akışı."""
        template = prompt_registry.get(request.template_slug)
        query_vector = await embedding_service.embed_text(request.query)

        chunks: list[RetrievedChunk] = []
        if template.requires_rag:
            chunks = await embedding_service.search_similar(
                db=db,
                query_vector=query_vector,
                tenant_id=request.tenant_id,
                top_k=settings.RAG_TOP_K,
                min_similarity=settings.RAG_MIN_SIMILARITY,
                document_ids=request.document_ids,
            )

        messages, system_prompt = self.renderer.render(
            template=template,
            query=request.query,
            chunks=chunks,
            extra_vars=request.extra_vars,
            conversation_history=request.conversation_history or [],
        )

        async for token in bedrock_service.stream(
            messages=messages,
            system_prompt=system_prompt,
            max_tokens=template.max_tokens,
            temperature=template.temperature,
        ):
            yield token


rag_service = RAGService()
