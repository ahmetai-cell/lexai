from app.prompts.base import PromptTemplate

TEMPLATE = PromptTemplate(
    slug="compliance_check",
    category="document_analysis",
    display_name_tr="Mevzuat Uyum Kontrolü",
    display_name_en="Regulatory Compliance Check",
    description_tr="KVKK, TTK, TBK, İş Kanunu ve Tüketici Koruma Kanunu kapsamında uyum denetimi yapar.",
    system_prompt="""Türk mevzuatı kapsamında uyum denetimi gerçekleştir.

Kontrol edilecek mevzuat çerçevesi (ilgili olanları uygula):
- **KVKK** – 6698 Sayılı Kişisel Verilerin Korunması Kanunu
- **TTK** – 6102 Sayılı Türk Ticaret Kanunu
- **TBK** – 6098 Sayılı Türk Borçlar Kanunu
- **İş Kanunu** – 4857 Sayılı
- **Tüketici Koruma** – 6502 Sayılı

Her uyumsuzluk için:
1. **Kanun Maddesi**: İhlal edilen madde numarası
2. **İhlal Açıklaması**: Ne şekilde uyumsuzluk var
3. **Risk Seviyesi**: Yüksek / Orta / Düşük
4. **Düzeltici Eylem Planı**: Somut adımlar

Eğer uyumsuzluk yoksa açıkça belirt.

BAĞLAM:
{{ context_blocks }}

Belge/Soru:
{{ query }}""",
    max_tokens=3500,
    temperature=0.1,
    requires_rag=True,
    citation_required=True,
    jurisdiction="TR",
    tags=["KVKK", "uyum", "mevzuat", "denetim"],
)
