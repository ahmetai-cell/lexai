"""
LexAI Legal Document Chunker

Chunking kuralları (kullanıcı spesifikasyonu):
1. 'Madde X' ile başlayan satır HER ZAMAN yeni chunk başlangıcıdır
2. Chunk asla 'bkz.', 'yukarıda', 'aşağıda', 'ilerleyen', 'önceki' ile BITEMEZ
   → bağlam tamamlanana kadar devam et
3. Minimum 50 kelime, maksimum 800 kelime
4. Her chunk'a [Belge:X, Sayfa:Y, Bölüm:Z] etiketi eklenir
"""
import re
from dataclasses import dataclass

# ── Pattern'lar ────────────────────────────────────────────────────────────────

# Zorunlu chunk sınır desenleri (her biri yeni chunk başlatır)
MANDATORY_BOUNDARY = re.compile(
    r"^(?:"
    r"Madde\s+\d+|MADDE\s+\d+"                  # Madde 1 / MADDE 1
    r"|m\.\s*\d+"                                # m.1
    r"|Ek\s+Madde\s+\d+"                         # Ek Madde
    r"|Geçici\s+Madde\s+\d+"                     # Geçici Madde
    r"|(?:BÖLÜM|Bölüm|KESİM|Kısım)\s+[IVXivx\d]+"  # Bölüm I
    r")",
    re.MULTILINE,
)

# Chunk'ın bu kelimelerle BİTMESİ yasak – bağlam belirsiz kalır
DANGLING_REFERENCE = re.compile(
    r"\b(?:bkz|yukarıda|aşağıda|ilerleyen|önceki|ilgili|söz konusu|bahsi geçen)"
    r"[\s.,;:]*$",
    re.IGNORECASE,
)

# Madde numarası çıkarma (etiketleme için)
ARTICLE_NUMBER_RE = re.compile(r"(?:Madde|MADDE|m\.)\s*(\d+(?:[/.-]\d+)?)")

MIN_WORDS = 50
MAX_WORDS = 800


@dataclass
class TextChunk:
    text: str
    chunk_index: int
    page_number: int | None
    section_title: str | None
    article_number: str | None
    char_start: int
    char_end: int
    word_count: int
    label: str  # [Belge:X, Sayfa:Y, Bölüm:Z]
    low_confidence: bool = False  # OCR'dan gelen düşük güvenli işaret


