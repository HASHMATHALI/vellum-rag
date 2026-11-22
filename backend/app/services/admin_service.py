import datetime
import os
from collections import deque

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.logging_config import redact
from app.config.settings import settings
from app.models.chat import ChatMessage
from app.models.document import Document, DocumentChunk
from app.models.user import User, utcnow


class AdminService:
    @staticmethod
    async def get_system_stats(db: AsyncSession) -> dict:
        total_users = (await db.execute(select(func.count(User.id)).where(User.role != "guest"))).scalar() or 0
        guests = (await db.execute(select(func.count(User.id)).where(User.role == "guest"))).scalar() or 0
        total_docs = (await db.execute(select(func.count(Document.id)))).scalar() or 0
        storage_bytes = (await db.execute(select(func.sum(Document.file_size)))).scalar() or 0
        chunks = (await db.execute(select(func.count(DocumentChunk.id)))).scalar() or 0
        failed = (await db.execute(select(func.count(Document.id)).where(Document.status == "failed"))).scalar() or 0
        since = utcnow() - datetime.timedelta(hours=24)
        queries_today = (await db.execute(select(func.count(ChatMessage.id))
                                          .where(ChatMessage.role == "user", ChatMessage.created_at >= since))).scalar() or 0
        # Token usage recorded by the pipeline in chat_messages.meta (no fabricated numbers).
        metas = (await db.execute(select(ChatMessage.meta).where(ChatMessage.role == "assistant",
                                                                  ChatMessage.created_at >= since))).scalars().all()
        tokens = sum(((m or {}).get("usage") or {}).get("prompt_tokens", 0) + ((m or {}).get("usage") or {}).get("completion_tokens", 0)
                     for m in metas)
        # Users' questions are private content: admins see volume, not the text of other users' queries.
        return {
            "total_users": total_users,
            "total_documents": total_docs,
            "storage_used_mb": round(storage_bytes / (1024 * 1024), 2),
            "queries_today": queries_today,
            "most_asked_questions": [],
            "api_usage": {"guest_accounts": guests, "indexed_chunks": chunks, "failed_documents": failed,
                          "llm_tokens_24h": tokens, "answers_24h": len(metas)},
        }

    @staticmethod
    async def get_system_logs(lines: int = 100) -> list:
        path = settings.LOG_FILE
        if not path or not os.path.exists(path):
            return ["Log file is not available on this instance (logs go to stdout)."]
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            tail = deque(f, maxlen=lines)
        return [redact(line.rstrip()) for line in tail]
