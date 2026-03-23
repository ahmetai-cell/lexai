"""
HallucinationGuard — 3-aşamalı doğrulama birim testleri
"""
import pytest
from app.services.hallucination_guard import HallucinationGuard, CHUNK_MIN_CONFIDENCE
from app.services.embedding_service import RetrievedChunk


def make_chunk(text: str, score: float = 0.9, chunk_id: str = "test-id") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id="doc-id",
        chunk_text=text,
        page_number=1,
        section_title=None,
        article_number=None,
        similarity_score=score,
        source_metadata=None,
    )


# ── Aşama 1: Chunk Filtresi ────────────────────────────────────────


def test_filter_chunks_removes_low_confidence():
    guard = HallucinationGuard()
    chunks = [
        make_chunk("yüksek güven", score=0.85),
        make_chunk("düşük güven", score=0.60),
        make_chunk("sınırda güven", score=0.70),
    ]
    filtered, removed = guard.filter_chunks(chunks)
    assert removed == 1
    assert len(filtered) == 2
    assert all(c.similarity_score >= CHUNK_MIN_CONFIDENCE for c in filtered)


def test_filter_chunks_keeps_all_above_threshold():
    guard = HallucinationGuard()
    chunks = [make_chunk("a", score=0.80), make_chunk("b", score=0.95)]
    filtered, removed = guard.filter_chunks(chunks)
    assert removed == 0
    assert len(filtered) == 2


def test_filter_chunks_empty_list():
    guard = HallucinationGuard()
    filtered, removed = guard.filter_chunks([])
    assert filtered == []
    assert removed == 0


# ── Aşama 2: Cümle Bazlı Claim Doğrulaması ────────────────────────


def test_clean_answer_replaces_unverified_date():
    guard = HallucinationGuard()
    chunks = [make_chunk("sözleşme imzalanmıştır")]
    answer = "Sözleşme 15.03.2022 tarihinde imzalanmıştır."
    cleaned, replaced, checks = guard.clean_answer(answer, chunks)
    # Tarih chunk'ta yok → cümle değiştirilmeli
    assert len(replaced) == 1
    assert "Bu bilgi dosya kapsamında tespit edilememiştir" in cleaned


def test_clean_answer_keeps_verified_date():
    guard = HallucinationGuard()
    chunks = [make_chunk("sözleşme 15.03.2022 tarihinde imzalanmıştır")]
    answer = "Sözleşme 15.03.2022 tarihinde imzalanmıştır."
    cleaned, replaced, checks = guard.clean_answer(answer, chunks)
    assert len(replaced) == 0
    assert "15.03.2022" in cleaned


def test_clean_answer_replaces_unverified_tbk_article():
    guard = HallucinationGuard()
    chunks = [make_chunk("genel borçlar hukuku hükümleri uygulanır")]
    answer = "TBK madde 125 uyarınca alacak zamanaşımına uğrar."
    cleaned, replaced, _ = guard.clean_answer(answer, chunks)
    assert len(replaced) == 1


def test_clean_answer_keeps_verified_tbk_article():
    guard = HallucinationGuard()
    chunks = [make_chunk("TBK madde 125 uyarınca zamanaşımı on yıldır")]
    answer = "TBK madde 125 uyarınca alacak zamanaşımına uğrar."
    cleaned, replaced, _ = guard.clean_answer(answer, chunks)
    assert len(replaced) == 0


def test_clean_answer_no_claims_passes_through():
    guard = HallucinationGuard()
    chunks = [make_chunk("boş chunk")]
    answer = "Bu konuda genel değerlendirme yapılmaktadır."
    cleaned, replaced, checks = guard.clean_answer(answer, chunks)
    assert len(replaced) == 0
    assert len(checks) == 0
    assert cleaned == answer


def test_clean_answer_replaces_unverified_amount():
    guard = HallucinationGuard()
    chunks = [make_chunk("tazminat miktarı belirlenecektir")]
    answer = "Mahkeme 50.000 TL tazminata hükmetmiştir."
    cleaned, replaced, _ = guard.clean_answer(answer, chunks)
    assert len(replaced) == 1


# ── Aşama 3: Genel Jaccard + Karar Numarası ────────────────────────


