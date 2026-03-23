from app.prompts.base import PromptTemplate

TEMPLATE = PromptTemplate(
    slug="rag_context_injection",
    category="rag_system",
    display_name_tr="Bağlam Enjeksiyon Şablonu",
    display_name_en="RAG Context Injection Template",
    description_tr="Alınan chunk'ları numaralı ve etiketli kaynak bloğuna dönüştürür.",
    system_prompt="""[KAYNAK BELGELER – {{ chunk_count }} bölüm bulundu]

{% for chunk in chunks %}
---
KAYNAK {{ loop.index }}: {{ chunk.source_document }} | Sayfa {{ chunk.page_number }} | Benzerlik: {{ chunk.similarity_score }}
{{ chunk.text }}
{% endfor %}
---

Yukarıdaki kaynak belgeler dışında bilgi kullanma.
Yanıtında her iddia için [Kaynak N] referansı ver.""",
    max_tokens=None,
    temperature=None,
    requires_rag=True,
    citation_required=False,
    is_system_level=True,
    is_internal=True,
    jurisdiction=None,
)
