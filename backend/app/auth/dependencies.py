"""Authentication & authorisation dependencies.

Credentials are accepted from (1) the HttpOnly `vellum_access` cookie set by the browser login flow, or
(2) an `Authorization: Bearer` header (API clients, evaluation scripts). Cookie-authenticated, state-changing
requests must also carry a valid X-CSRF-Token header. Every token is checked against its server-side session
so logout / password change revoke it immediately. There is no anonymous fallback user.
"""
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import decode_token, verify_csrf
from app.database.connection import get_db, set_rls_context
from app.models.user import AuthSession, User, utcnow

ACCESS_COOKIE = "vellum_access"
REFRESH_COOKIE = "vellum_refresh"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

bearer_scheme = HTTPBearer(auto_error=False)

_unauthorized = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    via_cookie = False
    token = credentials.credentials if credentials else None
    if not token:
        token = request.cookies.get(ACCESS_COOKIE)
        via_cookie = token is not None
    if not token:
        raise _unauthorized

    payload = decode_token(token, "access")
    if payload is None:
        raise _unauthorized
    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError):
        raise _unauthorized
    session_id = payload.get("sid")

    auth_session = await db.get(AuthSession, session_id) if session_id else None
    if auth_session is None or auth_session.user_id != user_id or auth_session.revoked_at is not None \
            or auth_session.expires_at < utcnow():
        raise _unauthorized

    if via_cookie and request.method not in SAFE_METHODS:
        if not verify_csrf(session_id, request.headers.get(CSRF_HEADER)):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token missing or invalid")

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized

    request.state.user = user
    request.state.session_id = session_id
    await set_rls_context(db, user.id, is_admin=user.role == "admin")
    return user


async def get_registered_user(current_user: User = Depends(get_current_user)) -> User:
    """Excludes anonymous guest accounts (e.g. for MFA or profile changes)."""
    if current_user.role == "guest":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Create an account to use this feature")
    return current_user


async def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access forbidden: insufficient privileges")
    return current_user
