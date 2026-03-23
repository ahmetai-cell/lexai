"""
SystemPromptBuilder — Katman 4 birim testleri
"""
import pytest
from app.llm.system_prompt_builder import (
    SystemPromptBuilder,
    LEXAI_GLOBAL_SYSTEM,
    LEGAL_COT_INSTRUCTIONS,
)
from app.prompts.base import PromptTemplate


def make_template(
    slug: str = "test_template",
    category: str = "general",
    system_prompt: str = "test system",
) -> PromptTemplate:
    return PromptTemplate(
        slug=slug,
        category=category,
        display_name_tr="Test",
        display_name_en="Test",
        system_prompt=system_prompt,
    )


# ── Global LexAI system prompt her zaman dahil ───────────────────


def test_global_system_always_included():
    builder = SystemPromptBuilder()
    template = make_template()
    result = builder.build(template, "template-specific content")
    assert "LexAI'sın" in result
    assert "KRİTİK KURALLAR" in result


def test_global_system_has_5_rules():
    builder = SystemPromptBuilder()
    template = make_template()
    result = builder.build(template, "")
    # 5 kural numaralandırılmış olmalı
    for i in range(1, 6):
        assert f"{i}." in result


def test_global_system_has_confidence_score_format():
    builder = SystemPromptBuilder()
    template = make_template()
    result = builder.build(template, "")
    assert "Güven Skoru" in result
    assert "Yüksek" in result
    assert "Orta" in result
    assert "Düşük" in result


def test_global_system_includes_not_found_rule():
    builder = SystemPromptBuilder()
    template = make_template()
    result = builder.build(template, "")
    assert "Dosyada bu bilgiye ulaşılamadı" in result


def test_global_system_includes_citation_format_rule():
    builder = SystemPromptBuilder()
    template = make_template()
    result = builder.build(template, "")
    assert "[Belge:X, Sayfa:Y]" in result


# ── Template-specific system prompt ──────────────────────────────


def test_template_system_appended():
    builder = SystemPromptBuilder()
    template = make_template(system_prompt="ÖZEL BAĞLAM: test belgesi içeriği")
    result = builder.build(template, "ÖZEL BAĞLAM: test belgesi içeriği")
    assert "ÖZEL BAĞLAM" in result


def test_empty_template_system_no_extra_blank():
    builder = SystemPromptBuilder()
    template = make_template(system_prompt="")
    result = builder.build(template, "")
    # Boş template system prompt ile çift boşluk oluşmamalı
    assert "  \n" not in result


# ── CoT sadece hukuki analiz kategorisinde ───────────────────────


def test_cot_included_for_legal_analysis_category():
    builder = SystemPromptBuilder()
    template = make_template(category="legal_analysis")
    result = builder.build(template, "")
    assert "[OLGULAR]" in result
    assert "[HUKUK]" in result
    assert "[ANALİZ]" in result
    assert "[SONUÇ]" in result
    assert "[RİSKLER]" in result


def test_cot_included_for_document_analysis_category():
    builder = SystemPromptBuilder()
    template = make_template(category="document_analysis")
    result = builder.build(template, "")
    assert "[OLGULAR]" in result


def test_cot_not_included_for_general_category():
    builder = SystemPromptBuilder()
    template = make_template(category="rag_system")
    result = builder.build(template, "")
    assert "[OLGULAR]" not in result
    assert "[RİSKLER]" not in result


def test_cot_included_for_cot_slug():
    builder = SystemPromptBuilder()
    template = make_template(slug="chain_of_thought_analysis", category="legal_analysis")
    result = builder.build(template, "")
    assert "[OLGULAR]" in result


def test_cot_included_for_case_law_slug():
    builder = SystemPromptBuilder()
    template = make_template(slug="case_law_analysis", category="legal_analysis")
    result = builder.build(template, "")
    assert "[OLGULAR]" in result


def test_cot_not_for_drafting_template():
    builder = SystemPromptBuilder()
    template = make_template(slug="contract_drafting", category="drafting_support")
    result = builder.build(template, "")
    assert "[OLGULAR]" not in result


# ── Sıralama kontrolü ─────────────────────────────────────────────


def test_global_comes_before_template_system():
    builder = SystemPromptBuilder()
    template = make_template(category="rag_system")
    result = builder.build(template, "TEMPLATE_CONTENT")
    global_pos = result.index("LexAI'sın")
    template_pos = result.index("TEMPLATE_CONTENT")
    assert global_pos < template_pos


def test_cot_comes_after_template_system():
    builder = SystemPromptBuilder()
    template = make_template(category="legal_analysis")
    result = builder.build(template, "TEMPLATE_CONTENT")
    template_pos = result.index("TEMPLATE_CONTENT")
    cot_pos = result.index("[OLGULAR]")
    assert template_pos < cot_pos


# ── Singleton ─────────────────────────────────────────────────────


def test_system_prompt_builder_singleton_importable():
    from app.llm.system_prompt_builder import system_prompt_builder
    assert isinstance(system_prompt_builder, SystemPromptBuilder)


# ── CoT Template yükleniyor mu ────────────────────────────────────


def test_chain_of_thought_template_loadable():
    from app.prompts.legal_analysis.chain_of_thought import TEMPLATE
    assert TEMPLATE.slug == "chain_of_thought_analysis"
    assert TEMPLATE.category == "legal_analysis"
    assert TEMPLATE.hallucination_sensitivity == "high"
    assert TEMPLATE.requires_rag is True


def test_chain_of_thought_system_prompt_has_context():
    from app.prompts.legal_analysis.chain_of_thought import TEMPLATE
    assert "context_blocks" in TEMPLATE.system_prompt
    assert "chunk_count" in TEMPLATE.system_prompt