@pytest.mark.asyncio
async def test_high_overlap_passes():
    guard = HallucinationGuard(sensitivity="medium")
    source = "TBK madde 112 gereğince borçlu temerrüde düşmüştür alacaklı zararını talep edebilir"
    chunks = [make_chunk(source)]
    # Yanıt kaynakla yüksek Jaccard örtüşmesine sahip (>0.80)
    answer = "TBK madde 112 gereğince borçlu temerrüde düşmüştür alacaklı zararını talep edebilir"
    result = await guard.verify(answer, chunks)
    assert result.passed
    assert not result.hallucination_flag


@pytest.mark.asyncio
async def test_low_overlap_flags():
    guard = HallucinationGuard(sensitivity="high")
    chunks = [make_chunk("kira sözleşmesi fesih bildirimi gerektirir")]
    answer = "Yargıtay E. 2023/1234 sayılı kararla tazminata hükmetmiştir"
    result = await guard.verify(answer, chunks)
    assert not result.passed
    assert result.hallucination_flag


@pytest.mark.asyncio
async def test_critical_unverified_case_number():
    guard = HallucinationGuard(sensitivity="critical")
    chunks = [make_chunk("borçlunun edimi yerine getirmediği anlaşılmıştır")]
    answer = "E. 2022/999 sayılı karar uyarınca tazminata hükmedilir"
    result = await guard.verify(answer, chunks, template_sensitivity="critical")
    # Stage 2 cümleyi değiştirdiği için hallucination_flag=True
    assert result.hallucination_flag
    # Stage 2 doğrulanamayan cümleyi yakaladı
    assert len(result.replaced_sentences) > 0


@pytest.mark.asyncio
async def test_guard_result_has_original_and_cleaned():
    guard = HallucinationGuard()
    chunks = [make_chunk("genel değerlendirme")]
    answer = "Bu genel bir değerlendirmedir."
    result = await guard.verify(answer, chunks)
    assert result.original_answer == answer
    assert isinstance(result.cleaned_answer, str)


@pytest.mark.asyncio
async def test_guard_result_tracks_replaced_sentences():
    guard = HallucinationGuard()
    chunks = [make_chunk("sadece genel bilgi içerir")]
    answer = "Sözleşme 01.01.2023 tarihinde imzalandı."
    result = await guard.verify(answer, chunks)
    assert len(result.replaced_sentences) > 0


@pytest.mark.asyncio
async def test_verification_details_populated():
    guard = HallucinationGuard()
    chunks = [make_chunk("test metni")]
    result = await guard.verify("test cümle", chunks)
    details = result.verification_details
    assert "jaccard_score" in details
    assert "jaccard_threshold" in details
    assert "source_chunk_count" in details
    assert details["source_chunk_count"] == 1


# ── Extract Claims ─────────────────────────────────────────────────


def test_extract_claims_finds_date():
    guard = HallucinationGuard()
    claims = guard._extract_claims("Sözleşme 15.03.2022 tarihinde yapıldı.")
    types = [c[0] for c in claims]
    assert "date" in types


def test_extract_claims_finds_tbk():
    guard = HallucinationGuard()
    claims = guard._extract_claims("TBK m.112 uyarınca temerrüt oluşur.")
    types = [c[0] for c in claims]
    assert "article_number" in types


def test_extract_claims_finds_case_number():
    guard = HallucinationGuard()
    claims = guard._extract_claims("E. 2023/1234 sayılı karar.")
    types = [c[0] for c in claims]
    assert "case_number" in types


def test_extract_claims_finds_amount():
    guard = HallucinationGuard()
    claims = guard._extract_claims("50.000 TL tazminata hükmedildi.")
    types = [c[0] for c in claims]
    assert "amount" in types


def test_extract_claims_finds_percentage():
    guard = HallucinationGuard()
    claims = guard._extract_claims("%50 oranında indirim uygulanır.")
    types = [c[0] for c in claims]
    assert "percentage" in types


def test_extract_claims_no_claims_empty():
    guard = HallucinationGuard()
    claims = guard._extract_claims("Bu genel bir değerlendirmedir.")
    assert claims == []


# ── Split Sentences ────────────────────────────────────────────────


def test_split_sentences_basic():
    guard = HallucinationGuard()
    text = "İlk cümle. İkinci cümle. Üçüncü cümle."
    parts = guard._split_sentences(text)
    assert len(parts) >= 2


def test_split_sentences_single():
    guard = HallucinationGuard()
    text = "Tek cümle"
    parts = guard._split_sentences(text)
    assert parts == [text]
