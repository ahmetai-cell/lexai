from app.prompts.base import PromptTemplate

TEMPLATE = PromptTemplate(
    slug="summary_generation",
    category="document_analysis",
    display_name_tr="Hukuki Belge Özeti",
    display_name_en="Legal Document Summary",
    description_tr="Belgeyi avukat ve müvekkil kitlesine yönelik iki ayrı özet olarak sunar.",
    system_prompt="""Hukuki belgeyi iki ayrı kitle için özetle:

## [AVUKAT ÖZETİ]
Teknik hukuki terminoloji, madde atıfları, prosedürel notlar, önemli süreler ve
hak düşürücü tarihler dahil kapsamlı özet.

## [MÜVEKKİL ÖZETİ]
Sade Türkçe, teknik terimlerden kaçınılmış, pratik sonuçlar odaklı özet.
"Ne anlama geliyor?" ve "Ne yapmalıyım?" sorularını yanıtla.

Her özet için:
- Anahtar noktalar (madde madde)
- Önemli tarihler ve süreler
- Dikkat edilmesi gerekenler
- Tavsiye edilen sonraki adımlar

KAYNAK METİN:
{{ context_blocks }}

TALEP:
{{ query }}""",
    max_tokens=2000,
    temperature=0.3,
    requires_rag=True,
    citation_required=False,
    jurisdiction="TR",
    tags=["özet", "müvekkil", "basit"],
)
