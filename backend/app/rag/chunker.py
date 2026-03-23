"""
Türkiye hukuk belgesi farkındalıklı metin parçalayıcı.
Kanun maddeleri, bölüm başlıkları ve paragraf sınırlarına göre böler.
"""
import re
from dataclasses import dataclass

# Türk hukuk belgelerinde yaygın madde başlığı kalıpları
ARTICLE_HEADING = re.compile(r"^(Madde\s+\d+|MADDE\s+\d+|m\.\s*\d+)", re.MULTILINE)
SECTION_HEADING = re.compile(r"^(BÖLÜM|Bölüm|KESİM|KISIM)\s+[IVXivx\d]+", re.MULTILINE)

TARGET_TOKENS = 600
OVERLAP_TOKENS = 100
APPROX_CHARS_PER_TOKEN = 4  # Türkçe için yaklaşık değer


@dataclass
class TextChunk:
    text: str
    chunk_index: int
    page_number: int | None
    section_title: str | None
    article_number: str | None
    char_start: int
    char_end: int


class LegalDocumentChunker:
    def chunk(self, text: str, page_map: dict[int, int] | None = None) -> list[TextChunk]:
        """
        Metni anlamlı hukuki parçalara böl.
        page_map: {char_offset: page_number}
        """
        # Önce madde başlıklarına göre böl
        splits = self._split_on_articles(text)
        chunks = []
        idx = 0

        for section_text, section_title, article_number, char_start in splits:
            sub_chunks = self._split_by_tokens(section_text, char_start)
            for sub_text, sub_start, sub_end in sub_chunks:
                page = self._get_page(sub_start, page_map)
                chunks.append(
                    TextChunk(
                        text=sub_text.strip(),
                        chunk_index=idx,
                        page_number=page,
                        section_title=section_title,
                        article_number=article_number,
                        char_start=sub_start,
                        char_end=sub_end,
                    )
                )
                idx += 1

        return [c for c in chunks if len(c.text) > 50]

    def _split_on_articles(
        self, text: str
    ) -> list[tuple[str, str | None, str | None, int]]:
        """Madde başlıklarına göre böl."""
        results = []
        positions = [(m.start(), m.group()) for m in ARTICLE_HEADING.finditer(text)]

        if not positions:
            return [(text, None, None, 0)]

        for i, (pos, heading) in enumerate(positions):
            end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
            article_num = re.search(r"\d+", heading)
            results.append((
                text[pos:end],
                heading.strip(),
                article_num.group() if article_num else None,
                pos,
            ))

        return results

    def _split_by_tokens(
        self, text: str, base_offset: int
    ) -> list[tuple[str, int, int]]:
        """Uzun bölümleri token boyutuna göre böl (overlap ile)."""
        max_chars = TARGET_TOKENS * APPROX_CHARS_PER_TOKEN
        overlap_chars = OVERLAP_TOKENS * APPROX_CHARS_PER_TOKEN

        if len(text) <= max_chars:
            return [(text, base_offset, base_offset + len(text))]

        chunks = []
        start = 0
        while start < len(text):
            end = min(start + max_chars, len(text))
            # Cümle sınırına hizala
            if end < len(text):
                boundary = text.rfind(".", start, end)
                if boundary > start:
                    end = boundary + 1
            chunk_text = text[start:end]
            chunks.append((chunk_text, base_offset + start, base_offset + end))
            start = end - overlap_chars
        return chunks

    def _get_page(self, char_offset: int, page_map: dict[int, int] | None) -> int | None:
        if not page_map:
            return None
        page = None
        for offset, p in sorted(page_map.items()):
            if offset <= char_offset:
                page = p
        return page
