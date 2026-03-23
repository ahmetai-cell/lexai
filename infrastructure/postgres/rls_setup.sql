-- ═══════════════════════════════════════════════════════════════════
-- LexAI – PostgreSQL Row-Level Security (RLS) Kurulumu
-- Her hukuk bürosu sadece kendi verilerini görebilir.
-- Uygulama seviyesinde değil, VERİTABANI seviyesinde güvenlik.
-- ═══════════════════════════════════════════════════════════════════
--
-- Nasıl çalışır:
--   1. Her sorgudan önce SET LOCAL app.current_tenant_id = '<uuid>'
--   2. RLS policy bu session variable'ı okur
--   3. tenant_id eşleşmeyenleri DB ENGINE'de filtreler
--   4. Uygulama katmanı bypass edilse bile veri sızmaz
-- ═══════════════════════════════════════════════════════════════════

-- ── 1. Uygulama rolü oluştur (superuser değil!) ───────────────────
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lexai_app') THEN
        CREATE ROLE lexai_app LOGIN PASSWORD 'change-in-production';
    END IF;
END
$$;

-- lexai_app rolüne tabloları erişim ver
GRANT USAGE ON SCHEMA public TO lexai_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO lexai_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO lexai_app;

-- Gelecekte oluşturulacak tablolar için de ver
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO lexai_app;

-- ── 2. Ana tablolarda RLS etkinleştir ────────────────────────────

-- documents
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents FORCE ROW LEVEL SECURITY;

-- document_chunks
ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_chunks FORCE ROW LEVEL SECURITY;

-- conversations
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations FORCE ROW LEVEL SECURITY;

-- messages (conversation üzerinden dolaylı erişim)
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages FORCE ROW LEVEL SECURITY;

-- audit_logs
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs FORCE ROW LEVEL SECURITY;

-- users (kendi tenant'ını görür)
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE users FORCE ROW LEVEL SECURITY;

-- api_keys
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys FORCE ROW LEVEL SECURITY;

-- ── 3. Helper fonksiyon – geçerli tenant ID'yi döndür ────────────

CREATE OR REPLACE FUNCTION current_tenant_id()
RETURNS UUID
LANGUAGE sql
STABLE
AS $$
    SELECT NULLIF(
        current_setting('app.current_tenant_id', true),
        ''
    )::UUID
$$;

-- ── 4. RLS Politikaları ────────────────────────────────────────────
-- Her tablo için: SELECT / INSERT / UPDATE / DELETE ayrı ayrı

-- ── documents ──────────────────────────────────────────────────────
CREATE POLICY tenant_isolation_documents_select
    ON documents FOR SELECT
    TO lexai_app
    USING (tenant_id = current_tenant_id());

CREATE POLICY tenant_isolation_documents_insert
    ON documents FOR INSERT
    TO lexai_app
    WITH CHECK (tenant_id = current_tenant_id());

CREATE POLICY tenant_isolation_documents_update
    ON documents FOR UPDATE
    TO lexai_app
    USING (tenant_id = current_tenant_id())
    WITH CHECK (tenant_id = current_tenant_id());

CREATE POLICY tenant_isolation_documents_delete
    ON documents FOR DELETE
    TO lexai_app
    USING (tenant_id = current_tenant_id());

-- ── document_chunks ────────────────────────────────────────────────
CREATE POLICY tenant_isolation_chunks_select
    ON document_chunks FOR SELECT
    TO lexai_app
    USING (tenant_id = current_tenant_id());

CREATE POLICY tenant_isolation_chunks_insert
    ON document_chunks FOR INSERT
    TO lexai_app
    WITH CHECK (tenant_id = current_tenant_id());

CREATE POLICY tenant_isolation_chunks_update
    ON document_chunks FOR UPDATE
    TO lexai_app
    USING (tenant_id = current_tenant_id())
    WITH CHECK (tenant_id = current_tenant_id());

CREATE POLICY tenant_isolation_chunks_delete
    ON document_chunks FOR DELETE
    TO lexai_app
    USING (tenant_id = current_tenant_id());

-- ── conversations ──────────────────────────────────────────────────
CREATE POLICY tenant_isolation_conversations_select
    ON conversations FOR SELECT
    TO lexai_app
    USING (tenant_id = current_tenant_id());

CREATE POLICY tenant_isolation_conversations_insert
    ON conversations FOR INSERT
    TO lexai_app
    WITH CHECK (tenant_id = current_tenant_id());

CREATE POLICY tenant_isolation_conversations_update
    ON conversations FOR UPDATE
    TO lexai_app
    USING (tenant_id = current_tenant_id())
    WITH CHECK (tenant_id = current_tenant_id());

-- ── messages ───────────────────────────────────────────────────────
-- Messages'ın tenant_id'si conversation üzerinden dolaylı —
-- ama conversation_id'yi zaten RLS'li conversation tablosundan alıyoruz.
-- Ek güvenlik için: conversation'ın tenant'ını doğrula.
CREATE POLICY tenant_isolation_messages_select
    ON messages FOR SELECT
    TO lexai_app
    USING (
        EXISTS (
            SELECT 1 FROM conversations c
            WHERE c.id = messages.conversation_id
              AND c.tenant_id = current_tenant_id()
        )
    );

CREATE POLICY tenant_isolation_messages_insert
    ON messages FOR INSERT
    TO lexai_app
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM conversations c
            WHERE c.id = messages.conversation_id
              AND c.tenant_id = current_tenant_id()
        )
    );

