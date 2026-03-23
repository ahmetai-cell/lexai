-- pgvector ivfflat indeks ve benzerlik arama fonksiyonu
-- Bu dosya init.sql'den sonra çalıştırılır

-- ── Benzerlik arama fonksiyonu ────────────────────
CREATE OR REPLACE FUNCTION match_document_chunks(
    query_embedding vector(1536),
    p_tenant_id UUID,
    p_document_ids UUID[] DEFAULT NULL,
    match_count INT DEFAULT 8,
    min_similarity FLOAT DEFAULT 0.72
)
RETURNS TABLE (
    id UUID,
    document_id UUID,
    chunk_text TEXT,
    chunk_index INT,
    page_number INT,
    section_title VARCHAR,
    article_number VARCHAR,
    source_metadata JSONB,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        dc.id,
        dc.document_id,
        dc.chunk_text,
        dc.chunk_index,
        dc.page_number,
        dc.section_title,
        dc.article_number,
        dc.source_metadata,
        1 - (dc.embedding <=> query_embedding) AS similarity
    FROM document_chunks dc
    WHERE
        dc.tenant_id = p_tenant_id
        AND dc.embedding IS NOT NULL
        AND (p_document_ids IS NULL OR dc.document_id = ANY(p_document_ids))
        AND 1 - (dc.embedding <=> query_embedding) >= min_similarity
    ORDER BY dc.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- ivfflat index (public schema için – tenant schema'larında create_tenant_schema ile oluşturulur)
-- Bu index üretimde her tenant schema'sında ayrı oluşturulmalıdır:
-- CREATE INDEX ON tenant_{slug}.document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Session düzeyinde ivfflat probe sayısı (accuracy vs speed trade-off)
-- SET ivfflat.probes = 10;  -- Sorgu sırasında uygulanır
