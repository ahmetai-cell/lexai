from app.prompts.base import PromptTemplate

TEMPLATE = PromptTemplate(
    slug="case_law_analysis",
    category="legal_analysis",
    display_name_tr="İçtihat Analizi",
    display_name_en="Case Law Analysis",
    description_tr="Yargıtay ve Danıştay kararları bağlamında içtihat analizi yapar. Karar numaraları zorunlu doğrulama ile.",
    system_prompt="""Yargıtay ve Danıştay kararları bağlamında içtihat analizi yap.

Analiz yapısı:
1. **Emsal Kararlar** – Esas no, tarih, daire bilgisiyle
2. **Hukuki İlkeler** – Kararlardan çıkan temel ilkeler
3. **Kriterlerin Uygulanması** – Somut davaya nasıl uygulanır
4. **Karşıt İçtihatlar** – Varsa aykırı kararlar ve gerekçeleri
5. **Güncel Yargı Eğilimi** – Son dönem eğilimler

KRİTİK UYARI: Yalnızca bağlam kaynaklarında bulunan kararları kullan.
Uydurma karar numarası veya tarih KESINLIKLE yazma.
Emin olmadığın karar için: "Bu karar kaynaklarda doğrulanamadı" yaz.

KAYNAKLAR:
{{ context_blocks }}

ANALİZ TALEBİ:
{{ query }}""",
    max_tokens=4000,
    temperature=0.05,
    requires_rag=True,
    citation_required=True,
    hallucination_sensitivity="critical",
    jurisdiction="TR",
    tags=["içtihat", "Yargıtay", "emsal", "karar"],
)
