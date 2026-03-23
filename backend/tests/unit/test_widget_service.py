"""
WidgetService unit tests — JSON parse, Pydantic validation, error handling.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from app.schemas.widget import DavaAnaliziWidget, WidgetMeta, WidgetResponse
from app.services.widget_service import WidgetService, WidgetRequest, _MAX_CHUNKS


# ── Test verisi ───────────────────────────────────────────────────────────────

VALID_WIDGET_JSON = {
    "dava_ozeti": {
        "baslik": "Kira Sözleşmesi İhlali",
        "aciklama": "Kiracı 3 aylık kira borcunu ödememiş ve tahliye edilmek isteniyor.",
        "analiz_suresi": "45 dakika",
        "kazanma_ihtimali": 78,
        "risk_sayisi": 2,
        "eksik_belge_sayisi": 1,
    },
    "olaylar": [
        {
            "tarih": "01 Ocak 2024",
            "baslik": "Kira sözleşmesi imzalandı",
            "aciklama": "Taraflar arasında 1 yıllık kira sözleşmesi imzalandı.",
            "tip": "success",
            "kaynak": "Kira Sözleşmesi.pdf, Sayfa 1",
        }
    ],
    "taraflar": [
        {
            "rol": "Davacı",
            "ad": "Ahmet Yılmaz",
            "detay": "Ev sahibi",
            "uyari": "",
        }
    ],
    "riskler": [
        {
            "seviye": "Yüksek",
            "baslik": "Ödeme belgesi eksik",
            "aciklama": "Kiracının ödeme yaptığına dair belge bulunamadı.",
            "oneri": "Banka dekontları talep edin.",
        },
        {
            "seviye": "Düşük",
            "baslik": "Tebligat gecikmesi",
            "aciklama": "İhtarname tebligatı 3 gün geç yapılmış.",
            "oneri": "Tebligat tarihini doğrulayın.",
        },
    ],
}


def make_chunk(text="Madde 1. Kiracı aylık kira ödemekle yükümlüdür.", page=1):
    chunk = MagicMock()
    chunk.chunk_text = text
    chunk.page_number = page
    chunk.chunk_id = "c1"
    chunk.document_id = "d1"
    chunk.similarity_score = 0.85
    return chunk


# ── Şema testleri ─────────────────────────────────────────────────────────────

class TestDavaAnaliziWidget:
    def test_valid_json_parses(self):
        widget = DavaAnaliziWidget.model_validate(VALID_WIDGET_JSON)
        assert widget.dava_ozeti.kazanma_ihtimali == 78
        assert len(widget.olaylar) == 1
        assert len(widget.taraflar) == 1
        assert len(widget.riskler) == 2

    def test_kazanma_ihtimali_bounds(self):
        bad = {**VALID_WIDGET_JSON, "dava_ozeti": {**VALID_WIDGET_JSON["dava_ozeti"], "kazanma_ihtimali": 150}}
        with pytest.raises(ValidationError):
            DavaAnaliziWidget.model_validate(bad)

    def test_riskler_sorted_by_severity(self):
        shuffled = {
            **VALID_WIDGET_JSON,
            "riskler": [
                {"seviye": "Düşük", "baslik": "A", "aciklama": "a", "oneri": ""},
                {"seviye": "Yüksek", "baslik": "B", "aciklama": "b", "oneri": ""},
                {"seviye": "Orta", "baslik": "C", "aciklama": "c", "oneri": ""},
            ],
        }
        widget = DavaAnaliziWidget.model_validate(shuffled)
        assert [r.seviye for r in widget.riskler] == ["Yüksek", "Orta", "Düşük"]

    def test_invalid_olay_tip_rejected(self):
        bad_olay = {**VALID_WIDGET_JSON["olaylar"][0], "tip": "kritik"}
        bad = {**VALID_WIDGET_JSON, "olaylar": [bad_olay]}
        with pytest.raises(ValidationError):
            DavaAnaliziWidget.model_validate(bad)

    def test_invalid_taraf_rol_rejected(self):
        bad_taraf = {**VALID_WIDGET_JSON["taraflar"][0], "rol": "Hakim"}
        bad = {**VALID_WIDGET_JSON, "taraflar": [bad_taraf]}
        with pytest.raises(ValidationError):
            DavaAnaliziWidget.model_validate(bad)

    def test_empty_olaylar_allowed(self):
        widget = DavaAnaliziWidget.model_validate({**VALID_WIDGET_JSON, "olaylar": []})
        assert widget.olaylar == []


# ── _parse_json ───────────────────────────────────────────────────────────────

class TestParseJson:
    def setup_method(self):
        self.svc = WidgetService()

    def test_plain_json(self):
        raw = json.dumps(VALID_WIDGET_JSON)
        result = self.svc._parse_json(raw)
        assert result["dava_ozeti"]["kazanma_ihtimali"] == 78

    def test_json_in_code_block(self):
        raw = f"```json\n{json.dumps(VALID_WIDGET_JSON)}\n```"
        result = self.svc._parse_json(raw)
        assert result["dava_ozeti"]["baslik"] == "Kira Sözleşmesi İhlali"

    def test_json_in_generic_code_block(self):
        raw = f"```\n{json.dumps(VALID_WIDGET_JSON)}\n```"
        result = self.svc._parse_json(raw)
        assert "dava_ozeti" in result

    def test_json_with_preamble_stripped(self):
        raw = "İşte analiz sonucu:\n" + json.dumps(VALID_WIDGET_JSON)
        result = self.svc._parse_json(raw)
        assert "olaylar" in result

    def test_invalid_json_raises_value_error(self):
        with pytest.raises((ValueError, json.JSONDecodeError)):
            self.svc._parse_json("Bu bir JSON değil")

    def test_no_braces_raises_value_error(self):
        with pytest.raises(ValueError):
            self.svc._parse_json("sadece metin, hiç küme parantezi yok")


# ── _build_context ────────────────────────────────────────────────────────────

class TestBuildContext:
    def setup_method(self):
        self.svc = WidgetService()

    def test_includes_page_reference(self):
        chunk = make_chunk(text="Sözleşme metni", page=5)
        ctx = self.svc._build_context([chunk])
        assert "[Sayfa 5]" in ctx
        assert "Sözleşme metni" in ctx

    def test_long_chunk_truncated(self):
        from app.services.widget_service import _MAX_CHUNK_CHARS
        long_text = "A" * (_MAX_CHUNK_CHARS + 500)
        chunk = make_chunk(text=long_text)
        ctx = self.svc._build_context([chunk])
        assert "…" in ctx
        assert len(ctx) < _MAX_CHUNK_CHARS + 100

    def test_empty_chunks_skipped(self):
        empty = make_chunk(text="   ")
        good = make_chunk(text="Gerçek içerik", page=2)
        ctx = self.svc._build_context([empty, good])
        assert "Gerçek içerik" in ctx
        assert ctx.count("[Sayfa") == 1

    def test_multiple_chunks_separated(self):
        c1 = make_chunk(text="Birinci bölüm", page=1)
        c2 = make_chunk(text="İkinci bölüm", page=2)
        ctx = self.svc._build_context([c1, c2])
        assert "Birinci bölüm" in ctx
        assert "İkinci bölüm" in ctx
        assert "\n\n" in ctx


# ── analyze — tam akış ────────────────────────────────────────────────────────

class TestAnalyze:
    @pytest.mark.asyncio
    async def test_successful_analysis(self):
        svc = WidgetService()

        mock_hybrid_result = MagicMock()
        mock_hybrid_result.chunks = [make_chunk()]

        with patch("app.services.widget_service.hybrid_retriever") as mock_retriever, \
             patch("app.services.widget_service.bedrock_service") as mock_bedrock, \
             patch("app.services.widget_service.audit_service") as mock_audit:

            mock_retriever.search = AsyncMock(return_value=mock_hybrid_result)
            mock_bedrock.invoke = AsyncMock(return_value=json.dumps(VALID_WIDGET_JSON))
            mock_audit.log_rag_query = AsyncMock()

            req = WidgetRequest(
                document_ids=["doc-1"],
                tenant_id="tenant-1",
                user_id="user-1",
            )
            result = await svc.analyze(req, db=AsyncMock())

        assert isinstance(result, WidgetResponse)
        assert result.widget.dava_ozeti.kazanma_ihtimali == 78
        assert result.meta.chunks_used == 1
        assert result.meta.document_ids == ["doc-1"]

    @pytest.mark.asyncio
    async def test_empty_retrieval_raises(self):
        from app.core.exceptions import RAGRetrievalError
        svc = WidgetService()

        mock_hybrid_result = MagicMock()
        mock_hybrid_result.chunks = []

        with patch("app.services.widget_service.hybrid_retriever") as mock_retriever:
            mock_retriever.search = AsyncMock(return_value=mock_hybrid_result)

            with pytest.raises(RAGRetrievalError):
                await svc.analyze(
                    WidgetRequest(document_ids=["x"], tenant_id="t", user_id="u"),
                    db=AsyncMock(),
                )

    @pytest.mark.asyncio
    async def test_audit_error_does_not_raise(self):
        """Audit log hatası yanıtı engellememeli."""
        svc = WidgetService()

        mock_hybrid_result = MagicMock()
        mock_hybrid_result.chunks = [make_chunk()]

        with patch("app.services.widget_service.hybrid_retriever") as mock_retriever, \
             patch("app.services.widget_service.bedrock_service") as mock_bedrock, \
             patch("app.services.widget_service.audit_service") as mock_audit:

            mock_retriever.search = AsyncMock(return_value=mock_hybrid_result)
            mock_bedrock.invoke = AsyncMock(return_value=json.dumps(VALID_WIDGET_JSON))
            mock_audit.log_rag_query = AsyncMock(side_effect=RuntimeError("DB down"))

            result = await svc.analyze(
                WidgetRequest(document_ids=["d"], tenant_id="t", user_id="u"),
                db=AsyncMock(),
            )

        assert result.widget is not None  # audit hatası olsa bile döndü

    @pytest.mark.asyncio
    async def test_bedrock_invalid_json_raises_value_error(self):
        svc = WidgetService()

        mock_hybrid_result = MagicMock()
        mock_hybrid_result.chunks = [make_chunk()]

        with patch("app.services.widget_service.hybrid_retriever") as mock_retriever, \
             patch("app.services.widget_service.bedrock_service") as mock_bedrock:

            mock_retriever.search = AsyncMock(return_value=mock_hybrid_result)
            mock_bedrock.invoke = AsyncMock(return_value="Özür dilerim, analiz yapamadım.")

            with pytest.raises(ValueError):
                await svc.analyze(
                    WidgetRequest(document_ids=["d"], tenant_id="t", user_id="u"),
                    db=AsyncMock(),
                )
