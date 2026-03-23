"""
Dava Analizi Widget — Pydantic şemaları

Claude'un döndürdüğü raw JSON bu modellere parse edilir.
Frontend bu yapıyı direkt tüketir.
"""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, field_validator


# ── Alt modeller ──────────────────────────────────────────────────────────────

class DavaOzeti(BaseModel):
    baslik: str
    aciklama: str
    analiz_suresi: str
    kazanma_ihtimali: int = Field(ge=0, le=100)
    risk_sayisi: int = Field(ge=0)
    eksik_belge_sayisi: int = Field(ge=0)


class OlayTip(str):
    """success | info | warning | danger"""


class Olay(BaseModel):
    tarih: str
    baslik: str
    aciklama: str
    tip: Literal["success", "info", "warning", "danger"]
    kaynak: str


class Taraf(BaseModel):
    rol: Literal["Davacı", "Davalı", "Tanık", "Bilirkişi"]
    ad: str
    detay: str
    uyari: str = ""


class RiskSeviye(str):
    """Yüksek | Orta | Düşük"""


class Risk(BaseModel):
    seviye: Literal["Yüksek", "Orta", "Düşük"]
    baslik: str
    aciklama: str
    oneri: str


# ── Ana widget yanıtı ────────────────────────────────────────────────────────

class DavaAnaliziWidget(BaseModel):
    dava_ozeti: DavaOzeti
    olaylar: list[Olay] = Field(default_factory=list)
    taraflar: list[Taraf] = Field(default_factory=list)
    riskler: list[Risk] = Field(default_factory=list)

    @field_validator("riskler")
    @classmethod
    def riskler_siralama(cls, v: list[Risk]) -> list[Risk]:
        """Riskler Yüksek → Orta → Düşük sırasında olmalı (zaten Claude sıralar ama güvence)."""
        order = {"Yüksek": 0, "Orta": 1, "Düşük": 2}
        return sorted(v, key=lambda r: order.get(r.seviye, 99))


# ── API yanıtı ───────────────────────────────────────────────────────────────

class WidgetMeta(BaseModel):
    document_ids: list[str]
    chunks_used: int
    model_id: str
    cached: bool = False


class WidgetResponse(BaseModel):
    widget: DavaAnaliziWidget
    meta: WidgetMeta
