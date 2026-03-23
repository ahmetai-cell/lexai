from app.prompts.base import PromptTemplate

TEMPLATE = PromptTemplate(
    slug="petition_drafting",
    category="drafting_support",
    display_name_tr="Dava Dilekçesi Taslağı",
    display_name_en="Petition / Pleading Draft",
    description_tr="HMK 119. madde zorunlu unsurlarını içeren dava dilekçesi taslağı hazırlar.",
    system_prompt="""Türk yargı sistemine uygun dava dilekçesi taslağı hazırla.

HMK (Hukuk Muhakemeleri Kanunu) 119. madde zorunlu unsurları:

**[MAHKEMENİN ADI]**
**[MAHKEME SAYISI]**

**DAVACI**: [Ad Soyad / Ünvan] – [TC/Vergi No] – [Adres]
**VEKİLİ**: [Avukat Ad Soyad] – Baro Sicil No: [...]
**DAVALI**: [Ad Soyad / Ünvan] – [Adres]
**DAVA KONUSU**: [Dava türü ve değeri]
**AÇIKLAMALAR**:
1. [Vakıalar numaralı paragraflarla]
2. ...
**HUKUKİ SEBEPLER**: [TBK/TTK/HMK madde numaraları]
**DELİLLER**: [Delil listesi]
**SONUÇ VE TALEP** (NETİCE-İ TALEP):
[Davacının tam ve net talebi]

Resmi hukuki üslup, pasif çatı, kesin ifadeler kullan.

KAYNAK KARARLAR:
{{ context_blocks }}

DAVA BİLGİLERİ:
{{ query }}""",
    max_tokens=5000,
    temperature=0.15,
    requires_rag=True,
    citation_required=True,
    jurisdiction="TR",
    billable=True,
    compliance_framework="HMK_119",
    tags=["dilekçe", "dava", "HMK", "mahkeme"],
)
