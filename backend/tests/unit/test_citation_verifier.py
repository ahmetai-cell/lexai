"""
CitationVerifier — birim testleri
"""
import pytest
from app.rag.citation_verifier import CitationVerifier, MIN_OVERLAP_RATIO
from app.services.embedding_service import RetrievedChunk


def make_chunk(
    text: str,
    chunk_id: str = "c1",
    page: int | None = None,
    score: float = 0.85,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id="doc-1",
        chunk_text=text,
        page_number=page,
        section_title=None,
        article_number=None,
        similarity_score=score,
        source_metadata=None,
    )


# ── Temel doğrulama ────────────────────────────────────────────────


def test_no_citations_returns_original_unchanged():
    verifier = CitationVerifier()
    answer = "Bu yanıtta kaynak atıfı bulunmamaktadır."
    chunks = [make_chunk("herhangi bir chunk metni")]
    report = verifier.verify(answer, chunks)
    assert report.verified_answer == answer
    assert report.total_citations == 0
    assert report.error_count == 0


def test_verified_citation_no_warning():
    verifier = CitationVerifier()
    chunk_text = "temerrüt halinde faiz işler borçlu ödeme yapmak zorundadır"
    chunks = [make_chunk(chunk_text, chunk_id="c1", page=3)]
    # Kaynak 1, atıf metni chunk ile örtüşüyor
    answer = "Temerrüt halinde faiz işlemeye başlar [Kaynak 1: Sözleşme.pdf, Sayfa 3]."
    report = verifier.verify(answer, chunks)
    assert report.error_count == 0
    assert "ATIF HATASI" not in report.verified_answer


def test_unverified_citation_inserts_warning():
    verifier = CitationVerifier()
    chunks = [make_chunk("tamamen farklı bir içerik burada", chunk_id="c1", page=1)]
    answer = "Yargıtay 2022 yılında bu konuda karar vermiştir [Kaynak 1: Karar.pdf, Sayfa 5]."
    report = verifier.verify(answer, chunks)
    assert report.error_count > 0
    assert "ATIF HATASI" in report.verified_answer


def test_missing_ref_number_inserts_warning():
    verifier = CitationVerifier()
    chunks = [make_chunk("bir chunk")]  # sadece 1 chunk
    # Kaynak 5 yok
    answer = "Bu bilgi önemlidir [Kaynak 5: Belge.pdf, Sayfa 2]."
    report = verifier.verify(answer, chunks)
    assert report.error_count > 0


def test_page_mismatch_inserts_warning():
    verifier = CitationVerifier()
    # Chunk page=3 ama atıf page=7 diyor
    chunks = [make_chunk("borçlunun temerrüdü", chunk_id="c1", page=3)]
    answer = "Borçlu temerrüde düşmüştür [Kaynak 1: Sözleşme.pdf, Sayfa 7]."
    report = verifier.verify(answer, chunks)
    assert report.error_count > 0
    check = report.checks[0]
    assert not check.verified
    assert "Sayfa uyuşmazlığı" in check.reason


# ── Çoklu atıf ────────────────────────────────────────────────────


def test_multiple_citations_mixed():
    verifier = CitationVerifier()
    c1 = make_chunk("temerrüt faiz borçlu alacaklı", chunk_id="c1", page=1)
    c2 = make_chunk("kira sözleşmesi fesih ihbar", chunk_id="c2", page=2)
    chunks = [c1, c2]
    # İlk atıf geçerli, ikinci atıf hatalı sayfa
    answer = (
        "Temerrüt durumunda faiz işler [Kaynak 1, Sayfa 1]. "
        "Fesih bildirim süresine uymak gerekir [Kaynak 2, Sayfa 9]."
    )
    report = verifier.verify(answer, chunks)
    assert report.total_citations == 2
    # İkinci atıf sayfa uyumsuzluğu yüzünden hatalı
    assert report.error_count >= 1


