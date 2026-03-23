from app.prompts.base import PromptTemplate

TEMPLATE = PromptTemplate(
    slug="amendment_drafting",
    category="drafting_support",
    display_name_tr="Sözleşme Ek / Değişiklik Taslağı",
    display_name_en="Contract Amendment Drafting",
    description_tr="Mevcut sözleşmeye ek protokol veya değişiklik zeyilnamesi hazırlar.",
    system_prompt="""Mevcut sözleşmeye ek protokol veya değişiklik zeyilnamesi hazırla.

EK PROTOKOL yapısı:
━━━━━━━━━━━━━━━━━━━━━━━━━━
EK PROTOKOL / ZEYİLNAME
Ana Sözleşme: [Sözleşme Tarih ve No]
Protokol Tarihi: {{ current_date }}
━━━━━━━━━━━━━━━━━━━━━━━━━━

**Madde 1 – Kapsam**
[Ana sözleşmeye atıf]

**Madde 2 – Değiştirilen Hükümler**
[Madde No] sayılı maddenin mevcut metni:
> "[Eski metin]"
şeklinde değiştirilmiştir:
> "[Yeni metin]"

**Madde 3 – Eklenen Hükümler**
[Yeni maddeler]

**Madde 4 – Yürürlük**
Bu ek protokol [tarih] tarihinde yürürlüğe girer.
Ana sözleşmenin değiştirilmeyen hükümleri geçerliliğini korur.

Mevcut madde numaralarını koru, tutarsızlık oluşturma.

MEVCUT SÖZLEŞME BAĞLAMI:
{{ context_blocks }}

DEĞİŞİKLİK TALEBİ:
{{ query }}""",
    max_tokens=3000,
    temperature=0.1,
    requires_rag=True,
    citation_required=False,
    jurisdiction="TR",
    tags=["ek protokol", "değişiklik", "zeyilname"],
)
