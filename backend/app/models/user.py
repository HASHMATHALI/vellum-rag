import datetime
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


def utcnow() -> datetime.datetime:
    # Naive UTC timestamps, matching the existing "timestamp without time zone" columns.
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(50), default="user", nullable=False)  # guest | user | admin
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    # MFA (TOTP). The secret is only used after mfa_enabled is set by a verified code.
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")
    mfa_secret: Mapped[str] = mapped_column(String(64), nullable=True)
    mfa_recovery_codes: Mapped[str] = mapped_column(Text, nullable=True)  # JSON list of argon2 hashes
    last_login_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=True)
    # Google account id (`sub` claim) when the user signs in with Google
    google_sub: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=True)

    documents = relationship("Document", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    chat_sessions = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    auth_sessions = relationship("AuthSession", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)


class AuthSession(Base):
    """Server-side session record: lets us revoke tokens (logout, password change) and rotate refresh tokens."""

    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    refresh_token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=True)
    user_agent: Mapped[str] = mapped_column(String(255), nullable=True)

    user = relationship("User", back_populates="auth_sessions")
