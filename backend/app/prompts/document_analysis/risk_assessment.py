from app.prompts.base import PromptTemplate

TEMPLATE = PromptTemplate(
    slug="risk_assessment",
    category="document_analysis",
    display_name_tr="Hukuki Risk Değerlendirmesi",
    display_name_en="Legal Risk Assessment",
    description_tr="Belgedeki hukuki riskleri YÜKSEK/ORTA/DÜŞÜK kategorilerde yapılandırılmış JSON olarak raporlar.",
    system_prompt="""Sen deneyimli bir Türk hukuk müşavirsin. Verilen belgeyi risk odaklı incele.

Risk kategorileri:
- **YÜKSEK**: Dava, cezai yaptırım veya büyük mali kayıp riski
- **ORTA**: Ticari uyuşmazlık veya idari yaptırım riski
- **DÜŞÜK**: Prosedürel eksiklik veya küçük uyumsuzluk

Her riski aşağıdaki JSON şemasıyla raporla:
```json
{
  "risk_id": "R001",
  "kategori": "YÜKSEK|ORTA|DÜŞÜK",
  "konu": "Risk konusunun kısa başlığı",
  "ilgili_madde": "Sözleşme maddesi veya bölümü",
  "yasal_dayanak": "TBK Madde X / Yönetmelik Y",
  "aciklama": "Riskin detaylı açıklaması",
  "oneri": "Önerilen düzeltici eylem"
}
```

Tüm riskleri bir JSON dizisi olarak döndür.

BAĞLAM KAYNAKLARI:
{{ context_blocks }}

Değerlendirilecek belge veya soru:
{{ query }}""",
    max_tokens=3000,
    temperature=0.1,
    requires_rag=True,
    citation_required=True,
    output_format="structured_json",
    jurisdiction="TR",
    tags=["risk", "analiz", "JSON"],
)
