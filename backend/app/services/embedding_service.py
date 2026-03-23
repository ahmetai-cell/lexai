"""
AWS Bedrock Titan Embeddings v2 – vektör üretimi ve pgvector saklama
"""
import json
from dataclasses import dataclass

import boto3
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import EmbeddingError
from app.core.logging import get_logger
from app.models.embedding import DocumentChunk

logger = get_logger(__name__)

BATCH_SIZE = 25  # Bedrock throughput limiti


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    chunk_text: str
    page_number: int | None
    section_title: str | None
    article_number: str | None
    similarity_score: float
    source_metadata: dict | None


class EmbeddingService:
    def __init__(self):
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

    async def embed_text(self, text: str) -> list[float]:
        """Tek metni vektöre çevir."""
        try:
            response = self._client.invoke_model(
                modelId=settings.BEDROCK_EMBEDDING_MODEL_ID,
                contentType="application/json",
                accept="application/json",
                body=json.dumps({"inputText": text, "dimensions": settings.BEDROCK_EMBEDDING_DIMENSIONS}),
            )
            result = json.loads(response["body"].read())
            return result["embedding"]
        except Exception as e:
            raise EmbeddingError(f"Embedding hatası: {e}")

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Toplu embedding üretimi (batch)."""
        embeddings = []
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i : i + BATCH_SIZE]
            for text in batch:
                embedding = await self.embed_text(text)
                embeddings.append(embedding)
        return embeddings

    async def search_similar(
        self,
        db: AsyncSession,
        query_vector: list[float],
        tenant_id: str,
        top_k: int = 8,
        min_similarity: float = 0.72,
        document_ids: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        """pgvector cosine similarity araması – tenant scope'lu."""
        from sqlalchemy import select, func, text

        query_np = np.array(query_vector, dtype=np.float32).tolist()

        stmt = (
            select(
                DocumentChunk,
                (1 - func.cast(DocumentChunk.embedding.cosine_distance(query_np), float)).label("similarity"),
            )
            .where(DocumentChunk.tenant_id == tenant_id)
            .where(DocumentChunk.embedding.isnot(None))
        )

        if document_ids:
            stmt = stmt.where(DocumentChunk.document_id.in_(document_ids))

        stmt = stmt.order_by(text("similarity DESC")).limit(top_k)

        result = await db.execute(stmt)
        rows = result.all()

        chunks = []
        for chunk, similarity in rows:
            if similarity >= min_similarity:
                chunks.append(
                    RetrievedChunk(
                        chunk_id=str(chunk.id),
                        document_id=str(chunk.document_id),
                        chunk_text=chunk.chunk_text,
                        page_number=chunk.page_number,
                        section_title=chunk.section_title,
                        article_number=chunk.article_number,
                        similarity_score=round(float(similarity), 4),
                        source_metadata=chunk.source_metadata,
                    )
                )

        logger.info("retrieval_complete", count=len(chunks), tenant_id=tenant_id)
        return chunks


embedding_service = EmbeddingService()
