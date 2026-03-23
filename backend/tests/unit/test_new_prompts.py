"""Yeni eklenen 5 prompt + audit_summary için kayıt ve temel özellik testleri."""
import pytest
from app.prompts.loader import PromptRegistry


@pytest.fixture
def registry():
    r = PromptRegistry()
    r.load_all()
    return r


def test_financial_calculation_registered(registry):
    t = registry.get("financial_calculation")
    assert t.billable is True
    assert t.temperature <= 0.1  # Hesaplama = düşük temperature


def test_adversarial_simulation_registered(registry):
    t = registry.get("adversarial_simulation")
    assert t.billable is True
    assert t.hallucination_sensitivity == "high"
    assert "devil" in " ".join(t.tags).lower() or "strateji" in t.tags


def test_deadline_tracker_registered(registry):
    t = registry.get("deadline_tracker")
    assert "deadline" in t.tags
    assert t.temperature <= 0.1  # Tarih hesabı = deterministik


def test_version_comparison_registered(registry):
    t = registry.get("version_comparison")
    assert t.billable is True
    assert "diff" in t.tags or "karşılaştırma" in t.tags
    assert t.max_tokens >= 5000  # Uzun karşılaştırma


def test_audit_summary_registered(registry):
    t = registry.get("audit_summary")
    assert "audit" in t.tags
    assert "KVKK" in t.tags
    assert t.is_internal is False  # Admin arayüzünde görünmeli


def test_total_public_templates(registry):
    """Toplam public (non-internal) şablon sayısı en az 20 olmalı."""
    public = registry.list_all()
    assert len(public) >= 20, f"Yalnızca {len(public)} public şablon var"


def test_categories_complete(registry):
    """Tüm kategoriler mevcut olmalı."""
    templates = registry.list_all()
    categories = {t.category for t in templates}
    expected = {
        "document_analysis", "legal_analysis",
        "drafting_support", "rag_system", "presentation"
    }
    assert expected.issubset(categories)
