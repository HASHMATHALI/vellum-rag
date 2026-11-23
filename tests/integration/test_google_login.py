"""Sign in with Google. Google's token verification is stubbed (no network); everything after it is real."""
import pyotp
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.auth import google
from app.config.settings import settings
from app.database.connection import system_session
from app.models.user import User
from tests.conftest import PASSWORD, bearer, login, make_user


@pytest.fixture
def google_enabled(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "1234-test.apps.googleusercontent.com")
    claims = {}

    async def fake_verify(credential):
        if credential == "invalid-token-xxxxxxxxxxxxxxxx":
            raise HTTPException(401, "Google sign-in failed. Please try again.")
        return dict(claims)

    monkeypatch.setattr(google, "verify_google_token", fake_verify)
    return claims


TOKEN = "header.payload.signature-from-google"


async def test_config_reports_google_client_id(client, monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "")
    assert (await client.get("/api/auth/config")).json()["google_client_id"] is None
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "abc.apps.googleusercontent.com")
    assert (await client.get("/api/auth/config")).json()["google_client_id"] == "abc.apps.googleusercontent.com"


async def test_google_login_disabled_without_client_id(client, monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "")
    r = await client.post("/api/auth/google", json={"credential": TOKEN})
    assert r.status_code == 404


async def test_new_google_user_gets_a_session_and_no_password_login(client, unique, google_enabled):
    email = unique("g-new")
    google_enabled.update(sub="g-111", email=email, email_verified=True, name="Gina Google", iss="accounts.google.com")
    r = await client.post("/api/auth/google", json={"credential": TOKEN})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["email"] == email and body["user"]["role"] == "user" and body["csrf_token"]
    assert any(c.startswith("vellum_access=") and "HttpOnly" in c for c in r.headers.get_list("set-cookie"))
    # a Google-only account has no usable password
    assert (await client.post("/api/auth/login", json={"email": email, "password": "!google-only"})).status_code == 401
    # signing in again finds the same account by Google id
    client.cookies.clear()
    again = await client.post("/api/auth/google", json={"credential": TOKEN})
    assert again.json()["user"]["id"] == body["user"]["id"]


async def test_existing_account_is_linked_by_verified_email(client, unique, google_enabled):
    email = unique("g-link")
    existing = await make_user(email)
    google_enabled.update(sub="g-222", email=email.upper(), email_verified=True, iss="https://accounts.google.com")
    r = await client.post("/api/auth/google", json={"credential": TOKEN})
    assert r.status_code == 200 and r.json()["user"]["id"] == existing.id
    async with system_session() as db:
        u = (await db.execute(select(User).where(User.id == existing.id))).scalars().one()
    assert u.google_sub == "g-222"
    client.cookies.clear()
    assert (await login(client, email))["user"]["id"] == existing.id  # password login still works


async def test_unverified_google_email_is_rejected(client, unique, google_enabled):
    google_enabled.update(sub="g-333", email=unique("g-unv"), email_verified=False)
    assert (await client.post("/api/auth/google", json={"credential": TOKEN})).status_code == 401


async def test_email_linked_to_another_google_account_conflicts(client, unique, google_enabled):
    email = unique("g-conf")
    google_enabled.update(sub="g-444", email=email, email_verified=True)
    assert (await client.post("/api/auth/google", json={"credential": TOKEN})).status_code == 200
    client.cookies.clear()
    google_enabled.update(sub="g-999-other", email=email, email_verified=True)
    assert (await client.post("/api/auth/google", json={"credential": TOKEN})).status_code == 409


async def test_google_login_still_requires_mfa(client, unique, google_enabled):
    email = unique("g-mfa")
    await make_user(email)
    s = await login(client, email)
    client.cookies.clear()
    secret = (await client.post("/api/auth/mfa/setup", headers=bearer(s))).json()["secret"]
    assert (await client.post("/api/auth/mfa/enable", json={"code": pyotp.TOTP(secret).now()}, headers=bearer(s))).status_code == 200
    google_enabled.update(sub="g-555", email=email, email_verified=True)
    r = await client.post("/api/auth/google", json={"credential": TOKEN})
    assert r.json().get("mfa_required") is True and "access_token" not in r.json()
    ok = await client.post("/api/auth/login/mfa", json={"mfa_token": r.json()["mfa_token"], "code": pyotp.TOTP(secret).now()})
    assert ok.status_code == 200


async def test_invalid_google_token_is_rejected(client, google_enabled):
    r = await client.post("/api/auth/google", json={"credential": "invalid-token-xxxxxxxxxxxxxxxx"})
    assert r.status_code == 401 and "Traceback" not in r.text


async def test_real_verifier_rejects_a_forged_token(monkeypatch):
    """Without stubs: a token not signed by Google never verifies (no network needed: it fails before key lookup
    or on the signature)."""
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "1234-test.apps.googleusercontent.com")
    import jwt as pyjwt
    forged = pyjwt.encode({"sub": "1", "email": "x@gmail.com", "email_verified": True, "aud": "1234-test.apps.googleusercontent.com",
                           "iss": "accounts.google.com", "exp": 9999999999}, "attacker-key", algorithm="HS256")
    with pytest.raises(HTTPException) as e:
        await google.verify_google_token(forged)
    assert e.value.status_code == 401
