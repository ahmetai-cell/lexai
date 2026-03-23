-- ============================================================
-- Audit Log Immutability (Katman 5 — KVKK Uyumluluğu)
-- ============================================================
-- Bu dosya audit_logs tablosunu fiziksel olarak değiştirilemez
-- ve silinemez yapar. PostgreSQL RULE mekanizması kullanılır.
--
-- KVKK Madde 12: Kişisel verilerin güvenliğinin sağlanması.
-- Denetim kaydının bütünlüğü hukuki delil değeri taşır.
--
-- Çalıştırma sırası: 04_audit_immutability.sql
-- (init.sql ve rls_setup.sql'den SONRA çalışmalı)
-- ============================================================

-- UPDATE engelleyici kural
-- Her UPDATE denemesini sessizce reddeder (INSTEAD NOTHING)
DROP RULE IF EXISTS audit_no_update ON audit_logs;
CREATE RULE audit_no_update AS
    ON UPDATE TO audit_logs
    DO INSTEAD NOTHING;

-- DELETE engelleyici kural
-- Her DELETE denemesini sessizce reddeder
DROP RULE IF EXISTS audit_no_delete ON audit_logs;
CREATE RULE audit_no_delete AS
    ON DELETE TO audit_logs
    DO INSTEAD NOTHING;

-- TRUNCATE koruması: Sadece superuser TRUNCATE yapabilir
-- lexai_app rolü TRUNCATE yetkisine sahip değil (rls_setup.sql'den gelen kısıtlama)
REVOKE TRUNCATE ON audit_logs FROM lexai_app;

-- ── Denetim indeksleri (KVKK denetiminde hızlı sorgu için) ──────
-- Büro + tarih bazlı sorgu (KVKK denetçisi: "Bu büronun Mart ayı logları?")
CREATE INDEX IF NOT EXISTS idx_audit_tenant_date
    ON audit_logs (tenant_id, created_at DESC);

-- Kullanıcı bazlı sorgu
CREATE INDEX IF NOT EXISTS idx_audit_user_date
    ON audit_logs (user_id, created_at DESC)
    WHERE user_id IS NOT NULL;

-- Event tipi bazlı sorgu
CREATE INDEX IF NOT EXISTS idx_audit_event_type
    ON audit_logs (event_type, created_at DESC);

-- Hallucination tespit edilen kayıtlar
CREATE INDEX IF NOT EXISTS idx_audit_hallucination
    ON audit_logs (tenant_id, created_at DESC)
    WHERE hallucination_flag = true;

-- ── Yorum ───────────────────────────────────────────────────────
COMMENT ON TABLE audit_logs IS
    'KVKK denetim logu — immutable (UPDATE/DELETE kurallarla engellenmiş). '
    'Her kayıt Büro ID, Kullanıcı ID, zaman damgası, belge erişimi ve AI '
    'metriklerini içerir. Silme yetkisi sadece superuser''a aittir.';
