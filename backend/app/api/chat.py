from typing import List

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import ChatSessionResponse, MessageResponse, QueryRequest
from app.auth.dependencies import get_current_user
from app.database.connection import get_db
from app.middleware.rate_limiter import rate_limit_user
from app.models.user import User
from app.retrieval.gloss import audit_answer
from app.services.chat_service import ChatService

router = APIRouter(tags=["AI Chat"])


@router.post("/query", dependencies=[Depends(rate_limit_user("query", 20, 60)),
                                     Depends(rate_limit_user("query_daily", 300, 86400))])
async def query_rag(payload: QueryRequest, current_user: User = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)):
    """Streams a grounded RAG answer as Server-Sent Events.

    Events: `session` {session_id} → `sources` [citations] → data {content} (repeated) → `meta`
    {timings, usage, validation} → `close` "[DONE]". Errors after the stream started arrive as an `error` event.
    """
    prepared = await ChatService.prepare_query(db, current_user, payload.message, payload.session_id, payload.document_ids)
    generator = ChatService.stream_query(current_user, prepared["question"], payload.session_id, payload.search_mode,
                                         payload.document_ids, payload.k)
    return StreamingResponse(generator, media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/history", response_model=List[ChatSessionResponse])
async def list_chat_sessions(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await ChatService.get_user_sessions(db, current_user.id)


@router.get("/history/{session_id}", response_model=List[MessageResponse])
async def get_chat_messages(session_id: str, current_user: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    messages = await ChatService.get_session_messages(db, session_id, current_user.id)
    out = []
    for m in messages:
        item = MessageResponse.model_validate(m)
        if m.role == "assistant":
            # Gloss is deterministic, so it is recomputed on read rather than stored.
            item.gloss = audit_answer(m.content, m.sources or [])
        out.append(item)
    return out


@router.delete("/history/{session_id}", status_code=status.HTTP_200_OK)
async def delete_chat_session(session_id: str, current_user: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    await ChatService.delete_session(db, session_id, current_user.id)
    return {"message": "Conversation deleted."}
