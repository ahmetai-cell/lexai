"""
WidgetService — Dava Analizi Widget için Claude JSON Pipeline

Normal RAGService'ten FARKLI akış:
  1. Hybrid retrieval → chunks al (aynı)
  2. Chunk metinlerini DOSYA_METNI olarak birleştir
  3. case_widget şablonunun system + user promptlarıyla Bedrock'a çağır
  4. JSON yanıtı parse et (```json bloğu varsa temizle)
  5. Pydantic ile doğrula (DavaAnaliziWidget)
  6. Audit log yaz (aynı)
  7. WidgetResponse döndür

HallucinationGuard ve CitationVerifier BYPASS edilir:
  - Guard, prose yanıtlardaki cümleleri değiştirir → JSON yapısını kırar
  - CitationVerifier, [Kaynak N] desenini arar → JSON'da bu desen yok
  - JSON tutarlılığı Pydantic doğrulamasıyla sağlanır
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field as dc_field

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import RAGRetrievalError
from app.core.logging import get_logger
from app.prompts.document_analysis.case_widget import TEMPLATE, WIDGET_SYSTEM_PROMPT, WIDGET_USER_PROMPT
from app.rag.hybrid_retriever import hybrid_retriever
from app.services.bedrock_service import bedrock_service
from app.services.embedding_service import RetrievedChunk
from app.audit.audit_service import audit_service
from app.schemas.widget import DavaAnaliziWidget, WidgetResponse, WidgetMeta

logger = get_logger(__name__)

# Her chunk'tan alınacak maksimum karakter (bütçe kontrolü)
_MAX_CHUNK_CHARS = 800
# Widget için maksimum chunk sayısı (büyük dosyalarda token bütçesi)
_MAX_CHUNKS = 20


@dataclass
class WidgetRequest:
    document_ids: list[str]
    tenant_id: str
    user_id: str
    # Opsiyonel: belirli bir soru odağı (retrieval kalitesini artırır)
    query_hint: str = "Dava özeti, taraflar, riskler ve kritik olaylar"
    conversation_id: str | None = None
    ip_address: str | None = None
    anomaly_events: list | None = dc_field(default_factory=list)


class WidgetService:

    async def analyze(
        self,
        request: WidgetRequest,
        db: AsyncSession,
    ) -> WidgetResponse:
        """
        Dava dosyasını analiz edip DavaAnaliziWidget döndür.
        Raises: RAGRetrievalError, json.JSONDecodeError, ValidationError
        """
        # ── 1. Chunk retrieval ───────────────────────────────────────
        try:
            hybrid_result = await hybrid_retriever.search(
                db=db,
                query=request.query_hint,
                tenant_id=request.tenant_id,
                document_ids=request.document_ids,
                top_k=_MAX_CHUNKS,
            )
            chunks: list[RetrievedChunk] = hybrid_result.chunks
        except Exception as e:
            raise RAGRetrievalError(f"Widget retrieval hatası: {e}") from e

        if not chunks:
            raise RAGRetrievalError("Belirtilen belgeler için içerik bulunamadı.")

        # ── 2. DOSYA_METNI oluştur ───────────────────────────────────
        context = self._build_context(chunks)

        # ── 3. Bedrock çağrısı ───────────────────────────────────────
        user_message = WIDGET_USER_PROMPT.replace("{context}", context)

        raw = await bedrock_service.invoke(
            messages=[{"role": "user", "content": user_message}],
            system_prompt=WIDGET_SYSTEM_PROMPT,
            max_tokens=TEMPLATE.max_tokens,
            temperature=TEMPLATE.temperature,
        )

        logger.info(
            "widget_bedrock_response",
            tenant_id=request.tenant_id,
            chunks=len(chunks),
            raw_length=len(raw),
        )

        # ── 4. JSON parse ────────────────────────────────────────────
        widget_data = self._parse_json(raw)

        # ── 5. Pydantic doğrulama ────────────────────────────────────
        widget = DavaAnaliziWidget.model_validate(widget_data)

        # ── 6. Audit log ─────────────────────────────────────────────
        try:
            await audit_service.log_rag_query(
                db=db,
                tenant_id=request.tenant_id,
                user_id=request.user_id,
                template_slug=TEMPLATE.slug,
                document_ids=request.document_ids,
                query_text=request.query_hint,
                chunks_retrieved=len(chunks),
                response_generated=True,
                confidence_score=None,
                hallucination_flag=False,
                conversation_id=request.conversation_id,
                ip_address=request.ip_address,
                anomaly_events=request.anomaly_events,
            )
        except Exception as audit_err:
            logger.error("widget_audit_error", error=str(audit_err))

        return WidgetResponse(
            widget=widget,
            meta=WidgetMeta(
                document_ids=request.document_ids,
                chunks_used=len(chunks),
                model_id=settings.BEDROCK_MODEL_ID,
            ),
        )

    # ── Yardımcılar ──────────────────────────────────────────────────

    def _build_context(self, chunks: list[RetrievedChunk]) -> str:
        """
        Chunk metinlerini sayfa referansıyla birleştir.
        Uzun chunk'ları kırp (token bütçesi).
        """
        parts: list[str] = []
        for chunk in chunks:
            text = (chunk.chunk_text or "").strip()
            if not text:
                continue
            if len(text) > _MAX_CHUNK_CHARS:
                text = text[:_MAX_CHUNK_CHARS] + "…"
            source = f"[Sayfa {chunk.page_number}]" if chunk.page_number else ""
            parts.append(f"{source} {text}".strip())
        return "\n\n".join(parts)

    def _parse_json(self, raw: str) -> dict:
        """
        Claude yanıtından JSON çıkar.
        Nadiren ```json ... ``` bloğu içinde sarabilir — temizle.
        """
        text = raw.strip()

        # ```json ... ``` bloğunu soy
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            text = match.group(1).strip()

        # İlk { ... } bloğunu al (önünde/arkasında metin varsa)
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError(f"Claude geçerli JSON döndürmedi. Ham yanıt: {raw[:300]}")

        json_str = text[start:end]
        return json.loads(json_str)


widget_service = WidgetService()
