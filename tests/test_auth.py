import sys
import os
# Ensure app modules are importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from app.auth.jwt import get_password_hash, verify_password, create_access_token, decode_token

def test_password_hashing():
    password = "supersecretpassword123"
    hashed = get_password_hash(password)
    
    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("wrongpassword", hashed) is False

def test_jwt_token_generation():
    payload = {"sub": "test@example.com", "role": "user"}
    token = create_access_token(payload)
    
    assert isinstance(token, str)
    decoded = decode_token(token)
    assert decoded is not None
    assert decoded["sub"] == "test@example.com"
    assert decoded["role"] == "user"


# --- password limits (bcrypt>=5 refuses input over 72 bytes) ---
import pytest
from pydantic import ValidationError
from app.auth.jwt import password_problem, MAX_PASSWORD_BYTES
from app.api.schemas import UserRegister, UserProfileUpdate


def test_password_problem_limits():
    assert password_problem("short") is not None
    assert password_problem("long enough") is None
    assert password_problem("a" * MAX_PASSWORD_BYTES) is None
    assert password_problem("a" * (MAX_PASSWORD_BYTES + 1)) is not None
    # 25 three-byte characters are 75 bytes, over the limit despite being 25 characters
    assert password_problem("अ" * 25) is not None


def test_hashing_a_too_long_password_gives_a_clear_error_not_a_crash():
    with pytest.raises(ValueError, match="at most 72 bytes"):
        get_password_hash("a" * 100)
    # and verifying a too-long password simply fails
    assert verify_password("a" * 100, get_password_hash("a" * 72)) is False


def test_registration_rejects_out_of_range_passwords():
    ok = UserRegister(email="a@example.com", password="secret1", full_name="Ana")
    assert ok.password == "secret1"
    for bad in ("12345", "x" * 80):
        with pytest.raises(ValidationError):
            UserRegister(email="a@example.com", password=bad, full_name="Ana")


def test_profile_update_no_longer_accepts_an_empty_password():
    assert UserProfileUpdate(full_name="Ana").password is None
    assert UserProfileUpdate(password="newsecret").password == "newsecret"
    for bad in ("", "abc", "x" * 80):
        with pytest.raises(ValidationError):
            UserProfileUpdate(password=bad)