def test_multiple_citations_all_valid():
    verifier = CitationVerifier()
    c1 = make_chunk("sözleşme imzalandı taraflar arasında", chunk_id="c1", page=1)
    c2 = make_chunk("tazminat miktarı mahkemece belirlendi", chunk_id="c2", page=2)
    chunks = [c1, c2]
    answer = (
        "Sözleşme taraflar arasında imzalandı [Kaynak 1, Sayfa 1]. "
        "Tazminat miktarı mahkemece belirlendi [Kaynak 2, Sayfa 2]."
    )
    report = verifier.verify(answer, chunks)
    assert report.total_citations == 2


# ── Audit entries ─────────────────────────────────────────────────


def test_audit_entries_only_for_failures():
    verifier = CitationVerifier()
    chunks = [make_chunk("alakasız içerik", chunk_id="c1", page=1)]
    answer = "Test verisi [Kaynak 1, Sayfa 99]."
    report = verifier.verify(answer, chunks)
    entries = report.audit_entries()
    assert all("event" in e for e in entries)
    assert all("ref_number" in e for e in entries)
    assert len(entries) == report.error_count


def test_audit_entries_empty_when_all_valid():
    verifier = CitationVerifier()
    chunks = [make_chunk("borçlu ödemeyi yapmak zorundadır", chunk_id="c1", page=1)]
    answer = "Borçlu ödeme yapmak zorundadır [Kaynak 1, Sayfa 1]."
    report = verifier.verify(answer, chunks)
    # Geçerli atıflar için audit entry üretilmez
    entries = report.audit_entries()
    assert entries == []


# ── Overlap hesabı ────────────────────────────────────────────────


def test_compute_overlap_identical_texts():
    verifier = CitationVerifier()
    text = "temerrüt halinde faiz işler"
    overlap = verifier._compute_overlap(text, text)
    assert overlap == pytest.approx(1.0)


def test_compute_overlap_no_common_words():
    verifier = CitationVerifier()
    overlap = verifier._compute_overlap("elma armut kiraz", "masa sandalye dolap")
    assert overlap == pytest.approx(0.0)


def test_compute_overlap_partial():
    verifier = CitationVerifier()
    sentence = "temerrüt halinde faiz işler"
    chunk = "temerrüt durumunda başka koşullar da geçerli"
    overlap = verifier._compute_overlap(sentence, chunk)
    assert 0.0 < overlap < 1.0


def test_compute_overlap_empty_sentence_returns_zero():
    verifier = CitationVerifier()
    overlap = verifier._compute_overlap("", "herhangi bir metin")
    assert overlap == 0.0


# ── Context sentence extraction ───────────────────────────────────


def test_extract_context_sentence_from_full_text():
    verifier = CitationVerifier()
    # citation_pos bir atıf metninin başına işaret etmeli
    text = "İlk cümle buraya. İkinci cümle önemlidir [Kaynak 1]. Üçüncü cümle."
    pos = text.index("[Kaynak 1]")
    context = verifier._extract_context_sentence(text, pos)
    assert len(context) > 0


# ── VerificationReport.has_errors ─────────────────────────────────


def test_report_has_errors_false_when_clean():
    verifier = CitationVerifier()
    chunks = [make_chunk("test")]
    report = verifier.verify("atıfsız metin", chunks)
    assert not report.has_errors


def test_report_has_errors_true_when_bad_citation():
    verifier = CitationVerifier()
    chunks = [make_chunk("alakasız içerik", chunk_id="c1", page=1)]
    answer = "Önemli bilgi [Kaynak 99, Sayfa 1]."
    report = verifier.verify(answer, chunks)
    assert report.has_errors


# ── MIN_OVERLAP_RATIO sabiti ───────────────────────────────────────


def test_custom_min_overlap_stricter():
    verifier = CitationVerifier(min_overlap=0.80)
    chunk_text = "temerrüt faiz işler"
    chunks = [make_chunk(chunk_text, chunk_id="c1", page=1)]
    # Düşük örtüşme → yüksek eşikle başarısız olmalı
    answer = "Borçlu temerrüde düştüğünde çeşitli sonuçlar doğar [Kaynak 1, Sayfa 1]."
    report = verifier.verify(answer, chunks)
    assert report.error_count > 0
