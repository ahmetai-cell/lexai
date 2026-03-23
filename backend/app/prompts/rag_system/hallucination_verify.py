from app.prompts.base import PromptTemplate

TEMPLATE = PromptTemplate(
    slug="hallucination_verify",
    category="rag_system",
    display_name_tr="Hallüsinasyon Doğrulama",
    display_name_en="Hallucination Verification",
    description_tr="HallucinationGuard Aşama 2: Bedrock self-audit. İç kullanım – frontend'e expose edilmez.",
    system_prompt="""Aşağıdaki yanıttaki hukuki iddiaları, verilen kaynak belgelerle doğrula.

Her iddia için JSON formatında değerlendirme yap:
```json
{
  "claim": "İddia metni",
  "verified": true | false,
  "source_reference": "Kaynak N veya null",
  "confidence": 0.0-1.0,
  "note": "Açıklama"
}
```

KAYNAK BELGELER:
{{ context_blocks }}

DOĞRULANACAK YANIT:
{{ answer }}

Yanıt olarak yalnızca JSON dizisi döndür.""",
    max_tokens=2000,
    temperature=0.0,
    requires_rag=True,
    citation_required=False,
    is_system_level=False,
    is_internal=True,
    jurisdiction="TR",
)
