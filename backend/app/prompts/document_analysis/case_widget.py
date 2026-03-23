"""
case_widget — Dava Analizi Widget Prompt Şablonu

Claude bu şablon ile çağrıldığında yalnızca yapılandırılmış JSON döndürür.
HallucinationGuard ve CitationVerifier bu şablon için bypass edilir
(JSON yapısını kırarlar; doğrulama Pydantic katmanında yapılır).
"""
from app.prompts.base import PromptTemplate

# Widget için özel system prompt — kimlik + katı JSON kuralı
WIDGET_SYSTEM_PROMPT = """\
Sen LexAI'sın — Türk hukuku için özelleşmiş bir analiz sistemisin.
Sana verilen hukuki dava dosyasını analiz edip yalnızca aşağıdaki JSON formatında yanıt ver.
Açıklama, giriş cümlesi veya markdown ekleme. Sadece JSON döndür.\
"""

# User prompt şablonu — {context} ve kurallar
WIDGET_USER_PROMPT = """\
Aşağıdaki dava dosyasını analiz et ve şu JSON yapısını doldur:

{
  "dava_ozeti": {
    "baslik": "...",
    "aciklama": "...",
    "analiz_suresi": "...",
    "kazanma_ihtimali": 72,
    "risk_sayisi": 3,
    "eksik_belge_sayisi": 2
  },
  "olaylar": [
    {
      "tarih": "...",
      "baslik": "...",
      "aciklama": "...",
      "tip": "success | info | warning | danger",
      "kaynak": "Belge adı, Sayfa X"
    }
  ],
  "taraflar": [
    {
      "rol": "Davacı | Davalı | Tanık | Bilirkişi",
      "ad": "...",
      "detay": "...",
      "uyari": "..."
    }
  ],
  "riskler": [
    {
      "seviye": "Yüksek | Orta | Düşük",
      "baslik": "...",
      "aciklama": "...",
      "oneri": "..."
    }
  ]
}

Kurallar:
1. Yalnızca dosyada geçen bilgileri kullan — uydurma.
2. Her olayın kaynağına belge adı ve sayfa numarası ekle.
3. Riskler en yüksekten en düşüğe sıralı olsun.
4. Kazanma ihtimalini delil durumuna göre 0-100 arası ver, gerekçesiz yazma.
5. Tarihler DD Ay YYYY formatında.

Dosya:
{context}\
"""

TEMPLATE = PromptTemplate(
    slug="case_widget_analysis",
    category="document_analysis",
    display_name_tr="Dava Analizi Widget",
    display_name_en="Case Analysis Widget",
    system_prompt=WIDGET_SYSTEM_PROMPT,
    description_tr="Dava dosyasını analiz edip widget için yapılandırılmış JSON üretir.",
    max_tokens=4096,
    temperature=0.1,
    requires_rag=True,
    citation_required=False,          # JSON çıktı — citation guard bypass
    hallucination_sensitivity=None,   # JSON çıktı — hallucination guard bypass
    output_format="structured_json",
    jurisdiction="TR",
    billable=True,
    tags=["widget", "structured", "dava-analizi"],
)
