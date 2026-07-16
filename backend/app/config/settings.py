import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    PROJECT_NAME: str = "RAG Semantic Search Platform"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    
    # Auth
    JWT_SECRET_KEY: str = "9a7c3d2e9b8f5a1c0d4e3f2a1b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    
    # DB
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres_password_change_me@localhost:5432/rag_db"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Groq API
    GROQ_API_KEY: str = ""
    
    # Custom Admin Credentials for Deployment
    ADMIN_EMAIL: str = "admin@vellum.ai"
    ADMIN_PASSWORD: str = "admin123"
    
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
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.VECTOR_STORE_DIR, exist_ok=True)
