"""V1 API Router — aggregates all v1 endpoints."""

from fastapi import APIRouter

from app.api.v1.agents import router as agents_router
from app.api.v1.auth import router as auth_router
from app.api.v1.tasks import router as tasks_router

router = APIRouter()

router.include_router(auth_router)
router.include_router(agents_router)
router.include_router(tasks_router)
