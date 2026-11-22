import pyotp
import pytest

from app.auth.jwt import get_password_hash
from app.database.connection import system_session
from app.models.user import User
from tests.conftest import PASSWORD, bearer, login, make_user


async def test_register_login_profile_and_no_auto_admin(client, unique):
    email = unique("reg")
    r = await client.post("/api/auth/register", json={"email": email, "password": PASSWORD, "full_name": "Reg User"})
    assert r.status_code == 201 and r.json()["role"] == "user"  # never auto-promoted
    s = await login(client, email)
    prof = await client.get("/api/auth/profile", headers=bearer(s))
    assert prof.status_code == 200 and prof.json()["email"] == email


@pytest.mark.parametrize("pw", ["short", "admin123", "aaaaaaaaaaaaaa"])
async def test_weak_passwords_rejected(client, unique, pw):
    r = await client.post("/api/auth/register", json={"email": unique(), "password": pw, "full_name": "Weak"})
    assert r.status_code == 422


async def test_password_stored_as_argon2(client, unique):
    email = unique("hash")
    await client.post("/api/auth/register", json={"email": email, "password": PASSWORD, "full_name": "Hash"})
    async with system_session() as db:
        from sqlalchemy import select
        u = (await db.execute(select(User).where(User.email == email))).scalars().one()
    assert u.hashed_password.startswith("$argon2id$") and PASSWORD not in u.hashed_password


async def test_unauthenticated_requests_are_rejected(client):
    for method, url in [("get", "/api/documents"), ("get", "/api/history"), ("get", "/api/auth/profile"),
                        ("post", "/api/query"), ("get", "/api/stats")]:
        r = await getattr(client, method)(url, **({"json": {"message": "x"}} if method == "post" else {}))
        assert r.status_code == 401, url


@pytest.mark.parametrize("payload", [
    {"email": "admin@vellum.ai' OR '1'='1", "password": "x"},
    {"email": "x@example.com", "password": "' OR '1'='1' --"},
    {"email": "x@example.com'; DROP TABLE users;--", "password": "x"},
])
async def test_login_sql_injection_attempts_fail_safely(client, payload):
    r = await client.post("/api/auth/login", json=payload)
    assert r.status_code in (401, 422)
    async with system_session() as db:  # table still exists
        from sqlalchemy import func, select
        assert (await db.execute(select(func.count(User.id)))).scalar() >= 0


async def test_cookie_session_flags_csrf_and_logout(client, unique):
    email = unique("cookie")
    await make_user(email)
    r = await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    cookies = r.headers.get_list("set-cookie")
    access = next(c for c in cookies if c.startswith("vellum_access="))
    refresh = next(c for c in cookies if c.startswith("vellum_refresh="))
    assert "HttpOnly" in access and "samesite=lax" in access.lower() and "Path=/api" in access
    assert "HttpOnly" in refresh and "Path=/api/auth" in refresh
    csrf = r.json()["csrf_token"]
    # cookie auth: safe method OK, state-changing without CSRF header -> 403, with header -> allowed
    assert (await client.get("/api/documents")).status_code == 200
    assert (await client.post("/api/query", json={"message": "hi"})).status_code == 403
    bad = await client.post("/api/query", json={"message": "hi"}, headers={"X-CSRF-Token": "forged"})
    assert bad.status_code == 403
    ok = await client.post("/api/query", json={"message": "hi"}, headers={"X-CSRF-Token": csrf})
    assert ok.status_code == 200
    # logout revokes the server-side session: the old access token stops working
    token = r.json()["access_token"]
    out = await client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    assert out.status_code == 204
    assert (await client.get("/api/documents", headers={"Authorization": f"Bearer {token}"})).status_code == 401


async def test_bearer_requests_do_not_need_csrf(client, unique):
    email = unique("bearer")
    await make_user(email)
    s = await login(client, email)
    client.cookies.clear()
    r = await client.post("/api/query", json={"message": "hello"}, headers=bearer(s))
    assert r.status_code == 200


async def test_refresh_rotation_and_reuse_detection(client, unique):
    email = unique("refresh")
    await make_user(email)
    await login(client, email)
    old_refresh = client.cookies.get("vellum_refresh")
    r1 = await client.post("/api/auth/refresh")
    assert r1.status_code == 200
    new_refresh = client.cookies.get("vellum_refresh")
    assert new_refresh and new_refresh != old_refresh
    client.cookies.clear()
    replay = await client.post("/api/auth/refresh", cookies={"vellum_refresh": old_refresh})
    assert replay.status_code == 401
    # reuse revoked the whole session, so even the latest token is now dead
    assert (await client.post("/api/auth/refresh", cookies={"vellum_refresh": new_refresh})).status_code == 401


