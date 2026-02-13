"""Task schemas — submission and status."""

from datetime import datetime

from pydantic import BaseModel


class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    department: str
    priority: str = "P2"
    plan_json: dict | None = None
    assigned_agent_id: str | None = None


class TaskResponse(BaseModel):
    id: str
    title: str
    description: str | None = None
    department: str
    status: str
    priority: str
    assigned_agent_id: str | None = None
    submitted_by: str | None = None
    channel: str | None = None
    sender_name: str | None = None
    sender_identifier: str | None = None
    agent_response: str | None = None
    trace_id: str | None = None
    original_message: str | None = None
    result_json: dict | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
