"""
Execution Router — Agent execution and chat endpoints.

Provides endpoints for:
- Task execution through the agent pipeline
- Chat interactions with specific agents
- Execution history and audit trail
- Cost tracking summaries
"""

from fastapi import APIRouter, HTTPException

from app.core.deps import CurrentUser, DbSession
from app.schemas.execution import (
    AuditLogResponse,
    ChatRequest,
    ChatResponse,
    CostSummaryResponse,
    ExecuteRequest,
    ExecutionResponse,
)
from app.services.agent_executor import AgentExecutorService
from app.services.audit_service import AuditService

router = APIRouter(prefix="/execution", tags=["Execution"])


@router.post("/execute", response_model=ExecutionResponse)
async def execute_task(
    request: ExecuteRequest,
    db: DbSession,
    user: CurrentUser,
):
    """Execute a task through the agent pipeline.

    Creates a LangGraph execution graph, routes through supervisors,
    and runs the assigned agent. Results are saved to the task record.
    """
    executor = AgentExecutorService(db)

    if request.mode == "async":
        # For async mode, we'd dispatch via Celery.
        # For now, we run synchronously and return the result.
        pass

    result = await executor.execute_task(
        task_id=request.task_id,
        agent_id=request.agent_id,
        input_text=request.input_text,
    )

    if "error" in result and result.get("status") == "failed":
        raise HTTPException(status_code=400, detail=result["error"])

    return result


@router.post("/chat", response_model=ChatResponse)
async def chat_with_agent(
    request: ChatRequest,
    db: DbSession,
    user: CurrentUser,
):
    """Chat with a specific agent.

    Sends a message to the agent and returns the response.
    Supports conversation continuity via thread_id.
    """
    executor = AgentExecutorService(db)
    result = await executor.chat_with_agent(
        agent_id=request.agent_id,
        message=request.message,
        thread_id=request.thread_id,
    )

    if "error" in result and result.get("status") == "failed":
        raise HTTPException(status_code=400, detail=result["error"])

    return result


@router.get("/audit/{agent_name}", response_model=list[AuditLogResponse])
async def get_agent_audit(
    agent_name: str,
    db: DbSession,
    user: CurrentUser,
    limit: int = 50,
    action_type: str | None = None,
):
    """Get audit trail for a specific agent."""
    audit = AuditService(db)
    entries = await audit.get_agent_history(
        agent_name=agent_name,
        limit=limit,
        action_type=action_type,
    )
    return entries


@router.get("/audit/department/{department}", response_model=list[AuditLogResponse])
async def get_department_audit(
    department: str,
    db: DbSession,
    user: CurrentUser,
    limit: int = 100,
):
    """Get audit trail for an entire department."""
    audit = AuditService(db)
    entries = await audit.get_department_history(
        department=department,
        limit=limit,
    )
    return entries


@router.get("/costs", response_model=CostSummaryResponse)
async def get_cost_summary(
    db: DbSession,
    user: CurrentUser,
    department: str | None = None,
):
    """Get cost summary with optional department filter."""
    audit = AuditService(db)
    return await audit.get_cost_summary(department=department)
