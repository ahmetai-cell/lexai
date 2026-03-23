"""
DB Session – Her bağlantıda RLS tenant variable'ını set eder.

Akış:
  1. get_session() AsyncSession döndürür
  2. Request scope'unda tenant_id varsa SET LOCAL app.current_tenant_id = '...'
  3. PostgreSQL RLS policy bu variable'ı okuyarak cross-tenant sorgusunu engeller
  4. tenant_id yoksa (ör. login endpoint) RLS NULL döndürür → 0 satır
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.APP_DEBUG,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency: tenant context'siz session.
    deps.py'deki get_current_user çözümlendikten sonra
    set_tenant_context() ile tenant_id enjekte edilir.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_tenant_session(
    tenant_id: str,
) -> AsyncGenerator[AsyncSession, None]:
    """
    Tenant-aware session – RLS variable'ını set eder.
    Her sorgudan önce PostgreSQL'e tenant kimliğini bildirir.
    """
    async with AsyncSessionLocal() as session:
        try:
            # RLS için session-local variable set et
            await _set_rls_tenant(session, tenant_id)
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            # RLS variable'ını temizle (bağlantı havuzu güvenliği)
            await _clear_rls_tenant(session)
            await session.close()


async def _set_rls_tenant(session: AsyncSession, tenant_id: str) -> None:
    """
    PostgreSQL session-local variable set et.
    SET LOCAL: sadece mevcut transaction scope'unda geçerli.
    Bağlantı havuzuna döndürüldüğünde otomatik temizlenir.
    """
    # Güvenlik: UUID formatını doğrula (injection önlemi)
    _validate_uuid(tenant_id)
    await session.execute(
        text("SET LOCAL app.current_tenant_id = :tid"),
        {"tid": str(tenant_id)},
    )


async def _clear_rls_tenant(session: AsyncSession) -> None:
    """RLS variable'ını boşalt – bağlantı havuzu güvenliği."""
    try:
        await session.execute(text("SET LOCAL app.current_tenant_id = ''"))
    except Exception:
        pass  # Session zaten kapanıyor


def _validate_uuid(value: str) -> None:
    """Basit UUID format doğrulama – SQL injection önlemi."""
    import re
    uuid_pattern = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        re.IGNORECASE,
    )
    if not uuid_pattern.match(str(value)):
        raise ValueError(f"Geçersiz UUID formatı: {value}")
