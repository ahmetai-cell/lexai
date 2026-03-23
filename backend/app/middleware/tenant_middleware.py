from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

SKIP_PATHS = {"/health", "/docs", "/redoc", "/openapi.json", "/api/v1/auth/login"}


class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if any(path.startswith(skip) for skip in SKIP_PATHS):
            return await call_next(request)

        # tenant_id Authorization header'dan JWT decode ile çözümlenir (deps.py'de)
        # Burada sadece request.state'e placeholder set ediyoruz
        request.state.tenant_id = None

        response = await call_next(request)
        return response
