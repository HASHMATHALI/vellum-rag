import os
import datetime
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.user import User
from app.models.document import Document
from app.models.chat import ChatMessage

class AdminService:
    """Aggregates system-wide analytics, document quotas, API limits, and logs."""

    @staticmethod
    async def get_system_stats(db: AsyncSession) -> dict:
        # 1. Total Users
        users_count_res = await db.execute(select(func.count(User.id)))
        total_users = users_count_res.scalar() or 0
        
        # 2. Total Documents
        docs_count_res = await db.execute(select(func.count(Document.id)))
        total_docs = docs_count_res.scalar() or 0
        
        # 3. Storage Used (in bytes)
        storage_res = await db.execute(select(func.sum(Document.file_size)))
        total_storage_bytes = storage_res.scalar() or 0
        total_storage_mb = round(total_storage_bytes / (1024 * 1024), 2)
        
        # 4. Queries Today (last 24 hours)
        last_24h = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
        queries_res = await db.execute(
            select(func.count(ChatMessage.id))
            .where(ChatMessage.role == "user", ChatMessage.created_at >= last_24h)
        )
        queries_today = queries_res.scalar() or 0
        
        # 5. Most Asked Questions (recent search prompts)
        recent_queries_res = await db.execute(
            select(ChatMessage.content)
            .where(ChatMessage.role == "user")
            .order_by(ChatMessage.created_at.desc())
            .limit(5)
        )
        recent_queries = list(recent_queries_res.scalars().all())
        
        # 6. Mock API usage metric
        api_usage = {
            "auth_requests": 140,
            "indexing_jobs": total_docs,
            "llm_tokens_estimated": queries_today * 350
        }
        
        return {
            "total_users": total_users,
            "total_documents": total_docs,
            "storage_used_mb": total_storage_mb,
            "queries_today": queries_today,
            "most_asked_questions": recent_queries,
            "api_usage": api_usage
        }

    @staticmethod
    async def get_system_logs(lines: int = 100) -> list:
        """Reads the last N lines of application logs from app.log if available, otherwise returns mocked event logs."""
        log_filepath = "app.log"
        if os.path.exists(log_filepath):
            try:
                with open(log_filepath, "r") as f:
                    log_lines = f.readlines()
                return [line.strip() for line in log_lines[-lines:]]
            except Exception as e:
                return [f"Error reading log file: {e}"]
        
        # Fallback Mock Logs if running in docker without persistent logging to disk
        now = datetime.datetime.utcnow().isoformat()
        return [
            f"[{now}] INFO: Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)",
            f"[{now}] INFO: RateLimiter: Initialized in-memory fallback store.",
            f"[{now}] INFO: FaissStore: Initialized new FAISS IndexIDMap with IndexFlatIP.",
            f"[{now}] INFO: SentenceTransformer model loaded successfully (all-MiniLM-L6-v2).",
            f"[{now}] INFO: Database connection initialized successfully.",
            f"[{now}] INFO: Background task workers active."
        ]
