"""
Chain-of-Thought Hukuki Analiz Şablonu — Katman 4

Her adım etiketli yapısal analiz:
  [OLGULAR] → [HUKUK] → [ANALİZ] → [SONUÇ] → [RİSKLER]
"""
from app.prompts.base import PromptTemplate

TEMPLATE = PromptTemplate(
    slug="chain_of_thought_analysis",
    category="legal_analysis",
    display_name_tr="Zincir Düşünce Hukuki Analiz",
    display_name_en="Chain-of-Thought Legal Analysis",
    description_tr=(
        "Her hukuki soruyu 5 adımlı yapısal analizle yanıtlar: "
        "[OLGULAR] → [HUKUK] → [ANALİZ] → [SONUÇ] → [RİSKLER]. "
        "Güven Skoru ile birlikte sunulur."
    ),
    system_prompt="""\
BAĞLAM BELGELERİ ({{ chunk_count }} kaynak):
{{ context_blocks }}

Büro: {{ firm_name }} | Analiz Tarihi: {{ current_date }}

GÖREV:
Aşağıdaki soruyu/meseleyi 5 adımlı yapısal analiz çerçevesinde değerlendir.
Her adımı belirtilen etiketle başlat. Kaynakta bulunmayan bilgiyi üretme.""",
    max_tokens=4096,
    temperature=0.1,
    requires_rag=True,
    citation_required=True,
    hallucination_sensitivity="high",
    jurisdiction="TR",
    tags=["cot", "analiz", "yapısal", "5-adım"],
)
