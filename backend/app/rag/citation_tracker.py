"""
Citation Tracker – Yanıttaki kaynak referanslarını parse eder ve chunk'larla eşleştirir.
"""
import re
from app.services.embedding_service import RetrievedChunk

# [Kaynak N: Belge Adı, Sayfa X]
SOURCE_PATTERN = re.compile(r"\[Kaynak\s+(\d+)(?::\s*([^,\]]+?))?(?:,\s*Sayfa\s*(\d+))?\]")
# [TBK m.X] / [TTK m.X]
LAW_PATTERN = re.compile(r"\[(TBK|TTK|HMK|TMK|TCK|İK)\s+m\.\s*(\d+(?:/\d+)?)\]")
# [Yargıtay X. HD, tarih, E.YYYY/NNNN]
CASE_PATTERN = re.compile(r"\[Yargıtay\s+(\d+)\.\s*HD,\s*([^,\]]+),\s*E\.(\d{4}/\d+)\]")


class CitationTracker:
    def extract(
        self,
        answer: str,
        chunks: list[RetrievedChunk],
    ) -> dict:
        """
        Yanıttaki atıfları parse eder ve chunk ID'leriyle eşleştirir.
        Returns:
            {
                "sources": [{"ref": "[Kaynak 1]", "chunk_id": "...", "document_id": "..."}],
                "law_refs": [{"law": "TBK", "article": "179"}],
                "case_refs": [{"chamber": "4", "date": "...", "case_no": "..."}]
            }
        """
        chunk_map = {str(i + 1): c for i, c in enumerate(chunks)}

        sources = []
        for match in SOURCE_PATTERN.finditer(answer):
            ref_num = match.group(1)
            chunk = chunk_map.get(ref_num)
            sources.append({
                "ref": match.group(0),
                "ref_number": ref_num,
                "chunk_id": chunk.chunk_id if chunk else None,
                "document_id": chunk.document_id if chunk else None,
                "page_number": match.group(3) or (chunk.page_number if chunk else None),
            })

        law_refs = [
            {"law": m.group(1), "article": m.group(2)}
            for m in LAW_PATTERN.finditer(answer)
        ]

        case_refs = [
            {"chamber": m.group(1), "date": m.group(2).strip(), "case_no": m.group(3)}
            for m in CASE_PATTERN.finditer(answer)
        ]

        return {
            "sources": sources,
            "law_refs": law_refs,
            "case_refs": case_refs,
            "total_citations": len(sources) + len(law_refs) + len(case_refs),
        }
