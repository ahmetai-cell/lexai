"""
SystemPromptBuilder — Katman 4 LLM Prompt Mimarisi

Her istekte iki katman oluşturulur:

  Katman A (Global):  LexAI kimlik tanımı + 5 kritik kural + Güven Skoru formatı
  Katman B (Analiz):  Hukuki analiz şablonları için Chain-of-Thought adımları
                      [OLGULAR] → [HUKUK] → [ANALİZ] → [SONUÇ] → [RİSKLER]

Kullanım:
    system_prompt = system_prompt_builder.build(
        template=template,
        context_blocks=context_blocks,
        current_date=current_date,
    )
"""
from app.prompts.base import PromptTemplate

# ── Katman A: Global LexAI Sistem Promptu ─────────────────────────
# "Her istekte gönderilecek" — RAGService tarafından her çağrıya enjekte edilir
LEXAI_GLOBAL_SYSTEM = """\
Sen LexAI'sın — Türk hukuku için özelleşmiş bir analiz sistemisin.

KRİTİK KURALLAR:
1. Yalnızca sana verilen context içindeki bilgiyi kullan.
2. Her iddiayı [Belge:X, Sayfa:Y] formatında kaynak göster.
3. Emin olmadığın durumlarda "Dosyada bu bilgiye ulaşılamadı" de.
4. Hukuki tavsiye verme — analiz yap.
5. Yanıtının sonuna Güven Skoru ekle: Yüksek / Orta / Düşük ve neden.

GÜVEN SKORU FORMATI:
---
**Güven Skoru:** [Yüksek / Orta / Düşük]
**Neden:** [Kaynakların kalitesi, eksik bilgi veya çelişkili veriler hakkında kısa açıklama]
---"""

# ── Katman B: Chain-of-Thought Analiz Adımları ────────────────────
# Hukuki analiz kategorisinde her yanıtta bu yapı zorunludur
LEGAL_COT_INSTRUCTIONS = """\

ZORUNLU ANALİZ YAPISI:
Her hukuki analizde şu adımları sırayla yürüt ve her adımı etiketle:

[OLGULAR]
Dosyadan tespit edilen gerçekler. Yalnızca kaynak belgede yer alan olgular.

[HUKUK]
İlgili kanun maddeleri ve içtihat. Her referans [Belge:X, Sayfa:Y] ile kaynak gösterilmeli.

[ANALİZ]
Olguları hukukla eşleştir. Hangi kural hangi olguya uygulanıyor?

[SONUÇ]
Net hukuki değerlendirme. Somut ve gerekçeli ol.

[RİSKLER]
Belirsizlikler ve eksikler. Dosyada bulunmayan ama önemli olabilecek bilgiler."""

# Hukuki analiz kategorisi slugları
LEGAL_ANALYSIS_CATEGORIES = {
    "legal_analysis",
    "document_analysis",
}

# CoT'nin uygulanacağı spesifik template slugları (kategori dışında olanlar)
LEGAL_COT_SLUGS = {
    "case_law_analysis",
    "statute_interpretation",
    "precedent_comparison",
    "legal_opinion",
    "contract_review",
    "risk_assessment",
    "compliance_check",
    "financial_calculation",
    "adversarial_simulation",
    "chain_of_thought_analysis",
}


class SystemPromptBuilder:
    """
    Her RAG isteği için tam sistem promptunu oluşturur.
    Template'in kendi system_prompt'unu LEXAI_GLOBAL_SYSTEM ile birleştirir.
    """

    def build(
        self,
        template: PromptTemplate,
        rendered_template_system: str,
    ) -> str:
        """
        Final sistem promptunu oluştur:
          1. LexAI global kimlik + kurallar (her zaman)
          2. Template'e özgü prompt (Jinja2 ile render edilmiş)
          3. CoT adımları (hukuki analiz kategorisi için)

        Args:
            template: Kullanılan prompt şablonu
            rendered_template_system: PromptRenderer tarafından render edilmiş template system prompt

        Returns:
            Tam birleşik sistem promptu
        """
        parts: list[str] = [LEXAI_GLOBAL_SYSTEM]

        # Template'e özgü içerik (context_blocks, tarih vb. zaten render edilmiş)
        if rendered_template_system and rendered_template_system.strip():
            parts.append(rendered_template_system)

        # CoT: hukuki analiz kategorisi veya belirli sluglar
        if self._needs_cot(template):
            parts.append(LEGAL_COT_INSTRUCTIONS)

        return "\n\n".join(parts)

    def _needs_cot(self, template: PromptTemplate) -> bool:
        return (
            template.category in LEGAL_ANALYSIS_CATEGORIES
            or template.slug in LEGAL_COT_SLUGS
        )


system_prompt_builder = SystemPromptBuilder()
