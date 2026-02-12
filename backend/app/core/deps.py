"""
Multi-Agentic AI Enterprise OS — Dependency Injection

Provides database sessions, current authenticated user, and shared dependencies.
Includes the Single Chokepoint layer: LLMClient, ToolBroker, DataAccessLayer.
"""

from typing import Annotated, AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.security import decode_access_token

settings = get_settings()

# ── Database Engine ──────────────────────────
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DATABASE_ECHO,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ── Sync Engine (for telemetry DB sink) ──────
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

_sync_url = settings.DATABASE_URL.replace("+asyncpg", "").replace("postgresql+aiosqlite", "sqlite")
if _sync_url.startswith("postgresql+asyncpg"):
    _sync_url = _sync_url.replace("postgresql+asyncpg", "postgresql")
elif "asyncpg" in _sync_url:
    _sync_url = _sync_url.replace("asyncpg://", "postgresql://")

# Convert async URL to sync: postgresql+asyncpg:// → postgresql://
_sync_url = _sync_url.replace("postgresql+asyncpg", "postgresql").replace("+asyncpg", "")

sync_engine = create_engine(
    _sync_url,
    pool_size=5,
    max_overflow=5,
    pool_pre_ping=True,
)

SyncSession = sessionmaker(sync_engine, class_=Session, expire_on_commit=False)


def get_sync_session() -> Session:
    """Return a synchronous DB session for telemetry DB sink."""
    return SyncSession()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Auth Dependencies ────────────────────────
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/login")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Extract and validate the current user from JWT token."""
    from app.models.user import User

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    user_id: str = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    return user


# ── Single Chokepoint Dependencies ───────────

def get_llm_client():
    """Get the singleton LLMClient instance."""
    from app.core.llm_client import get_llm_client as _get
    return _get()


def get_tool_broker():
    """Get the singleton ToolBroker instance."""
    from app.core.tool_broker import get_tool_broker as _get
    return _get()


def get_dal(db: AsyncSession = Depends(get_db)):
    """Get a DataAccessLayer backed by the current DB session."""
    from app.core.data_access import DataAccessLayer
    return DataAccessLayer(db)


# ── Type Aliases ─────────────────────────────
DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated["User", Depends(get_current_user)]
LLMDep = Annotated["LLMClient", Depends(get_llm_client)]
BrokerDep = Annotated["ToolBroker", Depends(get_tool_broker)]
DALDep = Annotated["DataAccessLayer", Depends(get_dal)]


# ── Role-Based Access Control ────────────────
ROLE_HIERARCHY = {"admin": 4, "manager": 3, "lead": 2, "contributor": 1}


def require_role(min_role: str):
    """Factory: returns a FastAPI dependency that enforces a minimum role.

    Usage:
        @router.get("/admin-only", dependencies=[Depends(require_role("admin"))])
        async def admin_only(user: CurrentUser): ...
    """
    min_level = ROLE_HIERARCHY.get(min_role, 0)

    async def _check(
        user=Depends(get_current_user),
    ):
        user_level = ROLE_HIERARCHY.get(user.role, 0)
        if user_level < min_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {min_role} role or higher (your role: {user.role})",
            )
        return user

    return _check


# Convenience aliases
AdminOnly = Annotated["User", Depends(require_role("admin"))]
ManagerUp = Annotated["User", Depends(require_role("manager"))]
LeadUp = Annotated["User", Depends(require_role("lead"))]


# ── Granular Permission System ───────────────
# Maps permission string → minimum role required
PERMISSION_MAP: dict[str, str] = {
    # Dashboard
    "dashboard.read":           "contributor",
    # Traces
    "traces.read":              "contributor",
    "traces.export":            "admin",
    # Approvals
    "approvals.read":           "lead",
    "approvals.decide":         "lead",
    # Policies
    "policies.read":            "contributor",
    # Agents
    "agents.read":              "contributor",
    "agents.prompt.read":       "contributor",
    "agents.prompt.edit":       "manager",
    "agents.prompt.rollback":   "manager",
    "agents.test":              "lead",
    "agents.sync":              "admin",
    "agents.edit_privileged":   "admin",
    # LLM Settings
    "settings.llm.read":        "manager",
    "settings.llm.edit":        "admin",
    # Users
    "users.read":               "manager",
    "users.create":             "admin",
    "users.delete":             "admin",
    # Channels / Integrations
    "channels.read":            "contributor",
    "channels.configure":       "admin",
    # Knowledge
    "knowledge.read":           "contributor",
    "knowledge.ingest":         "lead",
    "knowledge.delete":         "manager",
    # Tasks
    "tasks.read":               "contributor",
    "tasks.create":             "contributor",
    "tasks.update":             "lead",
    # Souls
    "souls.read":               "contributor",
    "souls.create":             "contributor",
    "souls.delete":             "contributor",
    # Workflows
    "workflows.execute":        "lead",
    "workflows.approve":        "lead",
}


def has_permission(user, permission: str) -> bool:
    """Check if user role meets minimum for permission.

    Returns False for unknown permissions (deny by default).
    """
    min_role = PERMISSION_MAP.get(permission)
    if min_role is None:
        return False
    min_level = ROLE_HIERARCHY.get(min_role, 99)
    user_level = ROLE_HIERARCHY.get(user.role, 0)
    return user_level >= min_level


def require_permission(permission: str):
    """FastAPI dependency factory for permission-based access control.

    Usage:
        @router.get("/agents/{id}/prompt")
        async def get_prompt(user: PermCheck("agents.prompt.read")): ...
    or:
        @router.get("/agents/{id}/prompt",
                     dependencies=[Depends(require_permission("agents.prompt.read"))])
    """
    async def _check(user=Depends(get_current_user)):
        if not has_permission(user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission}' denied for role '{user.role}'",
            )
        return user
    return _check
