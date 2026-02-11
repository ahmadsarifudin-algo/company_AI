"""Tasks router — Task submission and status tracking."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession
from app.models.task import Task
from app.schemas.task import TaskCreate, TaskResponse

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
async def create_task(data: TaskCreate, db: DbSession, user: CurrentUser):
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
    user: CurrentUser,
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
