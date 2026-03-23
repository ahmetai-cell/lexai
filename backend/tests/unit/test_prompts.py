import pytest
from app.prompts.loader import PromptRegistry
from app.prompts.base import PromptTemplate


def test_registry_load_all():
    registry = PromptRegistry()
    registry.load_all()
    templates = registry.list_all()
    # En az 14 public template beklenir (6 internal hariç)
    assert len(templates) >= 14


def test_all_slugs_unique():
    registry = PromptRegistry()
    registry.load_all()
    all_templates = registry.list_all()
    slugs = [t.slug for t in all_templates]
    assert len(slugs) == len(set(slugs)), "Duplicate slug bulundu!"


def test_critical_templates_have_sensitivity():
    registry = PromptRegistry()
    registry.load_all()
    case_law = registry.get("case_law_analysis")
    assert case_law.hallucination_sensitivity == "critical"


def test_billable_templates():
    registry = PromptRegistry()
    registry.load_all()
    billable = [t for t in registry.list_all() if t.billable]
    slugs = {t.slug for t in billable}
    assert "legal_opinion" in slugs
    assert "contract_drafting" in slugs
    assert "petition_drafting" in slugs


def test_template_not_found():
    from app.core.exceptions import TemplateNotFoundError
    registry = PromptRegistry()
    registry.load_all()
    with pytest.raises(TemplateNotFoundError):
        registry.get("nonexistent_template")


def test_internal_templates_not_in_list():
    registry = PromptRegistry()
    registry.load_all()
    public = registry.list_all()
    for t in public:
        assert not t.is_internal, f"Internal şablon public'te göründü: {t.slug}"
