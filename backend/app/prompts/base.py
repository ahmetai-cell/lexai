from dataclasses import dataclass, field
from typing import Literal


@dataclass
class PromptTemplate:
    slug: str
    category: str
    display_name_tr: str
    display_name_en: str
    system_prompt: str
    description_tr: str = ""
    max_tokens: int | None = 4096
    temperature: float | None = 0.1
    requires_rag: bool = True
    citation_required: bool = True
    hallucination_sensitivity: Literal["low", "medium", "high", "critical"] | None = None
    output_format: str | None = None   # "structured_json" | "markdown_table" | "structured_report"
    jurisdiction: str | None = "TR"
    billable: bool = False
    is_system_level: bool = False
    is_internal: bool = False
    compliance_framework: str | None = None
    tags: list[str] = field(default_factory=list)
