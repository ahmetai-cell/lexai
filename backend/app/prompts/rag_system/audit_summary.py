from app.prompts.base import PromptTemplate

TEMPLATE = PromptTemplate(
    slug="audit_summary",
    category="rag_system",
    display_name_tr="Denetim İzi Raporu (Audit Trail)",
    display_name_en="Audit Trail Report – KVKK & Bar Compliance",
    description_tr=(
        "Kim hangi soruyu sordu, hangi belge kullanıldı, hangi cevap verildi. "
        "KVKK 12. madde ve baro denetimi için yapılandırılmış erişim kaydı raporu."
    ),
    system_prompt="""Yapay zeka kullanım kayıtlarını KVKK ve baro denetimi gerekliliklerine
uygun şekilde raporla.

━━━ DENETİM İZİ RAPORU ━━━
Büro: {{ firm_name }}
Rapor Tarihi: {{ current_date }}
Kapsam: {{ audit_period | default('Son 30 gün') }}

**1. KULLANIM ÖZETİ**
| Kullanıcı | Rol | Sorgu Sayısı | Erişilen Belge Sayısı | Son Aktivite |
|-----------|-----|-------------|----------------------|-------------|

**2. BELGE ERİŞİM KAYITLARI**
| Belge Adı | Erişen Kullanıcı | Tarih/Saat | Sorgu Türü | Şablon |
|-----------|----------------|-----------|-----------|--------|

**3. VERİ İŞLEME KAYITLARI** (KVKK m.12)
Kişisel veri içeren belgeler için:
| Belge | İçerdiği KVK | İşleme Amacı | Hukuki Dayanak | Saklama Süresi |
|-------|-------------|-------------|----------------|----------------|

**4. ANORMAL AKTİVİTELER** 🚨
- Mesai dışı erişimler
- Yüksek hacimli sorgular
- Başarısız kimlik doğrulama denemeleri
- Hallucination uyarısı alan sorgular

**5. UYUM DURUMU**
- KVKK Uyumu: ✅/❌
- Baro Mesleki Sır Kuralları: ✅/❌
- Veri Silme Talepleri: {{ deletion_requests | default('Yok') }}

AUDIT LOG VERİSİ:
{{ context_blocks }}

RAPOR PARAMETRELERİ:
{{ query }}""",
    max_tokens=4000,
    temperature=0.05,
    requires_rag=True,
    citation_required=False,
    is_internal=False,
    output_format="structured_report",
    jurisdiction="TR",
    tags=["audit", "KVKK", "denetim", "log", "uyum"],
)
