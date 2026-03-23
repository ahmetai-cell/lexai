from app.prompts.base import PromptTemplate

TEMPLATE = PromptTemplate(
    slug="legal_brief",
    category="presentation",
    display_name_tr="Hukuki Bülten / Sunum",
    display_name_en="Legal Brief / Presentation",
    description_tr="Müvekkil veya iç sunum için hukuki bülten hazırlar. Hedef kitle ve format parametrelenebilir.",
    system_prompt="""Müvekkil veya iç sunum için hukuki bülten hazırla.

Hedef kitle: {{ audience_type | default('genel') }}
Sunum formatı: {{ format_type | default('bülten') }}

İçerik yapısı:
**1. BAŞLIK VE KAPSAM**
[Konunun 1-2 cümlelik tanımı]

**2. TEMEL HUKUKİ GELİŞMELER**
[Her madde için özet – kanun değişiklikleri, yeni kararlar]

**3. MÜVEKKİLE ETKİSİ**
[Pratik sonuçlar – "Bu sizin için ne anlama geliyor?"]

**4. ALINMASI GEREKEN ÖNLEMLER**
- [ ] Eylem 1
- [ ] Eylem 2
- [ ] Eylem 3

**5. KAYNAKLAR**
[İlgili mevzuat ve kararlar]

Dil: Net, anlaşılır, gereksiz jargondan kaçınılmış.

KAYNAK:
{{ context_blocks }}

KONU:
{{ query }}""",
    max_tokens=3000,
    temperature=0.4,
    requires_rag=True,
    citation_required=False,
    jurisdiction="TR",
    billable=True,
    tags=["bülten", "sunum", "müvekkil"],
)
