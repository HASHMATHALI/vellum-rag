import json
import logging
from typing import AsyncGenerator, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import async_session, set_rls_context
from app.llm.groq_client import LLMError
from app.models.chat import ChatMessage, ChatSession
from app.models.document import Document
from app.models.user import User
from app.observability import tracing
from app.rag.pipeline import normalize_citations, pipeline, strip_invalid_citations, validate_question

logger = logging.getLogger(__name__)


def sse(data, event: Optional[str] = None) -> str:
    head = f"event: {event}\n" if event else ""
    return f"{head}data: {json.dumps(data, ensure_ascii=False)}\n\n"


class ChatService:
    @staticmethod
    async def get_user_sessions(db: AsyncSession, user_id: int) -> List[ChatSession]:
        res = await db.execute(select(ChatSession).where(ChatSession.user_id == user_id).order_by(ChatSession.created_at.desc()))
        return list(res.scalars().all())

    @staticmethod
    async def get_owned_session(db: AsyncSession, session_id: str, user_id: int) -> ChatSession:
        res = await db.execute(select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user_id))
        session = res.scalars().first()
        if not session:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Chat session not found.")
        return session

    @classmethod
    async def get_session_messages(cls, db: AsyncSession, session_id: str, user_id: int) -> List[ChatMessage]:
        await cls.get_owned_session(db, session_id, user_id)
        res = await db.execute(select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at.asc()))
        return list(res.scalars().all())

    @classmethod
    async def delete_session(cls, db: AsyncSession, session_id: str, user_id: int) -> None:
        session = await cls.get_owned_session(db, session_id, user_id)
        await db.delete(session)
        await db.commit()

    @classmethod
    async def prepare_query(cls, db: AsyncSession, user: User, message: str, session_id: Optional[str],
                            document_ids: Optional[List[int]]) -> dict:
        """Everything that can fail with a proper HTTP status runs here, before the stream starts."""
        try:
            question = validate_question(message)
        except ValueError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
        if session_id:
            await cls.get_owned_session(db, session_id, user.id)
        if document_ids is not None:
            owned = (await db.execute(select(Document.id).where(Document.id.in_(document_ids), Document.user_id == user.id))).scalars().all()
            if set(owned) != set(document_ids):
                raise HTTPException(status.HTTP_404_NOT_FOUND, "One or more documents were not found.")
        return {"question": question}

    @classmethod
    async def stream_query(cls, user: User, question: str, session_id: Optional[str], search_mode: str,
                           document_ids: Optional[List[int]], k: int) -> AsyncGenerator[str, None]:
        # The request-scoped DB session may be closed once the response starts streaming,
        # so the generator owns its own session.
        async with async_session() as db:
            await set_rls_context(db, user.id, is_admin=user.role == "admin")
            if not session_id:
                session = ChatSession(title=question[:60] + ("..." if len(question) > 60 else ""), user_id=user.id)
                db.add(session)
                await db.commit()
                session_id = session.id
            hist_rows = (await db.execute(
                select(ChatMessage).where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at.desc()).limit(10))).scalars().all()
            history = [{"role": m.role, "content": m.content} for m in reversed(hist_rows)]
            db.add(ChatMessage(session_id=session_id, role="user", content=question, sources=[]))
            await db.commit()
            yield sse({"session_id": session_id}, "session")

            meta: dict = {}
            answer_parts: List[str] = []
            sources: List[dict] = []
            with tracing.span("rag.query", "CHAIN", {"rag.mode": search_mode, "rag.top_k": k, "user.id": user.id,
                                                      "session.id": session_id}) as root:
                tracing.set_attrs(root, {tracing.INPUT: question}, content=True)
                try:
                    prepared = await pipeline.prepare(db, user.id, question, history, search_mode, k, document_ids)
                    sources = prepared.context.sources
                    yield sse(sources, "sources")
                    async for tok in pipeline.stream(prepared, meta):
                        answer_parts.append(tok)
                        yield sse({"content": tok})
                except LLMError as e:
                    yield sse({"detail": e.public_message}, "error")
                except Exception:
                    logger.exception("RAG query failed")
                    yield sse({"detail": "Something went wrong while answering. Please retry."}, "error")
                answer = normalize_citations("".join(answer_parts))
                if meta.get("validation", {}).get("invalid_refs"):
                    answer = strip_invalid_citations(answer, meta["validation"]["invalid_refs"])
                cited = set(meta.get("validation", {}).get("cited_refs", []))
                for s in sources:
                    s["cited"] = s["ref"] in cited
                if meta:
                    yield sse({k_: v for k_, v in meta.items() if k_ != "search_query"}, "meta")
                tracing.set_attrs(root, {tracing.OUTPUT: answer}, content=True)
            yield sse("[DONE]", "close")

            if answer.strip():
                db.add(ChatMessage(session_id=session_id, role="assistant", content=answer, sources=sources, meta=meta))
                await db.commit()
