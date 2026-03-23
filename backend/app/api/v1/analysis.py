"""
Analysis API — Widget ve yapılandırılmış analiz endpoint'leri

POST /api/v1/analysis/widget
  Dava dosyasını analiz edip widget için JSON döndürür.
  Frontend bu veriyi direkt widgete bağlar.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_tenant_db
from app.models.user import User
from app.services.widget_service import widget_service, WidgetRequest
from app.schemas.widget import WidgetResponse
from app.core.exceptions import RAGRetrievalError
from app.core.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


class WidgetAnalysisRequest(BaseModel):
    document_ids: list[str]
    # Hangi konuya odaklanılsın — retrieval kalitesini artırır, zorunlu değil
    query_hint: str = "Dava özeti, taraflar, riskler ve kritik olaylar"


@router.post(
    "/widget",
    response_model=WidgetResponse,
    status_code=status.HTTP_200_OK,
    summary="Dava Analizi Widget",
    description=(
        "Verilen belge ID'lerini analiz edip widget için yapılandırılmış JSON döndürür. "
        "Claude yalnızca JSON üretir; HallucinationGuard bypass edilir, "
        "doğrulama Pydantic katmanında yapılır."
    ),
)
async def analyze_widget(
    body: WidgetAnalysisRequest,
    request: Request,
    db: AsyncSession = Depends(get_tenant_db),
    current_user: User = Depends(get_current_user),
) -> WidgetResponse:
    if not body.document_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="En az bir belge ID'si gerekli.",
        )

    widget_request = WidgetRequest(
        document_ids=body.document_ids,
        tenant_id=str(current_user.tenant_id),
        user_id=str(current_user.id),
        query_hint=body.query_hint,
        ip_address=request.client.host if request.client else None,
        anomaly_events=getattr(request.state, "anomaly_events", None),
    )

    try:
        return await widget_service.analyze(widget_request, db)
    except RAGRetrievalError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        # JSON parse veya içerik hatası
        logger.error("widget_parse_error", error=str(e), user=str(current_user.id))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Model geçerli JSON döndürmedi. Lütfen tekrar deneyin.",
        )
    except Exception as e:
        logger.error("widget_unexpected_error", error=str(e), user=str(current_user.id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Analiz sırasında beklenmeyen hata.",
        )
