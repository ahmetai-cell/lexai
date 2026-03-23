"""
LexAI – FastAPI Application Entry Point
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import engine
from app.db.base import Base
from app.middleware.error_handler import register_exception_handlers
from app.middleware.tenant_middleware import TenantMiddleware
from app.middleware.audit_middleware import AuditMiddleware
from app.prompts.loader import prompt_registry


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup ve shutdown lifecycle hook."""
    configure_logging()

    # Prompt şablonlarını kayıt defterine yükle
    prompt_registry.load_all()

    yield

    # Cleanup
    await engine.dispose()
    from app.core.redis import close_redis
    await close_redis()


app = FastAPI(
    title="LexAI – Hukuk Bürosu Yapay Zeka Platformu",
    description="Türk hukuk büroları için RAG tabanlı AI asistan",
    version="1.0.0",
    docs_url="/docs" if settings.APP_DEBUG else None,
    redoc_url="/redoc" if settings.APP_DEBUG else None,
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Audit & Anomaly Middleware ────────────────────
app.add_middleware(AuditMiddleware)

# ── Tenant Middleware ─────────────────────────────
app.add_middleware(TenantMiddleware)

# ── Exception Handlers ────────────────────────────
register_exception_handlers(app)

# ── Routers ──────────────────────────────────────
app.include_router(api_router, prefix="/api/v1")


@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok", "version": "1.0.0"}
