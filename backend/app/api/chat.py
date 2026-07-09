from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.database.connection import get_db
from app.api.schemas import QueryRequest, ChatSessionResponse, MessageResponse
from app.services.chat_service import ChatService
from app.auth.dependencies import get_current_user
from app.models.user import User

router = APIRouter(tags=["AI Chat"])

@router.post("/query")
async def query_rag(
    payload: QueryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Streams a RAG-backed LLM response using Server-Sent Events (SSE).
    Returns a stream of text chunks and matching citation sources.
    """
    generator = ChatService.stream_query(
        db=db,
        user=current_user,
        message=payload.message,
        session_id=payload.session_id,
        search_mode=payload.search_mode,
        document_ids=payload.document_ids,
        k=payload.k
    )
    
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no" # Prevents Nginx from buffering the stream
        }
    )

@router.get("/history", response_model=List[ChatSessionResponse])
async def list_chat_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Lists all chat threads/sessions for the authenticated user."""
    return await ChatService.get_user_sessions(db, current_user.id)

@router.get("/history/{session_id}", response_model=List[MessageResponse])
async def get_chat_messages(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Fetches all messages in a specific chat session thread."""
    return await ChatService.get_session_messages(db, session_id, current_user.id)
