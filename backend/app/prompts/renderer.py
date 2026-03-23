"""
Prompt Renderer – Jinja2 şablonlarını RAG bağlamıyla render eder.
"""
from datetime import datetime, timezone

from jinja2 import Environment, StrictUndefined

from app.prompts.base import PromptTemplate
from app.services.embedding_service import RetrievedChunk

jinja_env = Environment(undefined=StrictUndefined, autoescape=False)


class PromptRenderer:
    def render(
        self,
        template: PromptTemplate,
        query: str,
        chunks: list[RetrievedChunk],
        extra_vars: dict | None = None,
        conversation_history: list[dict] | None = None,
        firm_name: str = "LexAI",
    ) -> tuple[list[dict], str | None]:
        """
        Returns:
            messages: Bedrock Converse API mesaj listesi
            system_prompt: Sistem promptu (ayrı gönderilir)
        """
        context_blocks = self._format_context(chunks)
        current_date = datetime.now(timezone.utc).strftime("%d.%m.%Y")

        vars_map = {
            "query": query,
            "context_blocks": context_blocks,
            "chunk_count": len(chunks),
            "chunks": [
                {
                    "text": c.chunk_text,
                    "source_document": c.source_metadata.get("filename", "Belge") if c.source_metadata else "Belge",
                    "page_number": c.page_number or "-",
                    "similarity_score": c.similarity_score,
                    "chunk_id": c.chunk_id,
                }
                for c in chunks
            ],
            "current_date": current_date,
            "firm_name": firm_name,
            **(extra_vars or {}),
        }

        rendered_system = self._render_string(template.system_prompt, vars_map)

        messages: list[dict] = []
        if conversation_history:
            messages.extend(conversation_history)

        messages.append({"role": "user", "content": query})

        if template.is_system_level:
            return messages, rendered_system

        return messages, rendered_system

    def _format_context(self, chunks: list[RetrievedChunk]) -> str:
        if not chunks:
            return "[Bağlam belgesi bulunamadı]"

        parts = []
        for i, chunk in enumerate(chunks, 1):
            source_name = (
                chunk.source_metadata.get("filename", "Belge") if chunk.source_metadata else "Belge"
            )
            page = chunk.page_number or "-"
            parts.append(
                f"[KAYNAK {i}: {source_name} | Sayfa {page} | Benzerlik: {chunk.similarity_score}]\n"
                f"{chunk.chunk_text}\n"
            )
        return "\n---\n".join(parts)

    def _render_string(self, template_str: str, variables: dict) -> str:
        try:
            tmpl = jinja_env.from_string(template_str)
            return tmpl.render(**variables)
        except Exception:
            # Undefined değişkenler için graceful fallback
            import re
            result = template_str
            for key, value in variables.items():
                result = result.replace(f"{{{{ {key} }}}}", str(value))
            return result
