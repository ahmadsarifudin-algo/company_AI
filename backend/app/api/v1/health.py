"""Health check router — System status endpoint."""

from fastapi import APIRouter
from redis.asyncio import from_url as redis_from_url
from sqlalchemy import text

from app.core.config import get_settings
from app.core.deps import DbSession

router = APIRouter(tags=["Health"])
settings = get_settings()


@router.get("/health")
async def health_check(db: DbSession):
    """Check system health: database and Redis connectivity."""
    health = {
        "status": "healthy",
        "database": "disconnected",
        "redis": "disconnected",
    }

    # Check database
    try:
        await db.execute(text("SELECT 1"))
        health["database"] = "connected"
    except Exception as e:
        health["status"] = "degraded"
        health["database"] = f"error: {str(e)[:100]}"

    # Check Redis
    try:
        redis = redis_from_url(settings.REDIS_URL)
        await redis.ping()
        health["redis"] = "connected"
        await redis.aclose()
    except Exception as e:
        health["status"] = "degraded"
        health["redis"] = f"error: {str(e)[:100]}"

    return health
