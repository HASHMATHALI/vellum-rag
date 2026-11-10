import os
import logging
import secrets
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    PROJECT_NAME: str = "RAG Semantic Search Platform"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    
    # Auth
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    
    # Comma-separated list of allowed browser origins ("*" allows any)
    CORS_ORIGINS: str = "*"

    # DB
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres_password_change_me@localhost:5432/rag_db"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Groq API
    GROQ_API_KEY: str = ""
    
    # Custom Admin Credentials for Deployment
    ADMIN_EMAIL: str = "admin@vellum.ai"
    ADMIN_PASSWORD: str = ""
    
    # Storage
    UPLOAD_DIR: str = "uploads"
    VECTOR_STORE_DIR: str = "vector_store"
    
    # Supabase (Optional for stateless deployment)
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    SUPABASE_STORAGE_BUCKET: str = "documents"
    
    # RAG Settings
    CHUNK_SIZE: int = 1500
    CHUNK_OVERLAP: int = 200
    MAX_UPLOAD_SIZE_MB: int = 20

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

# Create folders if they don't exist
settings = Settings()

# Secrets that were once published in this repository must never be trusted.
_KNOWN_LEAKED_SECRETS = {
    "9a7c3d2e9b8f5a1c0d4e3f2a1b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c",
}
if not settings.JWT_SECRET_KEY or settings.JWT_SECRET_KEY in _KNOWN_LEAKED_SECRETS or len(settings.JWT_SECRET_KEY) < 32:
    # Fall back to a random per-process key: the API keeps working, but sessions end on
    # restart and multiple workers will not share tokens. Set JWT_SECRET_KEY to fix that.
    logging.getLogger(__name__).warning(
        "JWT_SECRET_KEY is missing, too short, or a publicly known value. "
        "Using a random ephemeral key. Set JWT_SECRET_KEY (openssl rand -hex 32)."
    )
    settings.JWT_SECRET_KEY = secrets.token_hex(32)

os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
