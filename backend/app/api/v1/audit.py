"""
Audit Trail API – KVKK m.12 ve baro denetimi için erişim kayıtları
"""
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.api.v1.deps import get_current_user
from app.api.v1.deps import get_tenant_db
from app.models.audit_log import AuditLog
from app.models.user import User, UserRole
from app.services.audit_service import audit_service
from app.core.exceptions import AuthorizationError

router = APIRouter()


@router.get("/summary")
async def get_audit_summary(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_tenant_db),
    current_user: User = Depends(get_current_user),
):
    """Kullanım özeti – yalnızca ADMIN erişebilir."""
    if current_user.role != UserRole.ADMIN:
        raise AuthorizationError("Bu rapora yalnızca büro yöneticisi erişebilir")

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    summary = await audit_service.get_activity_summary(
        db, tenant_id=str(current_user.tenant_id), start_date=start, end_date=end
    )
    return summary


@router.get("/documents/{doc_id}")
async def get_document_audit(
    doc_id: str,
    db: AsyncSession = Depends(get_tenant_db),
    current_user: User = Depends(get_current_user),
):
    """Belgeye kimin ne zaman eriştiğini göster."""
    if current_user.role not in (UserRole.ADMIN, UserRole.ATTORNEY):
        raise AuthorizationError("Yetki yetersiz")

    logs = await audit_service.get_document_access_log(
        db, tenant_id=str(current_user.tenant_id), document_id=doc_id
    )
    return {"document_id": doc_id, "access_log": logs}


@router.get("/hallucination-alerts")
async def get_hallucination_alerts(
    days: int = Query(default=7, ge=1, le=90),
    db: AsyncSession = Depends(get_tenant_db),
    current_user: User = Depends(get_current_user),
):
    """Hallucination uyarısı alan sorguların listesi."""
    if current_user.role != UserRole.ADMIN:
        raise AuthorizationError("Bu rapora yalnızca büro yöneticisi erişebilir")

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(AuditLog)
        .where(
            and_(
                AuditLog.tenant_id == current_user.tenant_id,
                AuditLog.hallucination_flag == True,
                AuditLog.created_at >= cutoff,
            )
        )
        .order_by(AuditLog.created_at.desc())
        .limit(50)
    )
    logs = result.scalars().all()

    return {
        "alerts": [
            {
                "id": str(log.id),
                "user_id": str(log.user_id) if log.user_id else None,
                "template": log.template_slug,
                "confidence_score": log.confidence_score,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ],
        "total": len(logs),
    }
