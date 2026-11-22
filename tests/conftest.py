"""Test configuration.

All tests run against an isolated database (TEST_DATABASE_URL, default: the embedded PostgreSQL 'rag_test'
database from scripts/local_postgres.py). They never read the repository .env, so they cannot reach production.
The LLM is replaced by a deterministic fake except in tests marked `live`.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _test_db_url() -> str:
    if os.environ.get("TEST_DATABASE_URL"):
        return os.environ["TEST_DATABASE_URL"]
    out = subprocess.check_output([sys.executable, str(ROOT / "scripts" / "local_postgres.py"), "rag_test"], text=True,
                                  stderr=subprocess.DEVNULL)
    return [l for l in out.splitlines() if l.startswith("rag_test=")][0].split("=", 1)[1]


_live_key = ""
if (ROOT / ".env").exists():
    for _line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if _line.startswith("GROQ_API_KEY="):
            _live_key = _line.split("=", 1)[1].strip().strip('"')

os.environ.update({
    "DATABASE_URL": _test_db_url(), "ENVIRONMENT": "test", "SUPABASE_URL": "", "SUPABASE_KEY": "", "REDIS_URL": "",
    "GROQ_API_KEY": _live_key if "live" in " ".join(sys.argv) else "", "LOG_FILE": "", "COOKIE_SECURE": "false",
    "UPLOAD_DIR": str(ROOT / "backend" / ".test_uploads"), "JWT_SECRET_KEY": "test-" + "x" * 60,
    "CORS_ORIGINS": "http://localhost:5173", "ADMIN_EMAIL": "", "ADMIN_PASSWORD": "",
})
sys.path.insert(0, str(ROOT / "backend"))

import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.database.connection import async_session, engine, system_session  # noqa: E402
from app.database.migrations import run_migrations  # noqa: E402
from app.main import app  # noqa: E402
from app.middleware.rate_limiter import limiter  # noqa: E402
from app.models.user import User  # noqa: E402
from app.auth.jwt import get_password_hash  # noqa: E402

PASSWORD = "Correct-Horse-42!"


class FakeLLM:
    """Deterministic stand-in for Groq: answers by citing source 1 and records the messages it received."""

    def __init__(self):
        self.calls = []
        self.fail = False
        self.available = True

    async def stream_chat_completion(self, messages, usage=None, **kw):
        from app.llm.groq_client import LLMError
        self.calls.append(messages)
        if self.fail:
            raise LLMError("The language model is temporarily unavailable. Please try again in a moment.")
        if usage is not None:
            usage.model, usage.prompt_tokens, usage.completion_tokens = "fake-llm", 100, 10
        for tok in ["According to the documents, ", "the answer is in the first source ", "[1]."]:
            yield tok

    async def generate_chat_completion(self, messages, **kw):
        self.calls.append(messages)
        return "standalone rewritten query"


@pytest.fixture(scope="session", autouse=True)
async def database():
    # The schema is wiped below: refuse anything that is not a local database unless explicitly allowed.
    host = engine.url.host or ""
    if host not in ("127.0.0.1", "localhost", "::1") and os.environ.get("ALLOW_DESTRUCTIVE_TEST_DB") != "1":
        pytest.exit(f"Refusing to reset non-local test database host '{host}'", returncode=2)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await run_migrations(engine)
    yield
    await engine.dispose()


@pytest.fixture(autouse=True)
def fake_llm(monkeypatch, request):
    limiter.reset()
    if request.node.get_closest_marker("live"):
        return None  # live tests use the real Groq client
    from app.rag import pipeline as p
    fake = FakeLLM()
    monkeypatch.setattr(p.pipeline, "llm", fake)
    return fake


@pytest.fixture
async def client():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def make_user(email: str, role: str = "user", password: str = PASSWORD) -> User:
    async with system_session() as db:
        u = User(email=email, hashed_password=get_password_hash(password), full_name="Test User", role=role)
        db.add(u)
        await db.commit()
        await db.refresh(u)
        return u


async def login(client: httpx.AsyncClient, email: str, password: str = PASSWORD) -> dict:
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def bearer(session: dict) -> dict:
    return {"Authorization": f"Bearer {session['access_token']}"}


async def wait_indexed(client, headers, doc_id):
    r = await client.get(f"/api/document/{doc_id}", headers=headers)
    return r.json()


def parse_sse(body: str):
    events, ev = [], None
    import json
    for line in body.splitlines():
        if line.startswith("event:"):
            ev = line[6:].strip()
        elif line.startswith("data:"):
            events.append((ev or "message", json.loads(line[5:])))
            ev = None
    return events


@pytest.fixture
def unique():
    import uuid
    return lambda prefix="u": f"{prefix}-{uuid.uuid4().hex[:10]}@example.com"
