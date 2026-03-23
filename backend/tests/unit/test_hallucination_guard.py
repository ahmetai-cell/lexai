import pytest
from app.services.hallucination_guard import HallucinationGuard
from app.services.embedding_service import RetrievedChunk


def make_chunk(text: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="test-id",
        document_id="doc-id",
        chunk_text=text,
        page_number=1,
        section_title=None,
        article_number=None,
        similarity_score=0.9,
        source_metadata=None,
    )


@pytest.mark.asyncio
async def test_high_overlap_passes():
    guard = HallucinationGuard(sensitivity="medium")
    source = "TBK madde 112 gereğince borçlu temerrüde düşmüştür alacaklı zararını talep edebilir"
    chunks = [make_chunk(source)]
    answer = "TBK madde 112 gereğince borçlu temerrüde düşmüştür"
    result = await guard.verify(answer, chunks)
    assert result.passed
    assert not result.hallucination_flag


@pytest.mark.asyncio
async def test_low_overlap_flags():
    guard = HallucinationGuard(sensitivity="high")
    chunks = [make_chunk("kira sözleşmesi fesih bildirimi gerektirir")]
    answer = "Yargıtay 4. HD 2023/1234 sayılı kararla tazminata hükmetmiştir"
    result = await guard.verify(answer, chunks)
    assert not result.passed
    assert result.hallucination_flag


@pytest.mark.asyncio
async def test_critical_unverified_case_number():
    guard = HallucinationGuard(sensitivity="critical")
    chunks = [make_chunk("borçlunun edimi yerine getirmediği anlaşılmıştır")]
    answer = "E. 2022/999 sayılı karar uyarınca tazminata hükmedilir"
    result = await guard.verify(answer, chunks, template_sensitivity="critical")
    assert result.hallucination_flag
    assert len(result.unverified_case_numbers) > 0
