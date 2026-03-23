"""
Prompt Registry – Tüm şablonları startup'ta yükler ve kayıt eder.
"""
from app.prompts.base import PromptTemplate
from app.core.logging import get_logger

logger = get_logger(__name__)


class PromptRegistry:
    def __init__(self):
        self._templates: dict[str, PromptTemplate] = {}

    def register(self, template: PromptTemplate) -> None:
        self._templates[template.slug] = template

    def get(self, slug: str) -> PromptTemplate:
        from app.core.exceptions import TemplateNotFoundError
        if slug not in self._templates:
            raise TemplateNotFoundError(f"Şablon bulunamadı: {slug}")
        return self._templates[slug]

    def list_by_category(self, category: str) -> list[PromptTemplate]:
        return [t for t in self._templates.values() if t.category == category and not t.is_internal]

    def list_all(self) -> list[PromptTemplate]:
        return [t for t in self._templates.values() if not t.is_internal]

    def load_all(self) -> None:
        """Tüm prompt modüllerini import et ve şablonları kayıt et."""
        from app.prompts.document_analysis import contract_review, risk_assessment
        from app.prompts.document_analysis import clause_extraction, compliance_check, summary_generation
        from app.prompts.document_analysis import version_comparison
        from app.prompts.legal_analysis import case_law_analysis, statute_interpretation
        from app.prompts.legal_analysis import precedent_comparison, legal_opinion
        from app.prompts.legal_analysis import financial_calculation, adversarial_simulation, deadline_tracker
        from app.prompts.legal_analysis import chain_of_thought
        from app.prompts.drafting_support import contract_drafting, petition_drafting
        from app.prompts.drafting_support import legal_letter, amendment_drafting
        from app.prompts.rag_system import system_prompt, context_injection, citation_prompt
        from app.prompts.rag_system import hallucination_verify, rag_fallback, audit_summary
        from app.prompts.presentation import case_summary, legal_brief

        modules = [
            # Belge Analizi (6)
            contract_review, risk_assessment, clause_extraction,
            compliance_check, summary_generation, version_comparison,
            # Hukuki Analiz (7)
            case_law_analysis, statute_interpretation,
            precedent_comparison, legal_opinion,
            financial_calculation, adversarial_simulation, deadline_tracker,
            chain_of_thought,
            # Yazım Desteği (4)
            contract_drafting, petition_drafting, legal_letter, amendment_drafting,
            # RAG Sistem (6)
            system_prompt, context_injection, citation_prompt,
            hallucination_verify, rag_fallback, audit_summary,
            # Sunum (2)
            case_summary, legal_brief,
        ]

        for module in modules:
            if hasattr(module, "TEMPLATE"):
                self.register(module.TEMPLATE)

        logger.info("prompts_loaded", count=len(self._templates))


prompt_registry = PromptRegistry()
