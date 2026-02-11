"""
Multi-Agentic AI Enterprise OS — Core Configuration

Loads settings from environment variables with Pydantic Settings.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── App ──────────────────────────────────
    APP_NAME: str = "company-ai"
    APP_ENV: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str = "change-me-in-production"
    API_V1_PREFIX: str = "/api/v1"
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:8000"

    # ── Database ─────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@db:5432/company_ai"
    DATABASE_ECHO: bool = False

    # ── Redis ────────────────────────────────
    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"

    # ── LiteLLM ──────────────────────────────
    LITELLM_PROXY_URL: str = "http://litellm:4000"
    LITELLM_MASTER_KEY: str = "sk-litellm-master-key"

    # ── JWT ───────────────────────────────────
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # ── Rate Limiting ────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 60

    # ── Agent Execution ──────────────────────
    AGENT_MAX_TOOL_CALLS: int = 50
    AGENT_MAX_TOKENS: int = 100_000
    AGENT_MAX_EXECUTION_TIME: int = 600  # seconds (10 minutes)
    AGENT_LOOP_DETECTION_THRESHOLD: int = 5

    # ── Knowledge & RAG ──────────────────────
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSIONS: int = 1536
    CHUNK_SIZE: int = 500       # target tokens per chunk
    CHUNK_OVERLAP: int = 50     # token overlap between chunks
    RAG_TOP_K: int = 5          # default retrieval count

    # ── Agent Memory ─────────────────────────
    MEMORY_TTL: int = 86400     # Redis session TTL in seconds (24h)

    @property
    def allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()
