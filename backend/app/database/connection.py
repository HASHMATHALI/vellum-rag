from typing import AsyncGenerator, Optional

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from app.config.settings import settings

_connect_args = {}
if settings.DATABASE_URL.startswith("postgresql+asyncpg"):
    _connect_args = {
        "server_settings": {"statement_timeout": str(settings.DB_STATEMENT_TIMEOUT_MS), "application_name": "vellum-rag"},
        "timeout": 10,
        # Supabase's transaction pooler (pgbouncer) does not support prepared statement caching.
        "statement_cache_size": 0 if "pooler.supabase.com" in settings.DATABASE_URL else 100,
    }

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_recycle=1800,
    pool_timeout=15,
    connect_args=_connect_args,
)

async_session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


# --- Row-level security context -------------------------------------------------------------
# When ENABLE_RLS is on, every transaction carries transaction-local settings that the policies in
# database/rls.sql check. Without a context, the policies return no rows (fail closed).

def _set_context_sql(sync_session: Session, connection) -> None:
    info = sync_session.info
    if not settings.ENABLE_RLS or "rls_user_id" not in info:
        return
    connection.execute(
        text("SELECT set_config('app.user_id', :uid, true), set_config('app.is_admin', :adm, true), "
             "set_config('app.is_system', :sys, true)"),
        {"uid": str(info.get("rls_user_id") or ""), "adm": "on" if info.get("rls_admin") else "off",
         "sys": "on" if info.get("rls_system") else "off"},
    )


@event.listens_for(Session, "after_begin")
def _after_begin(session, transaction, connection):  # pragma: no cover - exercised in RLS tests
    _set_context_sql(session, connection)


async def set_rls_context(db: AsyncSession, user_id: Optional[int], is_admin: bool = False, system: bool = False) -> None:
    """Attach the authorisation context to this DB session and apply it to the open transaction."""
    db.info["rls_user_id"] = user_id
    db.info["rls_admin"] = is_admin
    db.info["rls_system"] = system
    if settings.ENABLE_RLS and db.in_transaction():
        await db.execute(
            text("SELECT set_config('app.user_id', :uid, true), set_config('app.is_admin', :adm, true), "
                 "set_config('app.is_system', :sys, true)"),
            {"uid": str(user_id or ""), "adm": "on" if is_admin else "off", "sys": "on" if system else "off"},
        )


def system_session() -> AsyncSession:
    """Session for trusted background work (ingestion, retention). Marked so RLS policies allow it."""
    s = async_session()
    s.info.update({"rls_user_id": None, "rls_admin": False, "rls_system": True})
    return s


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        # Authentication lookups happen before a user is known; they only touch the users/auth_sessions tables,
        # which are not under RLS.
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
