"""Password hashing and JWT helpers.

- Passwords: Argon2id (argon2-cffi defaults: t=3, m=64 MiB, p=4). Legacy bcrypt hashes still verify and are
  re-hashed with Argon2id on the next successful login (`needs_rehash`).
- Tokens: PyJWT (replaces python-jose, CVE-2024-33663/33664), HS256 only, with iss/aud/exp/iat/jti/typ checks.
"""
import datetime
import hashlib
import hmac
import secrets
import uuid
from typing import Optional

import bcrypt
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.config.settings import settings

_ph = PasswordHasher()
ALLOWED_ALGORITHMS = ["HS256"]


def get_password_hash(password: str) -> str:
    return _ph.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password:
        return False
    if hashed_password.startswith("$argon2"):
        try:
            return _ph.verify(hashed_password, plain_password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False
    if hashed_password.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
        except ValueError:
            return False
    return False


def needs_rehash(hashed_password: str) -> bool:
    if not hashed_password.startswith("$argon2"):
        return True
    try:
        return _ph.check_needs_rehash(hashed_password)
    except InvalidHashError:
        return True


# A valid hash of a random value, used to equalise timing when the user does not exist.
DUMMY_HASH = get_password_hash(secrets.token_urlsafe(16))


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def create_token(subject: str, token_type: str, expires_delta: datetime.timedelta, extra: Optional[dict] = None) -> str:
    now = _now()
    payload = {
        "sub": subject,
        "typ": token_type,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "iat": now,
        "nbf": now,
        "exp": now + expires_delta,
        "jti": str(uuid.uuid4()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: int, session_id: str, role: str) -> str:
    return create_token(str(user_id), "access", datetime.timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
                        {"sid": session_id, "role": role})


def create_mfa_token(user_id: int) -> str:
    return create_token(str(user_id), "mfa", datetime.timedelta(minutes=settings.MFA_TOKEN_EXPIRE_MINUTES))


def decode_token(token: str, expected_type: str = "access") -> Optional[dict]:
    if settings.JWT_ALGORITHM not in ALLOWED_ALGORITHMS:
        return None
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=ALLOWED_ALGORITHMS,
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
            options={"require": ["exp", "iat", "sub", "iss", "aud", "jti", "typ"]},
        )
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != expected_type:
        return None
    return payload


# --- Opaque refresh tokens & CSRF -------------------------------------------------------------

def new_refresh_token(session_id: str) -> str:
    return f"{session_id}.{secrets.token_urlsafe(32)}"


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def csrf_token_for(session_id: str) -> str:
    """Stateless CSRF token bound to the server-side session (HMAC), sent back in the X-CSRF-Token header."""
    return hmac.new(settings.JWT_SECRET_KEY.encode(), f"csrf:{session_id}".encode(), hashlib.sha256).hexdigest()


def verify_csrf(session_id: str, token: Optional[str]) -> bool:
    return bool(token) and hmac.compare_digest(csrf_token_for(session_id), token)
