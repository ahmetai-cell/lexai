-- LexAI – PostgreSQL Başlangıç Kurulumu
-- Bu dosya docker-entrypoint-initdb.d/ tarafından ilk başlatmada çalıştırılır

-- pgvector eklentisini etkinleştir
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- Metin benzerliği için

-- ── Ana tablolar (public schema) ─────────────────

CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    slug VARCHAR(64) UNIQUE NOT NULL,
    display_name VARCHAR(256) NOT NULL,
    schema_name VARCHAR(64) UNIQUE NOT NULL,
    tier VARCHAR(32) DEFAULT 'starter' NOT NULL,
    max_documents INTEGER DEFAULT 500,
    max_users INTEGER DEFAULT 10,
    api_rate_limit INTEGER DEFAULT 60,
    monthly_token_quota BIGINT DEFAULT 5000000,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email VARCHAR(256) NOT NULL,
    full_name VARCHAR(256) NOT NULL,
    hashed_password VARCHAR(512) NOT NULL,
    role VARCHAR(32) DEFAULT 'attorney',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, email)
);

CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(256) NOT NULL,
    key_hash VARCHAR(128) UNIQUE NOT NULL,
    key_prefix VARCHAR(16) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);

-- ── Tenant schema oluşturma prosedürü ─────────────
CREATE OR REPLACE FUNCTION create_tenant_schema(p_slug TEXT)
RETURNS VOID AS $$
DECLARE
    v_schema TEXT := 'tenant_' || p_slug;
BEGIN
    EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I', v_schema);

    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.documents (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id UUID NOT NULL,
            uploaded_by_user_id UUID NOT NULL,
            original_filename VARCHAR(512) NOT NULL,
            s3_key VARCHAR(1024) NOT NULL,
            file_hash VARCHAR(64) NOT NULL,
            mime_type VARCHAR(128) NOT NULL,
            page_count INTEGER,
            ocr_status VARCHAR(32) DEFAULT ''pending'',
            ocr_job_id VARCHAR(256),
            ocr_raw_text TEXT,
            document_metadata JSONB,
            processing_error TEXT,
            is_deleted BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )', v_schema);

    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.document_chunks (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            document_id UUID NOT NULL,
            tenant_id UUID NOT NULL,
            chunk_text TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            page_number INTEGER,
            section_title VARCHAR(512),
            article_number VARCHAR(64),
            embedding vector(1536),
            source_metadata JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )', v_schema);

    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.conversations (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id UUID NOT NULL,
            user_id UUID NOT NULL,
            title VARCHAR(512),
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )', v_schema);

    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.messages (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            conversation_id UUID NOT NULL,
            role VARCHAR(32) NOT NULL,
            content TEXT NOT NULL,
            template_id VARCHAR(128),
            rag_context_ids TEXT[],
            confidence_score FLOAT,
            hallucination_flag BOOLEAN DEFAULT FALSE,
            citation_map JSONB,
            token_usage JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )', v_schema);
END;
$$ LANGUAGE plpgsql;
