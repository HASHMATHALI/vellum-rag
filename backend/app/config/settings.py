import logging
import os
import secrets
from typing import List

from pydantic import ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Values that were committed to the repository at some point and must never be accepted in production.
KNOWN_PUBLIC_JWT_SECRETS = {
    "9a7c3d2e9b8f5a1c0d4e3f2a1b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c",
    "change_me", "changeme", "secret",
}
KNOWN_DEFAULT_PASSWORDS = {"admin123", "guest123", "password", "changeme", "admin"}


class Settings(BaseSettings):
    PROJECT_NAME: str = "Vellum RAG"
    ENVIRONMENT: str = "development"  # development | test | production
    DEBUG: bool = False
    PORT: int = 8000
    ENABLE_API_DOCS: bool = True  # forced off in production unless explicitly enabled

    # --- Auth / sessions ---
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_ISSUER: str = "vellum-rag"
    JWT_AUDIENCE: str = "vellum-rag-api"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    MFA_TOKEN_EXPIRE_MINUTES: int = 5
    COOKIE_SECURE: bool = True
    COOKIE_SAMESITE: str = "lax"  # lax | strict | none (none requires COOKIE_SECURE)
    COOKIE_DOMAIN: str = ""
    PASSWORD_MIN_LENGTH: int = 10

    # Guest mode: each anonymous visitor gets an isolated, short-lived account.
    ALLOW_GUEST: bool = True
    GUEST_TTL_HOURS: int = 24
    GUEST_MAX_DOCUMENTS: int = 5

    # Sign in with Google: OAuth 2.0 *Web* client ID(s), comma-separated. Empty = Google sign-in disabled.
    GOOGLE_CLIENT_ID: str = ""

    # Optional bootstrap admin (only created when both are set and the password is strong).
    ADMIN_EMAIL: str = ""
    ADMIN_PASSWORD: str = ""

    # --- Infrastructure ---
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/rag_db"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 10
    DB_STATEMENT_TIMEOUT_MS: int = 30000
    ENABLE_RLS: bool = False  # see backend/app/database/rls.sql
    REDIS_URL: str = ""
    CORS_ORIGINS: str = "http://localhost,http://localhost:5173,http://127.0.0.1:5173"
    TRUSTED_PROXY_HOPS: int = 0  # number of reverse proxies in front of the app (for X-Forwarded-For)

    # --- LLM ---
    GROQ_API_KEY: str = ""
    LLM_MODEL: str = "openai/gpt-oss-120b"
    LLM_FALLBACK_MODEL: str = "qwen/qwen3.8-27b"
    LLM_UTILITY_MODEL: str = "openai/gpt-oss-20b"  # query reformulation
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 1500
    LLM_TIMEOUT_SECONDS: float = 60.0
    LLM_MAX_RETRIES: int = 2
    PROMPT_GUARD_ENABLED: bool = False
    PROMPT_GUARD_MODEL: str = "meta-llama/llama-prompt-guard-2-86m"
    PROMPT_GUARD_THRESHOLD: float = 0.9

    # --- Storage ---
    UPLOAD_DIR: str = "uploads"
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    SUPABASE_STORAGE_BUCKET: str = "documents"
    MAX_UPLOAD_SIZE_MB: int = 20
    MAX_PDF_PAGES: int = 500
    MAX_EXTRACTED_CHARS: int = 5_000_000

    # --- RAG ---
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_DIM: int = 384
    EMBEDDING_BATCH_SIZE: int = 32
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 150
    RETRIEVAL_CANDIDATES: int = 20
    VECTOR_SEARCH: str = "exact"  # exact (per-tenant, recall 1.0) | hnsw (needs pgvector >= 0.8 iterative scans)
    RERANKER_ENABLED: bool = True
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    RERANK_TOP_N: int = 10  # fused candidates sent to the cross-encoder (~55 ms/pair on a laptop CPU; 10 = same quality as 15)
    TORCH_THREADS: int = 4  # intra-op threads per model call (avoid oversubscription under concurrency)
    MODEL_CONCURRENCY: int = 2  # concurrent CPU model calls per worker; extra requests queue instead of thrashing
    RERANK_MIN_SCORE: float = -5.0  # absolute floor (cross-encoder logit); see RAG_EVALUATION_REPORT.md
    RERANK_RELATIVE_MARGIN: float = 7.0  # also drop chunks scoring more than this below the best chunk
    SEMANTIC_MIN_SCORE: float = 0.25  # cosine; used when the reranker is disabled
    CONTEXT_MAX_TOKENS: int = 3000
    HISTORY_MAX_MESSAGES: int = 6

    # --- Observability ---
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = False
    LOG_FILE: str = "app.log"
    OTEL_ENABLED: bool = False
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:6006/v1/traces"  # Phoenix default
    OTEL_SERVICE_NAME: str = "vellum-rag-backend"
    TRACE_INCLUDE_CONTENT: bool = False  # never export document text / prompts unless explicitly enabled

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("COOKIE_SAMESITE")
    @classmethod
    def _samesite(cls, v: str) -> str:
        v = v.lower()
        if v not in {"lax", "strict", "none"}:
            raise ValueError("COOKIE_SAMESITE must be lax, strict or none")
        return v

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip().rstrip("/") for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @model_validator(mode="after")
    def _secure_defaults(self):
        if self.is_production:
            if not self.JWT_SECRET_KEY or self.JWT_SECRET_KEY in KNOWN_PUBLIC_JWT_SECRETS or len(self.JWT_SECRET_KEY) < 32:
                raise ValueError(
                    "JWT_SECRET_KEY must be set to a private random value of at least 32 characters in production "
                    "(generate one with: python -c \"import secrets; print(secrets.token_hex(32))\")"
                )
            if self.ADMIN_PASSWORD and (self.ADMIN_PASSWORD in KNOWN_DEFAULT_PASSWORDS or len(self.ADMIN_PASSWORD) < 12):
                raise ValueError("ADMIN_PASSWORD is a known default or shorter than 12 characters")
            if "*" in self.cors_origins:
                raise ValueError("CORS_ORIGINS may not contain '*' in production")
            if self.COOKIE_SAMESITE == "none" and not self.COOKIE_SECURE:
                raise ValueError("COOKIE_SAMESITE=none requires COOKIE_SECURE=true")
            self.DEBUG = False
        else:
            if not self.JWT_SECRET_KEY or self.JWT_SECRET_KEY in KNOWN_PUBLIC_JWT_SECRETS:
                # Per-process random secret: sessions do not survive restarts, which is acceptable outside production.
                self.JWT_SECRET_KEY = secrets.token_hex(32)
                logger.warning("JWT_SECRET_KEY missing or publicly known; generated an ephemeral secret (non-production only).")
        return self


def _load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as e:
        # pydantic includes the offending input values (which may contain DATABASE_URL credentials or keys) in its
        # message; report only field names and reasons.
        reasons = "; ".join(f"{'.'.join(map(str, err.get('loc', ()))) or 'settings'}: {err.get('msg')}" for err in e.errors())
        raise SystemExit(f"Invalid configuration: {reasons}") from None


settings = _load_settings()
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
