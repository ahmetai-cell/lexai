"""
Jobs API — Async belge işleme ilerleme takibi

GET  /api/v1/jobs/{job_id}       — Tek iş durumu
GET  /api/v1/jobs/               — Büronun tüm işleri (sayfalı)
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.v1.deps import get_current_user, get_tenant_db
from app.models.document_job import DocumentProcessingJob, JobStatus
from app.models.user import User

router = APIRouter()


@router.get("/{job_id}")
async def get_job_status(
    job_id: str,
    db: AsyncSession = Depends(get_tenant_db),
    current_user: User = Depends(get_current_user),
):
    """
    İş durumu ve ilerleme yüzdesini döndür.

    Yanıt:
      - status: pending | processing | paused | completed | failed
      - progress_pct: 0.0 – 100.0
      - completed_batches / total_batches
      - resume_from_batch: timeout sonrası devam noktası
    """
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Geçersiz iş ID formatı")

    result = await db.execute(
        select(DocumentProcessingJob).where(
            DocumentProcessingJob.id == job_uuid,
            DocumentProcessingJob.tenant_id == current_user.tenant_id,
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="İş bulunamadı")

    return _job_to_response(job)


@router.get("/")
async def list_jobs(
    db: AsyncSession = Depends(get_tenant_db),
    current_user: User = Depends(get_current_user),
    status_filter: JobStatus | None = None,
    page: int = 1,
    per_page: int = 20,
):
    """
    Büronun tüm işlerini listele.
    status_filter ile belirli durumu filtrele: ?status_filter=processing
    """
    query = select(DocumentProcessingJob).where(
        DocumentProcessingJob.tenant_id == current_user.tenant_id
    )
    if status_filter:
        query = query.where(DocumentProcessingJob.status == status_filter)

    query = (
        query
        .offset((page - 1) * per_page)
        .limit(per_page)
        .order_by(DocumentProcessingJob.created_at.desc())
    )

    result = await db.execute(query)
    jobs = result.scalars().all()

    return {
        "items": [_job_to_response(j) for j in jobs],
        "page": page,
        "per_page": per_page,
    }


def _job_to_response(job: DocumentProcessingJob) -> dict:
    return {
        "id":                  str(job.id),
        "document_id":         str(job.document_id) if job.document_id else None,
        "original_filename":   job.original_filename,
        "status":              job.status.value,
        "progress_pct":        job.progress_pct,
        "total_pages":         job.total_pages,
        "total_batches":       job.total_batches,
        "completed_batches":   job.completed_batches,
        "resume_from_batch":   job.resume_from_batch,
        "started_at":          job.started_at.isoformat() if job.started_at else None,
        "completed_at":        job.completed_at.isoformat() if job.completed_at else None,
        "created_at":          job.created_at.isoformat(),
        "error_message":       job.error_message,
        "failed_batch_index":  job.failed_batch_index,
    }
