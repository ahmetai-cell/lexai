"""
FastAPI Dependencies

get_db_with_tenant() – RLS tenant variable set edilmiş session döndürür.
Her protected endpoint bu dependency'yi kullanmalıdır.
"""
from typing import AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.security import decode_token
from app.core.exceptions import AuthenticationError
from app.db.session import AsyncSessionLocal, _set_rls_tenant, _clear_rls_tenant
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


# ── Temel session (login gibi tenant-less endpoint'ler için) ───────
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Kullanıcı çözümleme ────────────────────────────────────────────
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_session),
) -> User:
    try:
        payload = decode_token(token)
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Geçersiz token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Kullanıcı bulunamadı")

    return user


# ── RLS-aware tenant session ───────────────────────────────────────
async def get_tenant_db(
    current_user: User = Depends(get_current_user),
) -> AsyncGenerator[AsyncSession, None]:
    """
    Tenant-aware DB session.
    Her sorgudan önce PostgreSQL'e SET LOCAL app.current_tenant_id yapılır.
    RLS politikaları bu variable'ı okuyarak cross-tenant erişimi engeller.

    Kullanım:
        @router.get("/documents")
        async def list_docs(db: AsyncSession = Depends(get_tenant_db)):
            ...
    """
    tenant_id = str(current_user.tenant_id)

    async with AsyncSessionLocal() as session:
        try:
            await _set_rls_tenant(session, tenant_id)
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await _clear_rls_tenant(session)
            await session.close()


# ── Kısayollar ─────────────────────────────────────────────────────
async def get_current_tenant(
    current_user: User = Depends(get_current_user),
) -> str:
    return str(current_user.tenant_id)
