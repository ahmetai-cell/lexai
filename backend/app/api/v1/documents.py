import hashlib
import uuid

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.v1.deps import get_current_tenant, get_current_user
from app.api.v1.deps import get_tenant_db
from app.models.document import Document, DocumentStatus
from app.models.user import User

router = APIRouter()


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_tenant_db),
    current_user: User = Depends(get_current_user),
):
    """Belge yükle – S3 + Textract OCR iş kuyruğuna gönder."""
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

    doc = Document(
        tenant_id=current_user.tenant_id,
        uploaded_by_user_id=current_user.id,
        original_filename=file.filename,
        s3_key=s3_key,
        file_hash=file_hash,
        mime_type=file.content_type,
        ocr_status=DocumentStatus.PENDING,
    )
    db.add(doc)
    await db.flush()

    # TODO: S3 upload + Textract job başlat (background task)

    return {"id": str(doc.id), "filename": file.filename, "status": doc.ocr_status}


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
