from app.prompts.base import PromptTemplate

TEMPLATE = PromptTemplate(
    slug="legal_letter",
    category="drafting_support",
    display_name_tr="Hukuki İhtarname / Yazışma",
    display_name_en="Legal Notice / Correspondence",
    description_tr="Noter/KEP kanalına uygun ihtarname ve resmi hukuki yazışma taslağı hazırlar.",
    system_prompt="""Resmi hukuki ihtarname veya yazışma taslağı oluştur.

İhtarname türleri: temerrüt ihtarı | ayıplı mal bildirimi | akdin feshi bildirimi |
alacak talebi | sözleşme ihlali bildirimi | iş akdi feshi

Format:
━━━━━━━━━━━━━━━━━━━━━━━━━━
İHTARNAME
Gönderen: [Müvekkil / Avukat]
Muhatap: [Karşı Taraf]
Tarih: {{ current_date }}
Tebliğ Yolu: [Noter / KEP / Taahhütlü Posta]
━━━━━━━━━━━━━━━━━━━━━━━━━━

**Sayın [Muhatap Adı]**,

[Resmi hitap cümlesi]

**1. OLAY ÖZETİ**
[Kronolojik sırayla olaylar]

**2. HUKUKİ DAYANAK**
[İlgili kanun maddeleri]

**3. TALEP/İHTAR**
[Net ve açık talep]

**4. SÜRE VE AKIBETI**
İşbu ihtarnamenin tebliğinden itibaren [7/15/30] gün içinde...
Aksi halde yasal yollara başvurma hakkımız saklıdır.

━━━━━━━━━━━━━━━━━━━━━━━━━━
{{ firm_name }}
━━━━━━━━━━━━━━━━━━━━━━━━━━

İHTARNAME TALEBİ:
{{ query }}""",
    max_tokens=2000,
    temperature=0.15,
    requires_rag=False,
    citation_required=False,
    jurisdiction="TR",
    tags=["ihtarname", "noter", "KEP", "yazışma"],
)
