"""
Multi-Agentic AI Enterprise Operating System

FastAPI application entry point.
63 agents | 7 departments | 31 humans
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.v1.health import router as health_router
from app.api.v1.router import router as v1_router
from app.core.config import get_settings
from app.core.deps import engine
from app.models import Base

settings = get_settings()

# Rate limiter
limiter = Limiter(key_func=get_remote_address, default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup: create tables if they don't exist (dev only)
    if settings.APP_ENV == "development":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        # Auto-seed admin user + agents if empty
        from app.seed import seed_database
        await seed_database()
        print(f"🚀 {settings.APP_NAME} started in {settings.APP_ENV} mode")
        print(f"📊 Database connected: {settings.DATABASE_URL.split('@')[-1]}")

    # Load integration credentials from DB into CredentialVault
    from app.core.deps import async_session
    from app.services.orchestration.credential_vault import CredentialVault
    async with async_session() as db:
        await CredentialVault.load(db)
    print("🔑 CredentialVault loaded (env + DB)")

    # Register shared tools (email, calendar, drive, whatsapp, search)
    from app.agents.tools.shared_tools import register_shared_tools
    register_shared_tools()
    print("🔧 Shared tools registered (send_email, create_meeting, etc.)")

    # Start Telegram long-polling worker (no webhook URL needed)
    from app.services.channels.telegram_poller import telegram_poller
    await telegram_poller.start()
    if telegram_poller.is_running:
        print("📡 Telegram poller started (long-polling mode)")

    # Start Email IMAP poller (if configured)
    from app.services.channels.email_poller import email_poller
    await email_poller.start()
    if email_poller.is_running:
        print("📧 Email poller started (IMAP mode)")

    yield
    # Shutdown
    await telegram_poller.stop()
    await email_poller.stop()
    await engine.dispose()
    print("👋 Application shutdown complete")


# ── FastAPI App ──────────────────────────────
app = FastAPI(
    title="Multi-Agentic AI Enterprise OS",
    description="63 agents across 7 departments, supervised by 31 humans",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── Middleware ───────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.limiter = limiter

# ── Routers ──────────────────────────────────
app.include_router(health_router)
app.include_router(v1_router, prefix=settings.API_V1_PREFIX)


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint — system info."""
    return {
        "system": "Multi-Agentic AI Enterprise OS",
        "version": "0.1.0",
        "agents": 63,
        "departments": 7,
        "humans": 31,
        "docs": "/docs",
        "health": "/health",
    }
