"""Agents router — Agent registry CRUD."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.core.deps import DbSession, require_permission
from app.models.agent import Agent
from app.schemas.agent import AgentCreate, AgentResponse, AgentUpdate

PermAgentsEdit = Annotated["User", Depends(require_permission("agents.prompt.edit"))]

router = APIRouter(prefix="/agents", tags=["Agents"])


@router.get("", response_model=list[AgentResponse])
async def list_agents(db: DbSession, department: str | None = None):
    """List all agents, optionally filtered by department."""
    query = select(Agent)
    if department:
        query = query.where(Agent.department == department)
    query = query.order_by(Agent.department, Agent.name)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str, db: DbSession):
    """Get a specific agent by ID."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(data: AgentCreate, db: DbSession, user: PermAgentsEdit):
    """Register a new agent (requires auth)."""
    agent = Agent(**data.model_dump())
    db.add(agent)
    await db.flush()
    await db.refresh(agent)
    return agent


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(agent_id: str, data: AgentUpdate, db: DbSession, user: PermAgentsEdit):
    """Update an agent's configuration (requires auth)."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(agent, key, value)

    await db.flush()
    await db.refresh(agent)
    return agent


@router.get("/stats/summary")
async def agent_stats(db: DbSession):
    """Get agent statistics by department and tier."""
    result = await db.execute(select(Agent))
    agents = result.scalars().all()

    by_department = {}
    by_tier = {}
    for agent in agents:
        by_department[agent.department] = by_department.get(agent.department, 0) + 1
        by_tier[agent.tier] = by_tier.get(agent.tier, 0) + 1

    return {
        "total": len(agents),
        "by_department": by_department,
        "by_tier": by_tier,
    }