class LegalDocumentChunker:
    def __init__(
        self,
        document_name: str = "Belge",
        min_words: int = MIN_WORDS,
        max_words: int = MAX_WORDS,
    ):
        self.document_name = document_name
        self.min_words = min_words
        self.max_words = max_words

    def chunk(
        self,
        text: str,
        page_map: dict[int, int] | None = None,
    ) -> list[TextChunk]:
        """
        Metni hukuki kurallara göre chunk'lara böl.

        Args:
            text: OCR'dan gelen tam metin
            page_map: {char_offset: page_number} – sayfa tespiti için
        """
        # 1. Zorunlu sınırlara göre bölümlere ayır
        sections = self._split_on_mandatory_boundaries(text)

        # 2. Her bölümü boyut kuralına göre alt parçalara böl
        raw_chunks: list[tuple[str, int, int, str | None, str | None]] = []
        # (text, char_start, char_end, section_title, article_number)

        for sec_text, sec_title, sec_article, sec_start in sections:
            sub = self._split_by_word_count(sec_text, sec_start)
            for sub_text, sub_start, sub_end in sub:
                raw_chunks.append((sub_text, sub_start, sub_end, sec_title, sec_article))

        # 3. Dangling reference kuralını uygula (küçük parçaları birleştir)
        merged = self._fix_dangling_references(raw_chunks)

        # 4. Minimum kelime kuralını uygula (çok kısa parçaları birleştir)
        final = self._merge_short_chunks(merged)

        # 5. Sonuçları TextChunk nesnelerine dönüştür ve etiketle
        result: list[TextChunk] = []
        for idx, (chunk_text, c_start, c_end, s_title, s_article) in enumerate(final):
            page = self._get_page(c_start, page_map)
            section_label = s_title or s_article or "Genel"
            label = f"[Belge:{self.document_name}, Sayfa:{page or '?'}, Bölüm:{section_label}]"

            stripped = chunk_text.strip()
            if not stripped:
                continue

            result.append(TextChunk(
                text=stripped,
                chunk_index=idx,
                page_number=page,
                section_title=s_title,
                article_number=s_article,
                char_start=c_start,
                char_end=c_end,
                word_count=len(stripped.split()),
                label=label,
                low_confidence="MANUEL İNCELEME" in chunk_text,
            ))

        return result

    # ── Yardımcı metodlar ───────────────────────────────────────────────────

    def _split_on_mandatory_boundaries(
        self, text: str
    ) -> list[tuple[str, str | None, str | None, int]]:
        """
        KURAL 1: 'Madde X' ile başlayan satır her zaman yeni chunk başlangıcıdır.
        Returns: [(text, section_title, article_number, char_offset)]
        """
        boundaries: list[tuple[int, str]] = []
        for match in MANDATORY_BOUNDARY.finditer(text):
            boundaries.append((match.start(), match.group().strip()))

        if not boundaries:
            return [(text, None, None, 0)]

        results: list[tuple[str, str | None, str | None, int]] = []
        for i, (pos, heading) in enumerate(boundaries):
            end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)
            article_match = ARTICLE_NUMBER_RE.search(heading)
            article_num = article_match.group(1) if article_match else None
            results.append((text[pos:end], heading, article_num, pos))

        # Baştaki "giriş" metnini de ekle (ilk sınırdan önce)
        if boundaries[0][0] > 0:
            preamble = text[: boundaries[0][0]]
            if preamble.strip():
                results.insert(0, (preamble, "Giriş", None, 0))

        return results

    def _split_by_word_count(
        self, text: str, base_offset: int
    ) -> list[tuple[str, int, int]]:
        """
        KURAL 3: Maksimum 800 kelime.
        Cümle sınırlarına hizalayarak böl.
        """
        words = text.split()
        if len(words) <= self.max_words:
            return [(text, base_offset, base_offset + len(text))]

        chunks: list[tuple[str, int, int]] = []
        current_pos = 0

        while current_pos < len(text):
            # max_words kadar al
            word_list = text[current_pos:].split()
            target_text = " ".join(word_list[: self.max_words])

            # Cümle sınırına hizala (son '.', '!' veya '?' bul)
            boundary = -1
            for sep in (".\n", ".\t", ". ", "!\n", "? ", "!\t"):
                idx = target_text.rfind(sep)
                if idx > len(target_text) // 2:
                    boundary = max(boundary, idx + 1)

            if boundary == -1:
                # Cümle sınırı bulunamazsa kelime sınırında kes
                boundary = len(target_text)

            chunk_text = text[current_pos: current_pos + boundary].strip()
            end_pos = current_pos + boundary

            chunks.append((chunk_text, base_offset + current_pos, base_offset + end_pos))
            current_pos = end_pos

            # Boşlukları atla
            while current_pos < len(text) and text[current_pos].isspace():
                current_pos += 1

        return chunks

    def _fix_dangling_references(
        self,
        chunks: list[tuple[str, int, int, str | None, str | None]],
    ) -> list[tuple[str, int, int, str | None, str | None]]:
        """
        KURAL 2: Chunk 'bkz.', 'yukarıda', 'aşağıda' vb. ile bitemez.
        Böyle biten chunk'u bir sonrakiyle birleştir.
        """
        result: list[tuple[str, int, int, str | None, str | None]] = []
        i = 0
        while i < len(chunks):
            text, start, end, title, article = chunks[i]

            # Dangling reference tespiti
            if DANGLING_REFERENCE.search(text.strip()) and i + 1 < len(chunks):
                # Bir sonrakiyle birleştir
                next_text, _, next_end, next_title, next_article = chunks[i + 1]
                merged_text = text + " " + next_text
                result.append((
                    merged_text,
                    start,
                    next_end,
                    title or next_title,
                    article or next_article,
                ))
                i += 2
            else:
                result.append((text, start, end, title, article))
                i += 1

        return result

    def _merge_short_chunks(
        self,
        chunks: list[tuple[str, int, int, str | None, str | None]],
    ) -> list[tuple[str, int, int, str | None, str | None]]:
        """
        KURAL 3: Minimum 50 kelime.
        Çok kısa chunk'ları bir öncekiyle birleştir.
        """
        result: list[tuple[str, int, int, str | None, str | None]] = []

        for chunk_text, c_start, c_end, s_title, s_article in chunks:
            word_count = len(chunk_text.split())
            if word_count < self.min_words and result:
                # Bir öncekine ekle
                prev_text, prev_start, _, prev_title, prev_article = result[-1]
                # Birleştirilmiş boyutu kontrol et
                merged_words = len(prev_text.split()) + word_count
                if merged_words <= self.max_words:
                    result[-1] = (
                        prev_text + "\n" + chunk_text,
                        prev_start,
                        c_end,
                        prev_title or s_title,
                        prev_article or s_article,
                    )
                    continue
            result.append((chunk_text, c_start, c_end, s_title, s_article))

        return result

    def _get_page(self, char_offset: int, page_map: dict[int, int] | None) -> int | None:
        if not page_map:
            return None
        current_page = None
        for offset in sorted(page_map):
            if offset <= char_offset:
                current_page = page_map[offset]
        return current_page
