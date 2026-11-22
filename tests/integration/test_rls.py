"""Row-level security: applies backend/app/database/rls.sql to the test database, connects as the non-superuser
`vellum_app` role and checks that the database itself enforces tenant isolation (defence in depth)."""
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.connection import engine, set_rls_context, system_session
from app.embeddings.embedder import embedder
from app.models.document import Document, DocumentChunk
from app.models.user import User
from app.retrieval.retriever import Retriever

pytestmark = pytest.mark.rls
RLS_SQL = Path(__file__).resolve().parents[2] / "backend" / "app" / "database" / "rls.sql"
APP_PW = "rls-test-Password-123"


@pytest.fixture(scope="module")
async def rls_engine():
    sql = RLS_SQL.read_text(encoding="utf-8").replace(":app_password", f"'{APP_PW}'")
    stmts, buf, in_dollar = [], [], False
    for line in sql.splitlines():
        if line.strip().startswith("--") and not in_dollar:
            continue
        buf.append(line)
        in_dollar ^= line.count("$$") % 2 == 1
        if line.rstrip().endswith(";") and not in_dollar:
            stmts.append("\n".join(buf))
            buf = []
    async with engine.begin() as conn:
        for s in stmts:
            await conn.execute(text(s))
    url = engine.url.set(username="vellum_app", password=APP_PW)
    eng = create_async_engine(url)
    yield eng
    await eng.dispose()
    async with engine.begin() as conn:  # leave the shared test DB without RLS for the other tests
        for t in ("documents", "document_chunks", "chat_sessions", "chat_messages"):
            await conn.execute(text(f"ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY"))
            await conn.execute(text(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY"))


async def _seed(email, secret):
    async with system_session() as db:
        u = User(email=email, hashed_password="!unusable", full_name="R", role="user")
        db.add(u)
        await db.flush()
        d = Document(filename=f"{email}.txt", filepath="local:x", file_type="txt", file_size=1, user_id=u.id, status="indexed")
        db.add(d)
        await db.flush()
        db.add(DocumentChunk(document_id=d.id, user_id=u.id, chunk_index=0, text_content=secret, page_number=1,
                             embedding=embedder.get_embeddings([secret])[0].tolist()))
        await db.commit()
        return u.id, d.id


async def test_rls_enforces_isolation_at_database_level(rls_engine, monkeypatch):
    monkeypatch.setattr("app.database.connection.settings.ENABLE_RLS", True)
    a_id, a_doc = await _seed("rls-a@example.com", "Alpha secret: the vault code is 9911.")
    b_id, _ = await _seed("rls-b@example.com", "Bravo notes about gardening.")
    Session = async_sessionmaker(rls_engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:  # no context at all: fail closed
        assert (await db.execute(text("SELECT count(*) FROM documents"))).scalar() == 0
        assert (await db.execute(text("SELECT count(*) FROM document_chunks"))).scalar() == 0

    async with Session() as db:  # Bob sees only his own rows, even with an unfiltered query
        await db.execute(text("SELECT 1"))
        await set_rls_context(db, b_id)
        owners = set((await db.execute(text("SELECT user_id FROM document_chunks"))).scalars().all())
        assert owners == {b_id}
        assert (await db.execute(text("SELECT count(*) FROM documents WHERE id = :d"), {"d": a_doc})).scalar() == 0
        # context survives a commit (re-applied by the after_begin hook)
        await db.commit()
        owners = set((await db.execute(text("SELECT user_id FROM document_chunks"))).scalars().all())
        assert owners == {b_id}
        # even if application code forgot the owner filter, Alice's text is unreachable
        res = await Retriever.search(db, "vault code", user_id=b_id, mode="hybrid", k=5, apply_threshold=False)
        assert all("vault" not in r.text for r in res)
        # writes for another tenant are rejected by WITH CHECK
        with pytest.raises(Exception):
            await db.execute(text("INSERT INTO documents (filename, filepath, file_type, file_size, user_id, status, total_chunks, created_at) "
                                  "VALUES ('x','x','txt',1,:u,'indexed',0, now())"), {"u": a_id})
        await db.rollback()

    async with Session() as db:  # admin may list documents but never read other users' chunk text
        await db.execute(text("SELECT 1"))
        await set_rls_context(db, b_id, is_admin=True)
        assert (await db.execute(text("SELECT count(*) FROM documents WHERE id = :d"), {"d": a_doc})).scalar() == 1
        assert (await db.execute(text("SELECT count(*) FROM document_chunks WHERE user_id = :u"), {"u": a_id})).scalar() == 0

    async with Session() as db:  # Alice's own retrieval still works under RLS
        await db.execute(text("SELECT 1"))
        await set_rls_context(db, a_id)
        res = await Retriever.search(db, "What is the vault code?", user_id=a_id, mode="hybrid", k=3, apply_threshold=False)
        assert res and "9911" in res[0].text


async def test_app_role_is_not_superuser_and_cannot_bypass_rls(rls_engine):
    async with rls_engine.connect() as conn:
        row = (await conn.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"))).one()
        assert row == (False, False)
        with pytest.raises(Exception):
            await conn.execute(text("ALTER TABLE documents DISABLE ROW LEVEL SECURITY"))
