-- Migration: 003_worker_jobs
-- Adds document_processing_jobs table for large-file async pipeline (Katman 6)
-- Run order: after 001_initial, 002_audit_logs

-- ── Enum type ──────────────────────────────────────────────────────────────────

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'jobstatus') THEN
        CREATE TYPE jobstatus AS ENUM (
            'pending',
            'processing',
            'paused',
            'completed',
            'failed'
        );
    END IF;
END$$;


-- ── Table ──────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS document_processing_jobs (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Tenant / user / document references
    tenant_id            UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id              UUID NOT NULL REFERENCES users(id),
    document_id          UUID          REFERENCES documents(id) ON DELETE SET NULL,

    -- S3 location
    s3_key               VARCHAR(1024) NOT NULL,
    original_filename    VARCHAR(512)  NOT NULL,

    -- Job status
    status               jobstatus     NOT NULL DEFAULT 'pending',

    -- Batch progress / checkpoint
    total_pages          INTEGER NOT NULL DEFAULT 0,
    total_batches        INTEGER NOT NULL DEFAULT 0,
    completed_batches    INTEGER NOT NULL DEFAULT 0,
    last_completed_batch INTEGER NOT NULL DEFAULT -1,
    -- -1  → no batch completed yet
    -- N   → batches 0..N are done; N+1 is next resume point

    -- SQS tracking (for message lifecycle management)
    sqs_message_id       VARCHAR(256),
    sqs_receipt_handle   TEXT,

    -- Error info
    error_message        TEXT,
    failed_batch_index   INTEGER,

    -- Timestamps
    started_at           TIMESTAMPTZ,
    completed_at         TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Extra metadata (notification prefs, etc.)
    job_metadata         JSONB
);


-- ── Indexes ───────────────────────────────────────────────────────────────────

-- Primary lookup patterns
CREATE INDEX IF NOT EXISTS ix_dpj_tenant_id      ON document_processing_jobs (tenant_id);
CREATE INDEX IF NOT EXISTS ix_dpj_document_id    ON document_processing_jobs (document_id);
CREATE INDEX IF NOT EXISTS ix_dpj_status         ON document_processing_jobs (status);
CREATE INDEX IF NOT EXISTS ix_dpj_created_at     ON document_processing_jobs (created_at DESC);

-- Worker polling: pending jobs per tenant
CREATE INDEX IF NOT EXISTS ix_dpj_tenant_status  ON document_processing_jobs (tenant_id, status);

-- Resume lookup: paused jobs awaiting re-queue
CREATE INDEX IF NOT EXISTS ix_dpj_paused         ON document_processing_jobs (status)
    WHERE status = 'paused';


-- ── updated_at trigger ────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_dpj_updated_at ON document_processing_jobs;

CREATE TRIGGER trg_dpj_updated_at
    BEFORE UPDATE ON document_processing_jobs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ── RLS (tenant isolation — same pattern as other tables) ─────────────────────

ALTER TABLE document_processing_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_processing_jobs FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS dpj_tenant_isolation ON document_processing_jobs;

CREATE POLICY dpj_tenant_isolation ON document_processing_jobs
    USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

-- Worker process needs cross-tenant access (runs as superuser / elevated role)
-- Grant to lexai_worker role (created separately via infra setup):
-- GRANT ALL ON document_processing_jobs TO lexai_worker;
-- ALTER TABLE document_processing_jobs DISABLE ROW LEVEL SECURITY; -- for worker role
-- (Handled by infrastructure setup scripts, not here)