-- ── audit_logs ─────────────────────────────────────────────────────
CREATE POLICY tenant_isolation_audit_select
    ON audit_logs FOR SELECT
    TO lexai_app
    USING (tenant_id = current_tenant_id());

CREATE POLICY tenant_isolation_audit_insert
    ON audit_logs FOR INSERT
    TO lexai_app
    WITH CHECK (tenant_id = current_tenant_id());

-- ── users ──────────────────────────────────────────────────────────
-- Kullanıcı kendi tenant'ındakileri görür
CREATE POLICY tenant_isolation_users_select
    ON users FOR SELECT
    TO lexai_app
    USING (tenant_id = current_tenant_id());

-- ── api_keys ───────────────────────────────────────────────────────
CREATE POLICY tenant_isolation_apikeys_select
    ON api_keys FOR SELECT
    TO lexai_app
    USING (tenant_id = current_tenant_id());

-- ── 5. Superuser bypass (migration ve yönetim için) ──────────────
-- Not: Superuser FORCE ROW LEVEL SECURITY'den muaftır.
-- Migration'ları superuser ile çalıştır, app'i lexai_app ile.

-- ── 6. RLS Durum Kontrolü (test amaçlı) ──────────────────────────
-- SELECT tablename, rowsecurity, forceroulsecurity
-- FROM pg_tables
-- WHERE schemaname = 'public';

-- ── 7. Cross-tenant Sızma Testi ───────────────────────────────────
-- Doğru kullanım:
--   SET LOCAL app.current_tenant_id = 'tenant-uuid-A';
--   SELECT COUNT(*) FROM document_chunks;  -- sadece A'nın kayıtları
--
-- Yanlış kullanım (sızma girişimi):
--   SET LOCAL app.current_tenant_id = '';  -- NULL döner, 0 kayıt gelir
--   -- Tüm kayıtlara erişim MÜMKÜN DEĞİL

-- ── 8. pgvector similarity search RLS uyumluluğu ─────────────────
-- match_document_chunks fonksiyonu lexai_app rolüyle çağrılacak.
-- RLS otomatik devreye girer — fonksiyona ekstra WHERE gerekmez.
GRANT EXECUTE ON FUNCTION match_document_chunks TO lexai_app;
GRANT EXECUTE ON FUNCTION current_tenant_id TO lexai_app;
