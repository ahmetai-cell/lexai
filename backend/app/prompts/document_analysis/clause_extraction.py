from app.prompts.base import PromptTemplate

TEMPLATE = PromptTemplate(
    slug="clause_extraction",
    category="document_analysis",
    display_name_tr="Madde Çıkarma ve Sınıflandırma",
    display_name_en="Clause Extraction & Classification",
    description_tr="Belgedeki hukuki maddeleri tespit eder, sınıflandırır ve önem skoru atar.",
    system_prompt="""Belgedeki hukuki maddeleri tespit et ve Türk hukuk sınıflandırmasına göre etiketle.

Sınıflandırma kategorileri:
taraflar | konu | bedel | süre | fesih | ceza | teminat |
uyuşmazlık_çözümü | gizlilik | force_majeure | devir_yasağı | diğer

Her madde için şu bilgileri çıkar:
- **orijinal_metin**: Maddenin tam metni (sayfa numarasıyla birlikte)
- **kategori**: Yukarıdaki kategorilerden biri
- **onem_skoru**: 1-5 arası (5 = kritik)
- **yorum**: Hukuki etkisi hakkında kısa yorum
- **kaynak**: [Sayfa X]

BAĞLAM:
{{ context_blocks }}

Sorgu:
{{ query }}""",
    max_tokens=2500,
    temperature=0.0,
    requires_rag=True,
    citation_required=True,
    jurisdiction="TR",
    tags=["madde", "sınıflandırma", "çıkarım"],
)
