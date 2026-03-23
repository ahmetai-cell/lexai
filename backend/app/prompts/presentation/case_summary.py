from app.prompts.base import PromptTemplate

TEMPLATE = PromptTemplate(
    slug="case_summary",
    category="presentation",
    display_name_tr="Dava Durum Raporu",
    display_name_en="Case Status Report",
    description_tr="Dava için kapsamlı durum raporu hazırlar. Kazanma olasılığı, risk analizi ve strateji içerir.",
    system_prompt="""Davaya ilişkin kapsamlı durum raporu hazırla.

━━━━━━━━━━━━━━━━━━━━━━━━━━━
DAVA DURUM RAPORU
{{ firm_name }} | {{ current_date }}
━━━━━━━━━━━━━━━━━━━━━━━━━━━

**YÖNETİCİ ÖZETİ** (3-5 cümle)
[Davanın mevcut durumunu özet hâlinde sun]

**DAVA BİLGİLERİ**
- Dava No / Mahkeme: [...]
- Taraflar: [...]
- Dava Türü: [...]
- Açılış Tarihi: [...]

**GÜNCEL DURUM**
- Son Gelişme: [...]
- Bekleyen İşlemler: [...]
- Sonraki Duruşma: [...]

**RİSK ANALİZİ**
- Kazanma Olasılığı: ▓▓▓▓░ [%XX] – [Düşük / Orta / Yüksek]
- Ana Riskler: [maddeler halinde]
- Güçlü Yönler: [maddeler halinde]

**ÖNERİLEN STRATEJİ**
[Somut ve uygulanabilir strateji önerileri]

NOT: Risk tahmini veri analizidir; hukuki sonucu garanti etmez.

BAĞLAM:
{{ context_blocks }}

DAVA BİLGİLERİ:
{{ query }}""",
    max_tokens=2500,
    temperature=0.3,
    requires_rag=True,
    citation_required=False,
    output_format="structured_report",
    jurisdiction="TR",
    tags=["dava", "rapor", "strateji", "risk"],
)
