"""Idempotent schema setup and upgrades, run at startup.

`Base.metadata.create_all` only creates missing tables, so columns and indexes added after the first
deployment are applied here with IF NOT EXISTS statements. Every statement is safe to re-run.
"""
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config.settings import settings

logger = logging.getLogger(__name__)

UPGRADE_STATEMENTS = [
    # users: MFA + login bookkeeping
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_enabled boolean NOT NULL DEFAULT false",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_secret varchar(64)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_recovery_codes text",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at timestamp",
    # documents: dedupe + error reporting
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_hash varchar(64)",
    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS error_message varchar(500)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_documents_user_hash ON documents (user_id, content_hash)",
    "CREATE INDEX IF NOT EXISTS ix_documents_user_id ON documents (user_id)",
    # chunks: owner, structure, injection score
    "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS user_id integer REFERENCES users(id) ON DELETE CASCADE",
    "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS section varchar(300)",
    "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS injection_score double precision",
    "UPDATE document_chunks c SET user_id = d.user_id FROM documents d WHERE c.document_id = d.id AND c.user_id IS NULL",
    "CREATE INDEX IF NOT EXISTS ix_document_chunks_document_id ON document_chunks (document_id)",
    "CREATE INDEX IF NOT EXISTS ix_document_chunks_user_id ON document_chunks (user_id)",
    # full-text search column for the keyword leg of hybrid retrieval
    "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS tsv tsvector "
    "GENERATED ALWAYS AS (to_tsvector('english', coalesce(section, '') || ' ' || text_content)) STORED",
    "CREATE INDEX IF NOT EXISTS ix_document_chunks_tsv ON document_chunks USING gin (tsv)",
    # approximate nearest neighbour index (cosine)
    "CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_hnsw ON document_chunks "
    "USING hnsw (embedding vector_cosine_ops)",
    # chat
    "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS meta json",
    "CREATE INDEX IF NOT EXISTS ix_chat_sessions_user_id ON chat_sessions (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_chat_messages_session_id ON chat_messages (session_id)",
    "CREATE INDEX IF NOT EXISTS ix_auth_sessions_user_id ON auth_sessions (user_id)",
]


async def check_embedding_dimension(conn) -> None:
    res = await conn.execute(text(
        "SELECT atttypmod FROM pg_attribute WHERE attrelid = 'document_chunks'::regclass AND attname = 'embedding'"
    ))
    dim = res.scalar()
    if dim and dim > 0 and dim != settings.EMBEDDING_DIM:
        raise RuntimeError(
            f"document_chunks.embedding is vector({dim}) but EMBEDDING_DIM={settings.EMBEDDING_DIM}. "
            "Re-embed the corpus (POST /api/build-index) after migrating the column, or fix EMBEDDING_MODEL."
        )


async def run_migrations(engine: AsyncEngine) -> None:
    from app.database.base import Base
    import app.models.user  # noqa: F401  (register models)
    import app.models.document  # noqa: F401
    import app.models.chat  # noqa: F401

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    for stmt in UPGRADE_STATEMENTS:
        # Each statement in its own transaction so one failure (e.g. missing privilege) does not abort the rest.
        try:
            async with engine.begin() as conn:
                await conn.execute(text(stmt))
        except Exception as e:  # pragma: no cover - depends on DB privileges
            logger.warning("Migration statement skipped (%s): %s", type(e).__name__, stmt[:90])
    async with engine.begin() as conn:
        await check_embedding_dimension(conn)
    logger.info("Database schema verified.")
