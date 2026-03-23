import pytest
from app.rag.chunker import LegalDocumentChunker, DANGLING_REFERENCE


def make_chunker(doc_name: str = "Test Sözleşmesi") -> LegalDocumentChunker:
    return LegalDocumentChunker(document_name=doc_name, min_words=5, max_words=50)


# ── Kural 1: Madde sınırları ───────────────────────────────────────────────

def test_article_boundary_splits():
    """Madde X her zaman yeni chunk başlatır."""
    text = (
        "Giriş paragrafı burada yer alır ve genel bilgi içerir.\n\n"
        "Madde 1 Bu madde tarafları tanımlar ve kapsam belirler.\n\n"
        "Madde 2 Bu madde yükümlülükleri düzenler ve sorumlulukları belirler."
    )
    chunker = make_chunker()
    chunks = chunker.chunk(text)
    article_numbers = [c.article_number for c in chunks if c.article_number]
    assert "1" in article_numbers
    assert "2" in article_numbers


def test_madde_keyword_variants():
    """MADDE (büyük harf) de sınır oluşturur."""
    text = "MADDE 1 Kapsam maddesidir.\nMADDE 2 Tanımlar maddesidir."
    chunker = make_chunker()
    chunks = chunker.chunk(text)
    assert len(chunks) >= 2


# ── Kural 2: Dangling reference ────────────────────────────────────────────

def test_dangling_bkz_merged():
    """'bkz.' ile biten chunk bir sonrakiyle birleştirilir."""
    text = (
        "Madde 1 Bu hüküm aşağıdaki kurallara tabidir bkz.\n"
        "Madde 2 İlgili hükümlerin tamamı bu maddede açıklanmıştır."
    )
    chunker = make_chunker()
    chunks = chunker.chunk(text)
    # Bkz. chunk'u bağımsız olmamalı
    for chunk in chunks:
        assert not DANGLING_REFERENCE.search(chunk.text.strip()), (
            f"Dangling reference chunk geçti: {chunk.text[:80]}"
        )


def test_dangling_yukarda_merged():
    """'yukarıda' ile biten chunk birleştirilir."""
    text = (
        "Madde 3 Söz konusu yükümlülükler yukarıda\n"
        "Madde 4 belirtilen hususlar çerçevesinde değerlendirilir ve uygulanır."
    )
    chunker = make_chunker()
    chunks = chunker.chunk(text)
    for chunk in chunks:
        assert not DANGLING_REFERENCE.search(chunk.text.strip())


# ── Kural 3: Boyut sınırları ───────────────────────────────────────────────

def test_min_word_count():
    """Hiçbir chunk 5 kelimeden az olmamalı (test min=5)."""
    text = "\n".join(
        f"Madde {i} Bu madde {i}. yükümlülüğü tanımlar ve kapsar."
        for i in range(1, 10)
    )
    chunker = make_chunker()
    chunks = chunker.chunk(text)
    for chunk in chunks:
        assert chunk.word_count >= 5, f"Kısa chunk: {chunk.text}"


def test_max_word_count():
    """Hiçbir chunk 50 kelimeden fazla olmamalı (test max=50)."""
    long_text = "Madde 1 " + " ".join([f"kelime{i}" for i in range(200)])
    chunker = make_chunker()
    chunks = chunker.chunk(long_text)
    for chunk in chunks:
        assert chunk.word_count <= 60, f"Uzun chunk ({chunk.word_count}): {chunk.text[:60]}"


# ── Kural 4: Etiketleme ────────────────────────────────────────────────────

def test_chunk_label_format():
    """Her chunk [Belge:X, Sayfa:Y, Bölüm:Z] etiketine sahip olmalı."""
    text = "Madde 1 Bu sözleşme taraflar arasında akdedilmiştir ve geçerlidir."
    chunker = LegalDocumentChunker(document_name="Kira Sözleşmesi")
    chunks = chunker.chunk(text)
    assert len(chunks) > 0
    for chunk in chunks:
        assert "Belge:Kira Sözleşmesi" in chunk.label
        assert "Sayfa:" in chunk.label
        assert "Bölüm:" in chunk.label


def test_low_confidence_marked():
    """OCR düşük güven işaretli metin chunk'ta low_confidence=True olmalı."""
    text = "Madde 1 ⚠️ [MANUEL İNCELEME GEREKLİ – Sayfa 3: Güven: %65] el yazısı kısmı burada."
    chunker = make_chunker()
    chunks = chunker.chunk(text)
    assert any(c.low_confidence for c in chunks)
