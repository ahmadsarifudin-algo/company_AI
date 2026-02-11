"""Execution schemas — Request/response for agent execution and chat."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ExecuteRequest(BaseModel):
    """Request to execute a task through the agent pipeline."""

    task_id: str
    agent_id: str | None = None
    input_text: str | None = None
    mode: str = "sync"  # "sync" or "async"


class ChatRequest(BaseModel):
    """Request to chat with a specific agent."""

    agent_id: str
    message: str
    thread_id: str | None = None


class ExecutionResponse(BaseModel):
    """Response from a task execution."""

    task_id: str
    agent_id: str | None = None
    agent_name: str | None = None
    status: str
    result: dict[str, Any] | None = None
    token_usage: int = 0
    tool_calls: int = 0
    artifacts: list[str] = []
    errors: list[str] = []
    execution_time_ms: float | None = None


class ChatResponse(BaseModel):
    """Response from a chat interaction."""

    agent_id: str
    agent_name: str
    thread_id: str
    response: str
    status: str


class AuditLogResponse(BaseModel):
    """Response for audit log entries."""

    id: str
    department: str
    agent_name: str
    action_type: str
    details: str | None = None
    resource_scope: str | None = None
    cost_estimate: float | None = None
    execution_time_ms: float | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CostSummaryResponse(BaseModel):
    """Response for cost summary."""

    total_entries: int
    total_cost_usd: float
    by_action_type: dict[str, Any]
