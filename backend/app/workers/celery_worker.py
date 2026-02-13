"""
Celery Worker — Auto-execute pending tasks.

Run with:
    celery -A app.workers.celery_worker worker --beat --loglevel=info

This worker:
1. Polls DB every 60s for pending tasks with assigned agents
2. Executes them via AgentExecutorService
3. Updates task status and result
"""

import asyncio
import os

from celery import Celery
from celery.schedules import crontab  # noqa: F401

# ── Celery app ──────────────────────────────────────────────
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

app = Celery(
    "company_ai_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Jakarta",
    enable_utc=True,
    beat_schedule={
        "execute-pending-tasks": {
            "task": "app.workers.celery_worker.execute_pending_tasks",
            "schedule": 60.0,  # every 60 seconds
        },
    },
)


# ── Helper: run async code from sync Celery task ────────────
def _run_async(coro):
    """Run an async coroutine from a synchronous Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Periodic task ───────────────────────────────────────────
@app.task(name="app.workers.celery_worker.execute_pending_tasks")
def execute_pending_tasks():
    """Find and execute all pending tasks that have assigned agents."""
    _run_async(_execute_pending_tasks_async())


async def _execute_pending_tasks_async():
    """Async implementation of the periodic task scanner."""
    import structlog
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.database import async_session_factory
    from app.models.task import Task
    from app.services.agent_executor import AgentExecutorService

    logger = structlog.get_logger()
    logger.info("celery_scanning_pending_tasks")

    async with async_session_factory() as session:  # type: AsyncSession
        # Find pending tasks with an agent assigned
        result = await session.execute(
            select(Task)
            .where(
                Task.status == "pending",
                Task.assigned_agent_id.isnot(None),
            )
            .limit(10)  # batch size
        )
        tasks = result.scalars().all()

        if not tasks:
            logger.info("celery_no_pending_tasks")
            return

        logger.info("celery_found_pending", count=len(tasks))

        for task in tasks:
            try:
                executor = AgentExecutorService(session)
                exec_result = await executor.execute_task(
                    task_id=str(task.id),
                )
                status = exec_result.get("status", "unknown")
                logger.info(
                    "celery_task_executed",
                    task_id=str(task.id),
                    status=status,
                )
            except Exception as e:
                logger.error(
                    "celery_task_failed",
                    task_id=str(task.id),
                    error=str(e),
                )

        await session.commit()


# ── One-off task execution ──────────────────────────────────
@app.task(name="app.workers.celery_worker.execute_single_task")
def execute_single_task(task_id: str, agent_id: str | None = None):
    """Execute a single task by ID (dispatched from API)."""
    return _run_async(_execute_single_async(task_id, agent_id))


async def _execute_single_async(task_id: str, agent_id: str | None = None):
    """Async implementation of single task execution."""
    import structlog

    from app.core.database import async_session_factory
    from app.services.agent_executor import AgentExecutorService

    logger = structlog.get_logger()

    async with async_session_factory() as session:
        executor = AgentExecutorService(session)
        result = await executor.execute_task(
            task_id=task_id,
            agent_id=agent_id,
        )
        await session.commit()
        logger.info("celery_single_task_done", task_id=task_id, status=result.get("status"))
        return result
