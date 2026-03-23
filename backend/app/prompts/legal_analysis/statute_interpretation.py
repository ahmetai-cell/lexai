from app.prompts.base import PromptTemplate

TEMPLATE = PromptTemplate(
    slug="statute_interpretation",
    category="legal_analysis",
    display_name_tr="Kanun Yorumu",
    display_name_en="Statute Interpretation",
    description_tr="Dört klasik yorum yöntemi (lafzi, sistematik, tarihi, amaçsal) ile kanun maddesi yorumu yapar.",
    system_prompt="""Türk hukuku kapsamında kanun maddesi yorumu yap.

Yorum yöntemlerini sırayla uygula:
1. **Lafzi Yorum** – Maddenin kelime ve gramer anlamı
2. **Sistematik Yorum** – Kanunun bütünü içindeki yeri
3. **Tarihi Yorum** – Kanun gerekçesi ve TBMM tutanakları
4. **Amaçsal Yorum** – Ratio legis: kanunun amacı

Ardından:
- **Yargıtay Yorumu**: Bağlam belgelerinden güncel yorumu tespit et
- **Doktrin Görüşü**: Varsa akademik görüşleri belirt

Her adımda kaynak göster: [Kaynak N] veya [TBK m.X] formatında.

KANUN KAYNAKLARI:
{{ context_blocks }}

YORUM TALEBİ:
{{ query }}""",
    max_tokens=3000,
    temperature=0.1,
    requires_rag=True,
    citation_required=True,
    jurisdiction="TR",
    tags=["kanun", "yorum", "TBK", "TTK"],
)
