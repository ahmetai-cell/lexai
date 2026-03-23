from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.v1.deps import get_current_user
from app.api.v1.deps import get_tenant_db
from app.models.conversation import Conversation, Message, MessageRole
from app.models.user import User
from app.services.rag_service import rag_service, RAGRequest

router = APIRouter()


class SendMessageRequest(BaseModel):
    query: str
    template_slug: str = "rag_system_base"
    document_ids: list[str] | None = None
    stream: bool = True


@router.post("/sessions")
async def create_session(
    db: AsyncSession = Depends(get_tenant_db),
    current_user: User = Depends(get_current_user),
):
    conv = Conversation(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
    )
    db.add(conv)
    await db.flush()
    return {"session_id": str(conv.id)}


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: str,
    body: SendMessageRequest,
    db: AsyncSession = Depends(get_tenant_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == session_id,
            Conversation.tenant_id == current_user.tenant_id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Oturum bulunamadı")

    rag_request = RAGRequest(
        query=body.query,
        tenant_id=str(current_user.tenant_id),
        user_id=str(current_user.id),
        template_slug=body.template_slug,
        document_ids=body.document_ids,
    )

    if body.stream:
        async def token_generator():
            async for token in rag_service.stream(rag_request, db):
                yield f"data: {token}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(token_generator(), media_type="text/event-stream")

    # Non-streaming
    response = await rag_service.query(rag_request, db)

    user_msg = Message(
        conversation_id=conv.id,
        role=MessageRole.USER,
        content=body.query,
        template_id=body.template_slug,
    )
    assistant_msg = Message(
        conversation_id=conv.id,
        role=MessageRole.ASSISTANT,
        content=response.answer,
        template_id=body.template_slug,
        confidence_score=response.confidence_score,
        hallucination_flag=response.hallucination_flag,
        citation_map=response.citation_map,
        rag_context_ids=[s.chunk_id for s in response.sources],
    )
    db.add(user_msg)
    db.add(assistant_msg)

    return {
        "answer": response.answer,
        "citation_map": response.citation_map,
        "confidence_score": response.confidence_score,
        "hallucination_flag": response.hallucination_flag,
        "flagged_claims": response.flagged_claims,
        "sources": [
            {
                "chunk_id": s.chunk_id,
                "document_id": s.document_id,
                "page": s.page_number,
                "text_snippet": s.chunk_text[:200],
                "similarity": s.similarity_score,
            }
            for s in response.sources
        ],
    }


@router.get("/sessions/{session_id}/history")
async def get_history(
    session_id: str,
    db: AsyncSession = Depends(get_tenant_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Message)
        .join(Conversation)
        .where(
            Conversation.id == session_id,
            Conversation.tenant_id == current_user.tenant_id,
        )
        .order_by(Message.created_at)
    )
    messages = result.scalars().all()
    return {
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "citation_map": m.citation_map,
                "confidence_score": m.confidence_score,
                "hallucination_flag": m.hallucination_flag,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ]
    }
