import hashlib
import uuid

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.v1.deps import get_current_tenant, get_current_user
from app.api.v1.deps import get_tenant_db
from app.models.document import Document, DocumentStatus
from app.models.document_job import DocumentProcessingJob
from app.models.user import User

router = APIRouter()


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_tenant_db),
    current_user: User = Depends(get_current_user),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """
    Belge yükle:
    - S3'e şifreli yükle
    - 3000+ sayfa ise async pipeline'a al (SQS kuyruğu)
    - Küçük dosyalar için senkron OCR yolu (mevcut akış)
    """
    if file.content_type not in ("application/pdf", "image/jpeg", "image/png", "image/tiff"):
        raise HTTPException(status_code=422, detail="Desteklenmeyen dosya türü")

    content = await file.read()
    file_hash = hashlib.sha256(content).hexdigest()

    # Duplicate kontrolü
    existing = await db.execute(
        select(Document).where(
            Document.tenant_id == current_user.tenant_id,
            Document.file_hash == file_hash,
            Document.is_deleted == False,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Bu belge zaten yüklenmiş")

    s3_key = f"tenants/{current_user.tenant_id}/documents/{uuid.uuid4()}/{file.filename}"

    # Sayfa sayısını tespit et (PDF için)
    page_count = _count_pdf_pages(content) if file.content_type == "application/pdf" else 1

    doc = Document(
        tenant_id=current_user.tenant_id,
        uploaded_by_user_id=current_user.id,
        original_filename=file.filename,
        s3_key=s3_key,
        file_hash=file_hash,
        mime_type=file.content_type,
        page_count=page_count,
        ocr_status=DocumentStatus.PENDING,
    )
    db.add(doc)
    await db.flush()

    # S3'e şifreli yükle (background task — upload bloklamamalı)
    background_tasks.add_task(
        _upload_and_queue,
        content=content,
        s3_key=s3_key,
        content_type=file.content_type,
        doc_id=str(doc.id),
        tenant_id=str(current_user.tenant_id),
        user_id=str(current_user.id),
        filename=file.filename,
        page_count=page_count,
    )

    response = {
        "id": str(doc.id),
        "filename": file.filename,
        "status": doc.ocr_status,
        "page_count": page_count,
    }

    # Büyük dosya → async job bilgisi ekle
    from app.core.config import settings
    if page_count > settings.LARGE_FILE_PAGE_THRESHOLD:
        response["async_processing"] = True
        response["message"] = (
            f"{page_count} sayfalık büyük belge. İşlem arka planda devam edecek. "
            f"İlerlemeyi /api/v1/jobs/ üzerinden takip edebilirsiniz."
        )

    return response


# ── Yardımcı fonksiyonlar ────────────────────────────────────────

def _count_pdf_pages(content: bytes) -> int:
    """PDF sayfa sayısını hızlıca oku."""
    try:
        import io
        try:
            import pypdf
            return len(pypdf.PdfReader(io.BytesIO(content)).pages)
        except ImportError:
            import PyPDF2
            return len(PyPDF2.PdfReader(io.BytesIO(content)).pages)
    except Exception:
        return 1  # Sayım başarısız → 1 sayfa varsay


async def _upload_and_queue(
    content: bytes,
    s3_key: str,
    content_type: str,
    doc_id: str,
    tenant_id: str,
    user_id: str,
    filename: str,
    page_count: int,
) -> None:
    """
    Background task: S3 şifreli yükleme + büyük dosya SQS kuyruğu.
    """
    from app.services.s3_service import s3_service
    from app.services.sqs_service import sqs_service, LARGE_FILE_PAGE_THRESHOLD
    from app.core.config import settings
    from app.db.session import AsyncSessionLocal
    from app.core.logging import get_logger

    log = get_logger("upload_background")

    try:
        # 1. S3 şifreli yükleme
        await s3_service.upload_encrypted(
            content=content,
            s3_key=s3_key,
            content_type=content_type,
            extra_metadata={
                "tenant_id": tenant_id,
                "document_id": doc_id,
                "original_filename": filename,
            },
        )
        log.info("s3_upload_done", doc_id=doc_id, pages=page_count)

        # 2. Büyük dosya → async worker pipeline
        threshold = getattr(settings, "LARGE_FILE_PAGE_THRESHOLD", LARGE_FILE_PAGE_THRESHOLD)
        if page_count > threshold and getattr(settings, "SQS_QUEUE_URL", None):
            async with AsyncSessionLocal() as db:
                # DocumentProcessingJob oluştur
                import uuid as _uuid
                job = DocumentProcessingJob(
                    tenant_id=_uuid.UUID(tenant_id),
                    user_id=_uuid.UUID(user_id),
                    document_id=_uuid.UUID(doc_id),
                    s3_key=s3_key,
                    original_filename=filename,
                    total_pages=page_count,
                    total_batches=(page_count + settings.WORKER_BATCH_SIZE - 1) // settings.WORKER_BATCH_SIZE,
                )
                db.add(job)
                await db.flush()
                job_id = str(job.id)
                await db.commit()

            # SQS'e gönder
            msg_id = await sqs_service.enqueue_document_job(
                job_id=job_id,
                tenant_id=tenant_id,
                user_id=user_id,
                document_id=doc_id,
                s3_key=s3_key,
                original_filename=filename,
                total_pages=page_count,
                batch_size=settings.WORKER_BATCH_SIZE,
            )
            log.info("large_file_queued", job_id=job_id, sqs_msg=msg_id)

    except Exception as e:
        log.error("upload_background_error", doc_id=doc_id, error=str(e))


@router.get("/")
async def list_documents(
    db: AsyncSession = Depends(get_tenant_db),
    current_user: User = Depends(get_current_user),
    page: int = 1,
    per_page: int = 20,
):
    offset = (page - 1) * per_page
    result = await db.execute(
        select(Document)
        .where(Document.tenant_id == current_user.tenant_id, Document.is_deleted == False)
        .offset(offset)
        .limit(per_page)
        .order_by(Document.created_at.desc())
    )
    docs = result.scalars().all()
    return {
        "items": [
            {"id": str(d.id), "filename": d.original_filename, "status": d.ocr_status, "pages": d.page_count}
            for d in docs
        ],
        "page": page,
    }


@router.get("/{doc_id}")
async def get_document(
    doc_id: str,
    db: AsyncSession = Depends(get_tenant_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Document).where(
            Document.id == doc_id,
            Document.tenant_id == current_user.tenant_id,
            Document.is_deleted == False,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Belge bulunamadı")
    return {"id": str(doc.id), "filename": doc.original_filename, "status": doc.ocr_status}


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    doc_id: str,
    db: AsyncSession = Depends(get_tenant_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Document).where(
            Document.id == doc_id,
            Document.tenant_id == current_user.tenant_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Belge bulunamadı")
    doc.is_deleted = True
