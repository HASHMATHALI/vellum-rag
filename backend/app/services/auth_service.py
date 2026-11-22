import datetime
import logging
import secrets
import uuid
from typing import Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import mfa
from app.auth.jwt import (DUMMY_HASH, create_access_token, get_password_hash, hash_refresh_token, needs_rehash,
                          new_refresh_token, verify_password)
from app.config.settings import KNOWN_DEFAULT_PASSWORDS, settings
from app.models.user import AuthSession, User, utcnow

logger = logging.getLogger(__name__)
LEGACY_SHARED_GUEST = "guest@vellum.ai"
GUEST_DOMAIN = "guest.vellum.invalid"


def validate_password_strength(password: str, email: str = "") -> None:
    if len(password) < settings.PASSWORD_MIN_LENGTH:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters.")
    if password.lower() in KNOWN_DEFAULT_PASSWORDS or (email and password.lower() == email.lower()):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Password is too common.")
    if len(set(password)) < 5:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Password is too simple.")


class AuthService:
    @staticmethod
    async def register(db: AsyncSession, email: str, password: str, full_name: str) -> User:
        email = email.strip().lower()
        validate_password_strength(password, email)
        if email.endswith("@" + GUEST_DOMAIN) or email == LEGACY_SHARED_GUEST:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "This e-mail address cannot be registered.")
        existing = (await db.execute(select(User).where(func.lower(User.email) == email))).scalars().first()
        if existing:
            # Same generic message regardless of state, to limit account enumeration.
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Registration failed. Use a different e-mail or sign in.")
        user = User(email=email, hashed_password=get_password_hash(password), full_name=full_name.strip()[:255],
                    role="user", is_active=True)  # never auto-promote: admins are bootstrapped explicitly
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    @staticmethod
    async def authenticate(db: AsyncSession, email: str, password: str) -> User:
        email = email.strip().lower()
        user = (await db.execute(select(User).where(func.lower(User.email) == email))).scalars().first()
        if user is None:
            verify_password(password, DUMMY_HASH)  # equalise timing
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")
        if not verify_password(password, user.hashed_password):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")
        if not user.is_active or user.role == "guest" or user.email == LEGACY_SHARED_GUEST:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")
        if settings.is_production and password.lower() in KNOWN_DEFAULT_PASSWORDS:
            logger.critical("Blocked login with a known default password for user id=%s", user.id)
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                "This account uses a known default password and has been locked. Reset it via the server.")
        if needs_rehash(user.hashed_password):
            user.hashed_password = get_password_hash(password)  # transparent bcrypt -> argon2id upgrade
        return user

    @staticmethod
    async def create_session(db: AsyncSession, user: User, user_agent: str = "") -> Tuple[str, str, AuthSession]:
        sid = str(uuid.uuid4())
        refresh = new_refresh_token(sid)
        s = AuthSession(id=sid, user_id=user.id, refresh_token_hash=hash_refresh_token(refresh),
                        expires_at=utcnow() + datetime.timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
                        user_agent=(user_agent or "")[:255])
        db.add(s)
        user.last_login_at = utcnow()
        await db.commit()
        return create_access_token(user.id, sid, user.role), refresh, s

    @staticmethod
    async def rotate_refresh(db: AsyncSession, refresh_token: str) -> Tuple[User, str, str, AuthSession]:
        sid = (refresh_token or "").split(".", 1)[0]
        s = await db.get(AuthSession, sid) if sid else None
        if s is None or s.revoked_at is not None or s.expires_at < utcnow():
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired. Please sign in again.")
        if not secrets.compare_digest(s.refresh_token_hash, hash_refresh_token(refresh_token)):
            # A stale refresh token was replayed: assume theft and revoke the whole session.
            s.revoked_at = utcnow()
            await db.commit()
            logger.warning("Refresh token reuse detected; session revoked (user id=%s)", s.user_id)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired. Please sign in again.")
        user = await db.get(User, s.user_id)
        if user is None or not user.is_active:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired. Please sign in again.")
        new_refresh = new_refresh_token(sid)
        s.refresh_token_hash = hash_refresh_token(new_refresh)
        await db.commit()
        return user, create_access_token(user.id, sid, user.role), new_refresh, s

    @staticmethod
    async def revoke_session(db: AsyncSession, session_id: Optional[str]) -> None:
        if session_id:
            await db.execute(update(AuthSession).where(AuthSession.id == session_id, AuthSession.revoked_at.is_(None))
                             .values(revoked_at=utcnow()))
            await db.commit()

    @staticmethod
    async def revoke_all_sessions(db: AsyncSession, user_id: int, except_session: Optional[str] = None) -> None:
        stmt = update(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        if except_session:
            stmt = stmt.where(AuthSession.id != except_session)
        await db.execute(stmt.values(revoked_at=utcnow()))
        await db.commit()

    @staticmethod
    async def create_guest(db: AsyncSession) -> User:
        if not settings.ALLOW_GUEST:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Guest access is disabled. Please sign up.")
        user = User(email=f"guest-{uuid.uuid4().hex}@{GUEST_DOMAIN}",
                    hashed_password="!unusable",  # nosec B106 - marker, not a password: login is impossible
                    full_name="Guest", role="guest", is_active=True)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    # --- MFA ---
    @staticmethod
    async def verify_second_factor(db: AsyncSession, user: User, code: str) -> bool:
        if mfa.verify_totp(user.mfa_secret, code):
            return True
        ok, updated = mfa.consume_recovery_code(user.mfa_recovery_codes, code)
        if ok:
            user.mfa_recovery_codes = updated
            await db.commit()
        return ok

    @staticmethod
    async def purge_expired_guests(db: AsyncSession) -> int:
        cutoff = utcnow() - datetime.timedelta(hours=settings.GUEST_TTL_HOURS)
        res = await db.execute(select(User.id).where(User.role == "guest", User.created_at < cutoff))
        ids = list(res.scalars().all())
        if ids:
            from app.models.document import Document
            from app.ingestion import storage
            docs = (await db.execute(select(Document.filepath).where(Document.user_id.in_(ids)))).scalars().all()
            for ref in docs:
                storage.delete(ref)
            await db.execute(delete(User).where(User.id.in_(ids)))
        await db.execute(delete(AuthSession).where(AuthSession.expires_at < utcnow() - datetime.timedelta(days=1)))
        await db.commit()
        return len(ids)
