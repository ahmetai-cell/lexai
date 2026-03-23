"""
AuditMiddleware — Her API isteğini yakalar, anomali kontrolü yapar.

Akış (her istek için):
  1. JWT'den tenant_id + user_id çıkar
  2. AnomalyDetector.check() çalıştır (sadece sorgu endpoint'leri için)
  3. Anomali tespit edilirse audit_service.log_security_anomaly() yaz
  4. Request.state'e context bilgisini aktar (RAGService'in kullanması için)

Not: RAG sonrası audit (chunks_retrieved, confidence_score, hallucination_flag)
     RAGService.query() içinde çağrılır; bu middleware sadece ön-kontrol yapar.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger

logger = get_logger(__name__)

# Bu path'lerde anomali ve audit kontrolü atlanır
SKIP_ANOMALY_PATHS = {
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
}

# Anomali kontrolü yalnızca bu pattern ile başlayan endpoint'lerde çalışır
ANOMALY_CHECK_PREFIXES = (
    "/api/v1/chat",
    "/api/v1/documents",
)


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Skip listesi
        if any(path.startswith(skip) for skip in SKIP_ANOMALY_PATHS):
            return await call_next(request)

        # Request state'e IP ve User-Agent aktar
        request.state.ip_address = self._get_client_ip(request)
        request.state.user_agent = request.headers.get("user-agent", "")

        # Anomali kontrolü: yalnızca ilgili endpoint'lerde
        if any(path.startswith(p) for p in ANOMALY_CHECK_PREFIXES):
            await self._run_anomaly_check(request)

        response = await call_next(request)
        return response

    async def _run_anomaly_check(self, request: Request) -> None:
        """
        Mevcut kullanıcı bilgisiyle anomali kontrolü çalıştır.
        Hata durumunda isteği engellemez — sadece loglar.
        """
        try:
            user_id = getattr(request.state, "user_id", None)
            tenant_id = getattr(request.state, "tenant_id", None)

            if not user_id or not tenant_id:
                # Auth middleware'den önce çalışıyor olabilir; skip
                return

            from app.audit.anomaly_detector import anomaly_detector, DetectionContext

            # Body'i oku (query text için) — streaming body sorununu önle
            # Not: Body sadece okunabilirse alınır; yoksa boş dict
            query_text = ""
            document_ids = None
            try:
                body = await request.body()
                if body:
                    import json
                    data = json.loads(body)
                    query_text = data.get("query", data.get("message", ""))
                    document_ids = data.get("document_ids")
            except Exception:
                pass  # Body parse hatası anomali tespitini engellemez

            ctx = DetectionContext(
                user_id=str(user_id),
                tenant_id=str(tenant_id),
                query_text=query_text,
                document_ids=document_ids,
                ip_address=request.state.ip_address,
            )

            events = await anomaly_detector.check(ctx)

            # Anomali eventlerini state'e aktar (RAGService loglaması için)
            request.state.anomaly_events = events

            # Her anomali için audit kaydı (DB session varsa)
            if events:
                db = getattr(request.state, "db", None)
                if db:
                    from app.audit.audit_service import audit_service
                    for event in events:
                        try:
                            await audit_service.log_security_anomaly(
                                db=db,
                                tenant_id=str(tenant_id),
                                user_id=str(user_id),
                                rule_id=event.rule_id,
                                severity=event.severity,
                                details=event.details,
                                ip_address=request.state.ip_address,
                            )
                        except Exception as e:
                            logger.error(
                                "anomaly_audit_write_failed",
                                error=str(e),
                                rule_id=event.rule_id,
                            )

        except Exception as e:
            logger.error("audit_middleware_error", error=str(e), path=request.url.path)

    def _get_client_ip(self, request: Request) -> str:
        # Proxy arkasında gerçek IP'yi al
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"
