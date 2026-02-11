"""Agent schemas — CRUD request/response."""

from pydantic import BaseModel


class AgentCreate(BaseModel):
    name: str
    department: str
    tier: str = "standard"
    description: str | None = None
    system_prompt: str | None = None
    tools_config: dict | None = None
    paired_user_id: str | None = None


class AgentUpdate(BaseModel):
    name: str | None = None
    tier: str | None = None
    status: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    tools_config: dict | None = None
    paired_user_id: str | None = None


class AgentResponse(BaseModel):
    id: str
    name: str
    department: str
    tier: str
    status: str
    description: str | None = None
    paired_user_id: str | None = None

    model_config = {"from_attributes": True}
