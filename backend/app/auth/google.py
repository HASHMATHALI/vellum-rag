"""Sign in with Google (Google Identity Services ID-token flow).

The browser obtains a signed ID token (JWT) from Google's sign-in button and posts it to /api/auth/google.
We verify it server-side with Google's published keys (signature, `aud` = our client ID, `iss`, `exp`) and
require `email_verified`. No client secret is needed and no Google access token ever reaches our server.
"""
import logging
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.config.settings import settings
from app.models.user import User

logger = logging.getLogger(__name__)
GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
_request = None


def client_ids() -> list:
    return [c.strip() for c in settings.GOOGLE_CLIENT_ID.split(",") if c.strip()]


def enabled() -> bool:
    return bool(client_ids())


def _verify_sync(credential: str) -> dict:
    global _request
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token
    if _request is None:
        _request = google_requests.Request()  # caches Google's signing certificates
    last: Optional[Exception] = None
    for cid in client_ids():
        try:
            return id_token.verify_oauth2_token(credential, _request, audience=cid, clock_skew_in_seconds=10)
        except ValueError as e:  # wrong audience, bad signature, expired...
            last = e
    raise ValueError(str(last) if last else "no client id configured")


async def verify_google_token(credential: str) -> dict:
    """Returns verified claims or raises HTTP 401. Monkeypatched in tests."""
    if not enabled():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Google sign-in is not enabled on this server.")
    try:
        claims = await run_in_threadpool(_verify_sync, credential)
    except Exception as e:
        logger.warning("Rejected Google ID token (%s)", type(e).__name__)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Google sign-in failed. Please try again.")
    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Google sign-in failed. Please try again.")
    return claims


async def user_for_google(db: AsyncSession, claims: dict) -> User:
    """Find the account for a verified Google identity, linking or creating it as needed."""
    sub = str(claims.get("sub") or "")
    email = str(claims.get("email") or "").strip().lower()
    if not sub or not email or claims.get("email_verified") not in (True, "true"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your Google account e-mail is not verified.")

    user = (await db.execute(select(User).where(User.google_sub == sub))).scalars().first()
    if user is None:
        user = (await db.execute(select(User).where(func.lower(User.email) == email))).scalars().first()
        if user is not None:
            if user.google_sub and user.google_sub != sub:
                raise HTTPException(status.HTTP_409_CONFLICT, "This e-mail is linked to a different Google account.")
            if user.role == "guest":
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Google sign-in failed. Please try again.")
            user.google_sub = sub  # Google has verified ownership of this e-mail: link the existing account
        else:
            user = User(email=email, hashed_password="!google-only",  # nosec B106 - unusable marker, not a password
                        full_name=(claims.get("name") or email.split("@")[0])[:255], role="user",
                        is_active=True, google_sub=sub)
            db.add(user)
        await db.commit()
        await db.refresh(user)
    if not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "This account is disabled.")
    return user
