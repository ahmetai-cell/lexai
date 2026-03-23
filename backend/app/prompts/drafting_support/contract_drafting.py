from app.prompts.base import PromptTemplate

TEMPLATE = PromptTemplate(
    slug="contract_drafting",
    category="drafting_support",
    display_name_tr="Sözleşme Taslağı Oluşturma",
    display_name_en="Contract Drafting",
    description_tr="TBK uyumlu standart sözleşme taslağı hazırlar. Boş alanlar [BRACKET] formatında işaretlenir.",
    system_prompt="""Türk Borçlar Kanunu (TBK) kapsamında sözleşme taslağı hazırla.

Standart sözleşme yapısı:
1. **Taraflar ve Tanımlar**
2. **Sözleşmenin Konusu**
3. **Bedel ve Ödeme Koşulları**
4. **Tarafların Hak ve Yükümlülükleri**
5. **Sözleşme Süresi ve Fesih** (TBK 435-440 atıflı)
6. **Ceza Koşulu ve Tazminat** (TBK 179-180 atıflı)
7. **Mücbir Sebep**
8. **Gizlilik**
9. **Uyuşmazlık Çözümü** (Türk mahkemeleri / tahkim tercihi)
10. **Genel Hükümler**

Doldurulacak alanları [TARAF ADI], [TARİH], [TUTAR] gibi köşeli parantezle işaretle.
Hukuki terminoloji kullan, açık ve uygulanabilir ifadeler seç.

MEVCUT ŞABLONLAR VE BAĞLAM:
{{ context_blocks }}

SÖZLEŞME TALEBİ:
{{ query }}""",
    max_tokens=6000,
    temperature=0.2,
    requires_rag=True,
    citation_required=False,
    jurisdiction="TR",
    billable=True,
    tags=["sözleşme", "taslak", "TBK"],
)
