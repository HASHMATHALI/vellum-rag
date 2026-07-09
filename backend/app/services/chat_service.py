import json
import logging
from typing import List, Dict, Tuple, AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi import HTTPException, status
from app.models.chat import ChatSession, ChatMessage
from app.models.document import DocumentChunk, Document
from app.models.user import User
from app.retrieval.retriever import Retriever
from app.llm.groq_client import groq_client
from app.prompts.rag_prompts import SYSTEM_RAG_PROMPT, SYSTEM_REFORMULATE_PROMPT

logger = logging.getLogger(__name__)

class ChatService:
    """Orchestrates chatbot conversational state, query retrieval (RAG), and streaming LLM replies."""

    @staticmethod
    async def get_user_sessions(db: AsyncSession, user_id: int) -> List[ChatSession]:
        """Fetch all chat sessions of a user ordered by created_at."""
        result = await db.execute(
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(ChatSession.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_session_messages(db: AsyncSession, session_id: str, user_id: int) -> List[ChatMessage]:
        """Fetch all messages of a chat session, validating ownership."""
        # Validate session ownership
        session_result = await db.execute(
            select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user_id)
        )
        session = session_result.scalars().first()
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat session not found or access forbidden."
            )
            
        result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
        )
        return list(result.scalars().all())

    @classmethod
    async def stream_query(
        cls,
        db: AsyncSession,
        user: User,
        message: str,
        session_id: str = None,
        search_mode: str = "semantic",
        document_ids: List[int] = None,
        k: int = 5
    ) -> AsyncGenerator[str, None]:
        """
        Processes query, reformulates, retrieves chunks, streams LLM reply via Server-Sent Events, 
        and records dialog in Postgres.
        """
        # 1. Initialize or validate session
        if not session_id:
            # Create a new session
            session = ChatSession(
                title=message[:50] + ("..." if len(message) > 50 else ""),
                user_id=user.id
            )
            db.add(session)
            await db.commit()
            await db.refresh(session)
            session_id = session.id
        else:
            # Validate session ownership
            result = await db.execute(
                select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user.id)
            )
            session = result.scalars().first()
            if not session:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Session not found or unauthorized access."
                )

        # 2. Get past history for reformulation and conversational context
        history_res = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(10)
        )
        history = list(reversed(history_res.scalars().all()))

        # 3. Reformulate search query if history exists
        search_query = message
        if history:
            history_text = "\n".join([f"{msg.role.capitalize()}: {msg.content}" for msg in history])
            reform_prompt = SYSTEM_REFORMULATE_PROMPT.format(
                chat_history=history_text,
                user_question=message
            )
            search_query = await groq_client.generate_chat_completion([
                {"role": "system", "content": "You are a query reformulation assistant."},
                {"role": "user", "content": reform_prompt}
            ])
            if not search_query.strip():
                search_query = message

        # 4. Perform Retrieval based on search_mode
        # Fetch only documents that belong to this user (or all if admin)
        allowed_doc_ids = document_ids
        if allowed_doc_ids is None:
            # Auto-restrict to user's documents
            user_docs_res = await db.execute(select(Document.id).where(Document.user_id == user.id))
            allowed_doc_ids = list(user_docs_res.scalars().all())
        else:
            # Ensure specified docs belong to the user
            user_docs_res = await db.execute(
                select(Document.id)
                .where(Document.id.in_(allowed_doc_ids), Document.user_id == user.id)
            )
            allowed_doc_ids = list(user_docs_res.scalars().all())
            
        retrieved_chunks = []
        if allowed_doc_ids:
            search_mode_clean = search_mode.lower()
            if search_mode_clean == "mmr":
                retrieved_chunks = await Retriever.mmr_search(db, search_query, k=k, document_ids=allowed_doc_ids)
            elif search_mode_clean == "hybrid":
                retrieved_chunks = await Retriever.hybrid_search(db, search_query, k=k, document_ids=allowed_doc_ids)
            else: # "semantic"
                retrieved_chunks = await Retriever.semantic_search(db, search_query, k=k, document_ids=allowed_doc_ids)

        # 5. Format contexts and citations
        context_text_blocks = []
        sources = []
        
        for idx, (chunk, score) in enumerate(retrieved_chunks):
            # Fetch document details for metadata/filename
            doc_res = await db.execute(select(Document).where(Document.id == chunk.document_id))
            doc = doc_res.scalars().first()
            filename = doc.filename if doc else "Unknown Source"
            
            context_text_blocks.append(
                f"[Source: {filename}, Page: {chunk.page_number}]\n{chunk.text_content}\n"
            )
            sources.append({
                "document_id": chunk.document_id,
                "filename": filename,
                "chunk_index": chunk.chunk_index,
                "page_number": chunk.page_number,
                "similarity_score": score,
                "text_content": chunk.text_content
            })

        context_text = "\n".join(context_text_blocks) if context_text_blocks else "No context available."

        # 6. Build Chat LLM Prompt Payload
        # We append a structured prompt setting RAG context as System, then user chat messages.
        llm_messages = []
        
        # Add RAG System instructions
        llm_messages.append({
            "role": "system", 
            "content": SYSTEM_RAG_PROMPT.format(context_text=context_text)
        })
        
        # Add conversation history
        for msg in history:
            llm_messages.append({"role": msg.role, "content": msg.content})
            
        # Add current user prompt
        llm_messages.append({"role": "user", "content": message})

        # Save user message to PostgreSQL
        user_message_db = ChatMessage(
            session_id=session_id,
            role="user",
            content=message,
            sources=[]
        )
        db.add(user_message_db)
        await db.commit()

        # Send meta headers/setup back in the SSE stream
        yield f"event: session\ndata: {json.dumps({'session_id': session_id})}\n\n"
        yield f"event: sources\ndata: {json.dumps(sources)}\n\n"

        # 7. Start Streaming Response
        assistant_reply_accumulated = []
        
        async for chunk in groq_client.stream_chat_completion(llm_messages):
            assistant_reply_accumulated.append(chunk)
            # Write chunk in standard SSE formatting
            yield f"data: {json.dumps({'content': chunk})}\n\n"

        # Yield close event
        yield "event: close\ndata: [DONE]\n\n"

        # 8. Save Assistant message to Database asynchronously
        full_reply = "".join(assistant_reply_accumulated)
        if full_reply.strip():
            # Since connection may have yielded, create a clean async session
            from app.database.connection import async_session
            async with async_session() as write_db:
                assistant_message_db = ChatMessage(
                    session_id=session_id,
                    role="assistant",
                    content=full_reply,
                    sources=sources
                )
                write_db.add(assistant_message_db)
                await write_db.commit()
