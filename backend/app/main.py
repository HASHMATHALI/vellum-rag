import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config.logging_config import configure_logging
from app.config.settings import KNOWN_DEFAULT_PASSWORDS, settings

configure_logging()
logger = logging.getLogger(__name__)

from app.api import admin, auth, chat, documents  # noqa: E402
from app.middleware.security import SecurityHeadersMiddleware  # noqa: E402
from app.observability.tracing import setup_tracing, shutdown_tracing  # noqa: E402


async def bootstrap_admin() -> None:
    """Create the bootstrap admin only when explicitly configured with a strong password."""
    from sqlalchemy import func, select
    from app.auth.jwt import get_password_hash, verify_password
    from app.database.connection import system_session
    from app.models.user import User

    async with system_session() as db:
        if settings.ADMIN_EMAIL and settings.ADMIN_PASSWORD:
            if settings.ADMIN_PASSWORD.lower() in KNOWN_DEFAULT_PASSWORDS or len(settings.ADMIN_PASSWORD) < 12:
                logger.error("ADMIN_PASSWORD is weak or a known default; bootstrap admin NOT created.")
            else:
                email = settings.ADMIN_EMAIL.strip().lower()
                user = (await db.execute(select(User).where(func.lower(User.email) == email))).scalars().first()
                if user is None:
                    db.add(User(email=email, hashed_password=get_password_hash(settings.ADMIN_PASSWORD),
                                full_name="Administrator", role="admin", is_active=True))
                    logger.info("Bootstrap admin account created.")
                elif user.role != "admin":
                    logger.warning("ADMIN_EMAIL exists but is not an admin; not promoting automatically.")
        # Warn loudly about accounts still using the old seeded defaults (cannot log in in production).
        legacy = (await db.execute(select(User).where(User.email.in_(["admin@vellum.ai", "guest@vellum.ai"])))).scalars().all()
        for u in legacy:
            if any(verify_password(p, u.hashed_password) for p in ("admin123", "guest123")):
                if u.email == "guest@vellum.ai" and u.is_active:
                    u.is_active = False  # shared guest account: disabled (guests are now isolated per visitor)
                    logger.critical("Disabled legacy shared guest account (id=%s).", u.id)
                else:
                    logger.critical("User id=%s still has a default password. Rotate it immediately.", u.id)
        await db.commit()


async def retention_loop() -> None:
    from app.database.connection import system_session
    from app.services.auth_service import AuthService
    while True:
        try:
            async with system_session() as db:
                n = await AuthService.purge_expired_guests(db)
                if n:
                    logger.info("Retention: purged %d expired guest accounts.", n)
        except Exception as e:
            logger.error("Retention job failed: %s", type(e).__name__)
        await asyncio.sleep(3600)


async def warm_models() -> None:
    """Load embedding/reranker models in the background so the first user request does not pay ~20s of cold start."""
    from starlette.concurrency import run_in_threadpool
    from app.embeddings.embedder import embedder
    from app.retrieval.reranker import reranker
    try:
        await run_in_threadpool(embedder.get_embeddings, ["warm up"])
        if settings.RERANKER_ENABLED:
            await run_in_threadpool(reranker.score, "warm up", ["warm up"])
        logger.info("Models warmed up.")
    except Exception as e:
        logger.error("Model warm-up failed: %s", type(e).__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.database.connection import engine
    from app.database.migrations import run_migrations
    setup_tracing()
    await run_migrations(engine)
    await bootstrap_admin()
    task = asyncio.create_task(retention_loop()) if settings.ENVIRONMENT != "test" else None
    warm = asyncio.create_task(warm_models()) if settings.ENVIRONMENT != "test" else None
    yield
    if warm and not warm.done():
        warm.cancel()
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    shutdown_tracing()
    await engine.dispose()


docs_enabled = settings.ENABLE_API_DOCS and not settings.is_production
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Vellum RAG: document question answering with grounded, cited answers.",
    version="2.0.0",
    docs_url="/docs" if docs_enabled else None,
    redoc_url="/redoc" if docs_enabled else None,
    openapi_url="/openapi.json" if docs_enabled else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
    max_age=600,
)
app.add_middleware(SecurityHeadersMiddleware)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    # Do not echo submitted values (could contain passwords) back to the client.
    errors = [{"loc": e.get("loc"), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        raise exc
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(documents.router)
api_router.include_router(chat.router)
api_router.include_router(admin.router)
app.include_router(api_router)


@app.get("/")
async def root():
    return {"name": settings.PROJECT_NAME, "status": "online"}
