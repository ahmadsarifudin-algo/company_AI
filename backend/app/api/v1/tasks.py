"""Tasks router — Task submission and status tracking."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession, require_permission
from app.models.task import Task
from app.schemas.task import TaskCreate, TaskResponse
from app.services.agent_executor import AgentExecutorService

PermTaskCreate = Annotated["User", Depends(require_permission("tasks.create"))]
PermTaskUpdate = Annotated["User", Depends(require_permission("tasks.update"))]

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.get("", response_model=list[TaskResponse])
async def list_tasks(
    db: DbSession,
    department: str | None = None,
    task_status: str | None = None,
    limit: int = 50,
):
    """List tasks with optional filters."""
    query = select(Task)
    if department:
        query = query.where(Task.department == department)
    if task_status:
        query = query.where(Task.status == task_status)
    query = query.order_by(Task.created_at.desc()).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, db: DbSession):
    """Get a specific task by ID."""
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(data: TaskCreate, db: DbSession, user: PermTaskCreate):
    """Submit a new task (requires auth)."""
    task = Task(**data.model_dump(), submitted_by=user.id)
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return task


@router.patch("/{task_id}/status")
async def update_task_status(
    task_id: str,
    new_status: str,
    db: DbSession,
    user: PermTaskUpdate,
):
    """Update a task's status (requires auth)."""
    valid_statuses = {"pending", "running", "waiting_approval", "completed", "failed"}
    if new_status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {valid_statuses}",
        )

    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.status = new_status
    await db.flush()
    return {"id": task.id, "status": task.status, "message": f"Status updated to {new_status}"}


@router.post("/{task_id}/execute")
async def execute_task(
    task_id: str,
    db: DbSession,
    user: CurrentUser,
):
    """Execute a pending task through the agent pipeline.

    Triggers AgentExecutorService which:
    1. Loads the task and assigned agent from DB
    2. Builds a LangGraph execution graph
    3. Injects RAG context from knowledge base
    4. Runs the agent with tools
    5. Updates task status and result_json
    6. Logs audit entry
    """
    # Verify task exists and is executable
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status not in ("pending", "failed"):
        raise HTTPException(
            status_code=400,
            detail=f"Task is already '{task.status}'. Only pending or failed tasks can be executed.",
        )

    # Execute through the agent pipeline
    try:
        executor = AgentExecutorService(db)
        exec_result = await executor.execute_task(
            task_id=task_id,
            agent_id=task.assigned_agent_id,
            input_text=task.description or task.title,
        )
    except Exception as e:
        # Pipeline errors (missing API keys, LLM failures, etc.)
        exec_result = {
            "task_id": task_id,
            "status": "failed",
            "error": str(e),
        }

    return exec_result


