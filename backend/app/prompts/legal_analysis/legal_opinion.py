from app.prompts.base import PromptTemplate

TEMPLATE = PromptTemplate(
    slug="legal_opinion",
    category="legal_analysis",
    display_name_tr="Hukuki Görüş Yazısı",
    display_name_en="Legal Opinion Draft",
    description_tr="Resmi hukuki görüş yazısı taslağı hazırlar. Fatura edilebilir premium şablon.",
    system_prompt="""Resmi hukuki görüş yazısı taslağı hazırla.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HUKUKİ GÖRÜŞ
Büro: {{ firm_name }}
Tarih: {{ current_date }}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**I. OLAY VE TALEP ÖZETİ**
[Müvekkil ve konu kısa özeti]

**II. HUKUKİ ÇERÇEVE**
A. İlgili Mevzuat
   [Kanun maddeleri, yönetmelikler – kaynak atıflı]
B. Emsal Kararlar
   [Yalnızca kaynaklarda bulunan kararlar]

**III. HUKUKİ DEĞERLENDİRME**
[Olguların hukuki çerçeveyle birleştirilmesi – adım adım akıl yürütme]

**IV. SONUÇ VE TAVSİYE**
[Net tavsiye – belirsizlikler açıkça belirtilmeli]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NOT: Bu görüş hukuki tavsiye niteliği taşır; somut dava koşullarına göre değişebilir.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

KAYNAKLAR:
{{ context_blocks }}

KONU BİLGİSİ:
{{ query }}""",
    max_tokens=5000,
    temperature=0.2,
    requires_rag=True,
    citation_required=True,
    jurisdiction="TR",
    billable=True,
    tags=["görüş", "resmi", "premium"],
)
