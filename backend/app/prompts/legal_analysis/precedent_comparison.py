from app.prompts.base import PromptTemplate

TEMPLATE = PromptTemplate(
    slug="precedent_comparison",
    category="legal_analysis",
    display_name_tr="Emsal Karşılaştırma",
    display_name_en="Precedent Comparison",
    description_tr="İki veya daha fazla hukuki durumu emsal açısından karşılaştırma matrisi oluşturur.",
    system_prompt="""İki veya daha fazla hukuki durumu emsal açısından karşılaştır.

Karşılaştırma matrisini Markdown tablo formatında oluştur:

| Kriter | Durum A | Durum B | İlgili Emsal Karar |
|--------|---------|---------|-------------------|
| ... | ... | ... | ... |

Tablonun ardından:
- **Benzerlikler**: Ortak hukuki unsurlar
- **Kritik Farklılıklar**: Sonucu etkileyen ayrımlar
- **Güçlü Emsal**: Hangi emsalin daha güçlü uygulanacağı ve neden
- **Sonuç Tahmini**: Mevcut duruma en yakın emsale göre olası sonuç

YALNIZCA kaynaklardaki kararları kullan.

KAYNAK İÇTİHATLAR:
{{ context_blocks }}

KARŞILAŞTIRMA TALEBİ:
{{ query }}""",
    max_tokens=3500,
    temperature=0.1,
    requires_rag=True,
    citation_required=True,
    output_format="markdown_table",
    jurisdiction="TR",
    tags=["emsal", "karşılaştırma", "tablo"],
)
