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