async def test_password_change_requires_current_password_and_revokes_other_sessions(client, unique):
    email = unique("pwchange")
    await make_user(email)
    s1 = await login(client, email)
    s2 = await login(client, email)
    client.cookies.clear()
    bad = await client.post("/api/auth/password", json={"current_password": "wrong", "new_password": "Another-Strong-77"}, headers=bearer(s1))
    assert bad.status_code == 400
    ok = await client.post("/api/auth/password", json={"current_password": PASSWORD, "new_password": "Another-Strong-77"}, headers=bearer(s1))
    assert ok.status_code == 204
    assert (await client.get("/api/documents", headers=bearer(s2))).status_code == 401
    assert (await client.get("/api/documents", headers=bearer(s1))).status_code == 200


async def test_mfa_enrolment_login_and_recovery(client, unique):
    email = unique("mfa")
    await make_user(email)
    s = await login(client, email)
    client.cookies.clear()
    setup = (await client.post("/api/auth/mfa/setup", headers=bearer(s))).json()
    totp = pyotp.TOTP(setup["secret"])
    assert (await client.post("/api/auth/mfa/enable", json={"code": "123456" if totp.now() != "123456" else "654321"},
                              headers=bearer(s))).status_code == 400
    en = await client.post("/api/auth/mfa/enable", json={"code": totp.now()}, headers=bearer(s))
    assert en.status_code == 200 and len(en.json()["recovery_codes"]) == 8
    recovery = en.json()["recovery_codes"][0]
    # password alone is no longer enough
    step1 = (await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})).json()
    assert step1["mfa_required"] and "access_token" not in step1
    assert (await client.post("/api/auth/login/mfa", json={"mfa_token": step1["mfa_token"], "code": "000000"})).status_code == 401
    ok = await client.post("/api/auth/login/mfa", json={"mfa_token": step1["mfa_token"], "code": totp.now()})
    assert ok.status_code == 200 and ok.json()["user"]["mfa_enabled"]
    # recovery code works once
    step1 = (await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})).json()
    assert (await client.post("/api/auth/login/mfa", json={"mfa_token": step1["mfa_token"], "code": recovery})).status_code == 200
    step1 = (await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})).json()
    assert (await client.post("/api/auth/login/mfa", json={"mfa_token": step1["mfa_token"], "code": recovery})).status_code == 401


async def test_guest_accounts_are_isolated_and_cannot_password_login(client):
    g1 = (await client.post("/api/auth/guest")).json()
    client.cookies.clear()
    g2 = (await client.post("/api/auth/guest")).json()
    client.cookies.clear()
    assert g1["user"]["id"] != g2["user"]["id"] and g1["user"]["role"] == "guest"
    up = await client.post("/api/upload", headers=bearer(g1), files={"file": ("g1.txt", b"guest one secret: ZEBRA-17", "text/plain")})
    assert up.status_code == 201
    assert (await client.get("/api/documents", headers=bearer(g2))).json() == []
    assert (await client.post("/api/auth/mfa/setup", headers=bearer(g1))).status_code == 403


async def test_legacy_shared_guest_and_default_admin_cannot_log_in(client):
    import bcrypt
    async with system_session() as db:
        db.add(User(email="guest@vellum.ai", hashed_password=bcrypt.hashpw(b"guest123", bcrypt.gensalt()).decode(),
                    full_name="Guest", role="user"))
        await db.commit()
    r = await client.post("/api/auth/login", json={"email": "guest@vellum.ai", "password": "guest123"})
    assert r.status_code == 401


async def test_login_rate_limit(client, unique):
    email = unique("brute")
    await make_user(email)
    codes = [(await client.post("/api/auth/login", json={"email": email, "password": "wrong-password"})).status_code
             for _ in range(12)]
    assert codes[:10] == [401] * 10 and 429 in codes[10:]


async def test_admin_endpoints_require_admin(client, unique):
    user_email, admin_email = unique("plain"), unique("admin")
    await make_user(user_email)
    await make_user(admin_email, role="admin")
    u, a = await login(client, user_email), await login(client, admin_email)
    client.cookies.clear()
    for url in ("/api/stats", "/api/logs"):
        assert (await client.get(url, headers=bearer(u))).status_code == 403
        assert (await client.get(url, headers=bearer(a))).status_code == 200
    assert (await client.post("/api/build-index", headers=bearer(u))).status_code == 403
    stats = (await client.get("/api/stats", headers=bearer(a))).json()
    assert stats["most_asked_questions"] == []  # other users' questions are not exposed


async def test_account_deletion_removes_data(client, unique):
    email = unique("delete")
    await make_user(email)
    s = await login(client, email)
    client.cookies.clear()
    up = await client.post("/api/upload", headers=bearer(s), files={"file": ("d.txt", b"to be deleted content", "text/plain")})
    assert up.status_code == 201
    r = await client.request("DELETE", "/api/auth/account", json={"password": PASSWORD}, headers=bearer(s))
    assert r.status_code == 204
    async with system_session() as db:
        from sqlalchemy import func, select
        from app.models.document import Document
        assert (await db.execute(select(func.count(Document.id)).where(Document.id == up.json()["id"]))).scalar() == 0
