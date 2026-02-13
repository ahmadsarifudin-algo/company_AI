"""V1 API Router — aggregates all v1 endpoints."""

from fastapi import APIRouter

from app.api.v1.admin import router as admin_router
from app.api.v1.agents import router as agents_router
from app.api.v1.auth import router as auth_router
from app.api.v1.execution import router as execution_router
from app.api.v1.gateway import router as gateway_router
from app.api.v1.integrations import router as integrations_router
from app.api.v1.knowledge import knowledge_router
from app.api.v1.souls import router as souls_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.workflows import router as workflows_router

router = APIRouter()

router.include_router(admin_router)
router.include_router(auth_router)
router.include_router(agents_router)
router.include_router(tasks_router)
router.include_router(execution_router)
router.include_router(knowledge_router)
router.include_router(workflows_router)
router.include_router(gateway_router)
router.include_router(integrations_router)
router.include_router(souls_router)

