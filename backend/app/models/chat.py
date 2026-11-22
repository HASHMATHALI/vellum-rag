import uuid

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.user import utcnow


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(255), default="New Chat", nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    created_at = mapped_column(DateTime, default=utcnow, nullable=False)

    user = relationship("User", back_populates="chat_sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan",
                            passive_deletes=True, order_by="ChatMessage.created_at")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # [{"ref": 1, "document_id": 1, "filename": "x.pdf", "chunk_index": 2, "page_number": 1,
    #   "similarity_score": 0.85, "text_content": "..."}]
    sources = mapped_column(JSON, default=list, nullable=False)
    meta = mapped_column(JSON, nullable=True)  # latency, model, token usage, grounding flags
    created_at = mapped_column(DateTime, default=utcnow, nullable=False)

    session = relationship("ChatSession", back_populates="messages")
