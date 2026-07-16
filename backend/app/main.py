import logging
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from app.config.settings import settings
from app.api import auth, documents, chat, admin

# Setup logger configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("app.log")
    ]
)
logger = logging.getLogger(__name__)

# Initialize FastAPI App
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Production-ready AI-powered Semantic Search and RAG QA Platform APIs.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS Policy configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict to frontend domain
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Assemble API routes
api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(documents.router)
api_router.include_router(chat.router)
api_router.include_router(admin.router)

app.include_router(api_router)

@app.on_event("startup")
async def on_startup():
    """Initializes database tables on container launch."""
    logger.info("Initializing database schemas...")
    from app.database.base import Base
    from app.database.connection import engine
    # Import models to ensure they register on Base.metadata
    from app.models.user import User
    from app.models.document import Document, DocumentChunk
    from app.models.chat import ChatSession, ChatMessage
    
    try:
        async with engine.begin() as conn:
            from sqlalchemy import text
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database schemas verified/created successfully.")
        
        # Seed default users
        from app.database.connection import async_session
        from app.auth.jwt import get_password_hash
        from sqlalchemy.future import select
        async with async_session() as db:
            # Check guest
            result = await db.execute(select(User).where(User.email == "guest@vellum.ai"))
            guest = result.scalars().first()
            if guest is None:
                guest = User(
                    email="guest@vellum.ai",
                    hashed_password=get_password_hash("guest123"),
                    full_name="Guest User",
                    role="user",
                    is_active=True
                )
                db.add(guest)
                
            # Check admin
            result = await db.execute(select(User).where(User.email == settings.ADMIN_EMAIL))
            admin_user = result.scalars().first()
            if admin_user is None:
                admin_user = User(
                    email=settings.ADMIN_EMAIL,
                    hashed_password=get_password_hash(settings.ADMIN_PASSWORD),
                    full_name="Vellum Admin",
                    role="admin",
                    is_active=True
                )
                db.add(admin_user)
                
            await db.commit()
        logger.info("Default seed users verified/created successfully.")
    except Exception as e:
        logger.critical(f"Failed to initialize database tables: {e}", exc_info=True)

@app.get("/")
async def root():
    return {
        "message": f"Welcome to the {settings.PROJECT_NAME} API. Access Swagger docs at /docs",
        "status": "online"
    }
