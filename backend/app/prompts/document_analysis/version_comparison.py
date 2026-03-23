from app.prompts.base import PromptTemplate

TEMPLATE = PromptTemplate(
    slug="version_comparison",
    category="document_analysis",
    display_name_tr="Sözleşme Versiyon Karşılaştırma",
    display_name_en="Contract Version Comparison (Diff Analysis)",
    description_tr=(
        "İki sözleşme versiyonunu madde madde karşılaştırır: eklenen, silinen, "
        "değiştirilen ve risk arttıran maddeler ayrı renk/etiketle işaretlenir."
    ),
    system_prompt="""İki belge versiyonunu hukuki açıdan karşılaştır.

Versiyon A = eski sürüm, Versiyon B = yeni sürüm

━━━ KARŞILAŞTIRMA RAPORU ━━━

**ÖZET PANO**
| Değişiklik Türü | Sayı | Risk Etkisi |
|-----------------|------|-------------|
| ✅ Eklenen maddeler | N | Düşük/Orta/Yüksek |
| ❌ Silinen maddeler | N | ... |
| ✏️ Değiştirilen maddeler | N | ... |
| ⚠️ Risk arttıran değişiklikler | N | ... |
| 🟢 Risk azaltan değişiklikler | N | ... |

**DETAYLI DEĞİŞİKLİK LİSTESİ**

Her değişiklik için:
```
[DEĞİŞİKLİK #N] – [Tür: EKLENDİ / SİLİNDİ / DEĞİŞTİRİLDİ]
Madde: [Madde numarası / başlığı]
─── ESKİ METİN (Versiyon A) ───
> "[Eski içerik veya 'YOKTU']"
─── YENİ METİN (Versiyon B) ───
> "[Yeni içerik veya 'KALDIRILDI']"
Hukuki Etki: [Analiz]
Risk Değişimi: ⬆️ Arttı / ⬇️ Azaldı / ➡️ Değişmedi
Öneri: [Varsa tavsiye]
```

**KRİTİK DEĞİŞİKLİKLER** ⚠️
Risk seviyesi YÜKSEK olan değişiklikler ayrıca vurgulanır.

**DEĞİŞMEYEN KRİTİK MADDELER** ✅
Önemli maddelerin her iki versiyonda da aynı kaldığı teyidi.

**GENEL DEĞERLENDİRME**
Yeni versiyon müvekkil açısından daha avantajlı mı?
Net tavsiye: İmzalanabilir / Müzakere gerekli / İmzalanmamalı

KAYNAK BELGELER (A ve B versiyonları):
{{ context_blocks }}

KARŞILAŞTIRMA TALEBİ:
{{ query }}""",
    max_tokens=6000,
    temperature=0.05,
    requires_rag=True,
    citation_required=True,
    output_format="structured_report",
    jurisdiction="TR",
    billable=True,
    tags=["versiyon", "karşılaştırma", "diff", "değişiklik", "sözleşme"],
)
