from app.rag.citation_tracker import CitationTracker
from app.services.embedding_service import RetrievedChunk


def make_chunk(chunk_id: str, doc_id: str, page: int) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=doc_id,
        chunk_text="test text",
        page_number=page,
        section_title=None,
        article_number=None,
        similarity_score=0.9,
        source_metadata=None,
    )


def test_extracts_source_references():
    tracker = CitationTracker()
    chunks = [
        make_chunk("chunk-1", "doc-1", 5),
        make_chunk("chunk-2", "doc-2", 12),
    ]
    answer = "TBK çerçevesinde değerlendirme yapıldı [Kaynak 1: Sözleşme, Sayfa 5] ve ayrıca [Kaynak 2: Karar, Sayfa 12] incelendi."
    result = tracker.extract(answer, chunks)
    assert len(result["sources"]) == 2
    assert result["sources"][0]["chunk_id"] == "chunk-1"
    assert result["sources"][1]["chunk_id"] == "chunk-2"


def test_extracts_law_references():
    tracker = CitationTracker()
    answer = "Borçlunun yükümlülüğü [TBK m.112] ve tazminat [TBK m.49] kapsamında değerlendirilir."
    result = tracker.extract(answer, [])
    assert len(result["law_refs"]) == 2
    assert result["law_refs"][0]["law"] == "TBK"
    assert result["law_refs"][0]["article"] == "112"


def test_extracts_case_references():
    tracker = CitationTracker()
    answer = "[Yargıtay 4. HD, 15.03.2022, E.2022/1234] emsal gösterilmiştir."
    result = tracker.extract(answer, [])
    assert len(result["case_refs"]) == 1
    assert result["case_refs"][0]["chamber"] == "4"
    assert result["case_refs"][0]["case_no"] == "2022/1234"
