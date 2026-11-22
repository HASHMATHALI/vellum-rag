"""TOTP multi-factor authentication (RFC 6238) with single-use, hashed recovery codes."""
import json
import secrets
from typing import List, Optional, Tuple

import pyotp

from app.auth.jwt import get_password_hash, verify_password
from app.config.settings import settings


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=settings.PROJECT_NAME)


def verify_totp(secret: Optional[str], code: str) -> bool:
    if not secret or not code:
        return False
    code = code.strip().replace(" ", "")
    if not code.isdigit() or len(code) != 6:
        return False
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def new_recovery_codes(n: int = 8) -> Tuple[List[str], str]:
    codes = [f"{secrets.token_hex(4)}-{secrets.token_hex(4)}" for _ in range(n)]
    return codes, json.dumps([get_password_hash(c) for c in codes])


def consume_recovery_code(stored: Optional[str], code: str) -> Tuple[bool, Optional[str]]:
    """Returns (ok, updated_json). A matched code is removed so it cannot be reused."""
    if not stored or not code:
        return False, stored
    hashes = json.loads(stored)
    code = code.strip().lower()
    for i, h in enumerate(hashes):
        if verify_password(code, h):
            del hashes[i]
            return True, json.dumps(hashes)
    return False, stored
