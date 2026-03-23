from app.prompts.base import PromptTemplate

TEMPLATE = PromptTemplate(
    slug="rag_citation_format",
    category="rag_system",
    display_name_tr="Kaynak Gösterme Formatı",
    display_name_en="Citation Format Prompt",
    description_tr="Yanıtlarda kullanılacak atıf formatını tanımlar. CitationTracker bu formatı parse eder.",
    system_prompt="""Her hukuki iddia veya bilgi için şu atıf formatlarından birini kullan:

**Belge kaynağı**: [Kaynak {{ chunk_id }}: {{ document_name }}, Sayfa {{ page }}]
**Kanun kaynağı**: [TBK m.{{ article }}] veya [TTK m.{{ article }}] veya [HMK m.{{ article }}]
**İçtihat kaynağı**: [Yargıtay {{ chamber }}. HD, {{ date }}, E.{{ case_no }}]

Yanıtın sonuna mutlaka Kaynakça bölümü ekle:
## Kaynakça
{{ citation_list }}

Kaynak gösterilemeyen iddialar için açıkça belirt: ⚠️ [KAYNAK GEREKLİ]
Hiçbir karar numarası veya kanun maddesi uydurmayacaksın.""",
    max_tokens=None,
    temperature=None,
    requires_rag=True,
    citation_required=True,
    is_system_level=True,
    is_internal=True,
    jurisdiction="TR",
)
