"""
Admin Dashboard API — 9 endpoints for governance observability + agent config.

All queries use trace_index (fast) except drilldown and policies (audit_events).
"""

from datetime import datetime, timezone, timedelta
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select, text, case, literal_column
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_permission
from app.models.agent import Agent
from app.models.audit import AuditEvent
from app.models.prompt_history import PromptHistory
from app.models.trace_index import TraceIndex

# ── Granular permission aliases ──────────────
PermDashboardRead = Annotated["User", Depends(require_permission("dashboard.read"))]
PermTracesRead = Annotated["User", Depends(require_permission("traces.read"))]
PermApprovalsRead = Annotated["User", Depends(require_permission("approvals.read"))]
PermApprovalsDecide = Annotated["User", Depends(require_permission("approvals.decide"))]
PermPoliciesRead = Annotated["User", Depends(require_permission("policies.read"))]
PermAgentsRead = Annotated["User", Depends(require_permission("agents.read"))]
PermAgentsPromptRead = Annotated["User", Depends(require_permission("agents.prompt.read"))]
PermAgentsPromptEdit = Annotated["User", Depends(require_permission("agents.prompt.edit"))]
PermAgentsPromptRollback = Annotated["User", Depends(require_permission("agents.prompt.rollback"))]
PermAgentsTest = Annotated["User", Depends(require_permission("agents.test"))]
PermAgentsSync = Annotated["User", Depends(require_permission("agents.sync"))]
PermLLMRead = Annotated["User", Depends(require_permission("settings.llm.read"))]
PermLLMEdit = Annotated["User", Depends(require_permission("settings.llm.edit"))]
PermUsersRead = Annotated["User", Depends(require_permission("users.read"))]
PermUsersCreate = Annotated["User", Depends(require_permission("users.create"))]
PermUsersDelete = Annotated["User", Depends(require_permission("users.delete"))]

router = APIRouter(prefix="/admin", tags=["admin"])

# ── Department Scoping Helper ────────────────
_ROLE_LEVEL = {"admin": 4, "manager": 3, "lead": 2, "contributor": 1}


def _scope_department(query, dept_column, user, explicit_dept: str | None = None):
    """Apply department scoping to a query.

    - admin: see all departments (unless explicit_dept filter is set)
    - manager: scoped to own department
    - lead/contributor: always scoped to their own department
    """
    level = _ROLE_LEVEL.get(user.role, 0)
    if level >= 4:
        # Admin can optionally filter, but sees all by default
        if explicit_dept:
            query = query.where(dept_column == explicit_dept)
    else:
        # Manager/Lead/Contributor — scoped to own department
        query = query.where(dept_column == user.department)
    return query


def _redact_for_role(event_dict: dict, user) -> dict:
    """Redact sensitive fields in event payload based on user role."""
    level = _ROLE_LEVEL.get(user.role, 0)
    if level >= 4:  # admin sees all
        return event_dict
    sensitive_keys = ["api_key", "token", "secret", "password", "credential"]
    for key in list(event_dict.keys()):
        if any(s in key.lower() for s in sensitive_keys):
            event_dict[key] = "***REDACTED***"
    return event_dict


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  1) GET /admin/dashboard  — Overview
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/dashboard")
async def get_dashboard(
    user: PermDashboardRead,
    hours: int = Query(24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
):
    """Overview dashboard: status counts, cost, errors, approval backlog."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    # A) Status counts
    status_q = (
        select(
            TraceIndex.status,
            func.count().label("cnt"),
        )
        .where(TraceIndex.last_event_at >= cutoff)
        .group_by(TraceIndex.status)
    )
    status_q = _scope_department(status_q, TraceIndex.department, user)
    status_rows = (await db.execute(status_q)).all()
    status_counts = {row.status: row.cnt for row in status_rows}

    # B) Cost today & 7d
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    cost_q = select(
        func.coalesce(
            func.sum(
                case(
                    (TraceIndex.last_event_at >= today_start, TraceIndex.total_cost_usd),
                    else_=literal_column("0"),
                )
            ),
            0,
        ).label("cost_today"),
        func.coalesce(
            func.sum(
                case(
                    (TraceIndex.last_event_at >= week_ago, TraceIndex.total_cost_usd),
                    else_=literal_column("0"),
                )
            ),
            0,
        ).label("cost_7d"),
    )
    cost_row = (await db.execute(cost_q)).one()

    # C) Approval backlog
    pending_q = (
        select(func.count())
        .select_from(TraceIndex)
        .where(TraceIndex.approval_pending == True)
    )
    pending_q = _scope_department(pending_q, TraceIndex.department, user)
    pending_count = (await db.execute(pending_q)).scalar() or 0

    # D) Top errors (last N hours)
    errors_q = (
        select(
            TraceIndex.last_error_code,
            func.count().label("cnt"),
        )
        .where(
            TraceIndex.last_event_at >= cutoff,
            TraceIndex.status == "failed",
            TraceIndex.last_error_code.isnot(None),
        )
        .group_by(TraceIndex.last_error_code)
        .order_by(func.count().desc())
        .limit(10)
    )
    error_rows = (await db.execute(errors_q)).all()

    # E) Tool denies
    deny_q = (
        select(func.coalesce(func.sum(TraceIndex.denied_calls), 0))
        .where(TraceIndex.last_event_at >= cutoff)
    )
    tool_denies = (await db.execute(deny_q)).scalar() or 0

    # F) Cost by department
    dept_cost_q = (
        select(
            TraceIndex.department,
            func.sum(TraceIndex.total_cost_usd).label("cost"),
        )
        .where(TraceIndex.last_event_at >= week_ago)
        .group_by(TraceIndex.department)
        .order_by(func.sum(TraceIndex.total_cost_usd).desc())
    )
    dept_rows = (await db.execute(dept_cost_q)).all()

    return {
        "status_counts": status_counts,
        "cost": {
            "today_usd": float(cost_row.cost_today),
            "last7d_usd": float(cost_row.cost_7d),
        },
        "approval": {
            "pending": pending_count,
        },
        "top_errors": [
            {"error_code": r.last_error_code, "count": r.cnt}
            for r in error_rows
        ],
        "tool_denies": tool_denies,
        "cost_by_department": [
            {"department": r.department, "cost_usd": float(r.cost)}
            for r in dept_rows
        ],
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  2) GET /admin/traces  — Filterable trace list
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/traces")
async def list_traces(
    user: PermTracesRead,
    status: Optional[str] = None,
    department: Optional[str] = None,
    risk_level: Optional[str] = None,
    approval_pending: Optional[bool] = None,
    q: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Filterable trace list with sorting."""
    query = select(
        TraceIndex.trace_id,
        TraceIndex.department,
        TraceIndex.status,
        TraceIndex.last_event_at,
        TraceIndex.current_step,
        TraceIndex.current_agent_id,
        TraceIndex.total_cost_usd,
        TraceIndex.risk_level,
        TraceIndex.data_sensitivity,
        TraceIndex.last_error_code,
        TraceIndex.last_error_message_short,
        TraceIndex.approval_pending,
        TraceIndex.summary,
    )

    if status:
        query = query.where(TraceIndex.status == status)
    query = _scope_department(query, TraceIndex.department, user, department)
    if risk_level:
        query = query.where(TraceIndex.risk_level == risk_level)
    if approval_pending is not None:
        query = query.where(TraceIndex.approval_pending == approval_pending)
    if q:
        query = query.where(TraceIndex.summary.ilike(f"%{q}%"))

    query = query.order_by(TraceIndex.last_event_at.desc()).limit(limit).offset(offset)

    rows = (await db.execute(query)).all()

    return {
        "traces": [
            {
                "trace_id": r.trace_id,
                "department": r.department,
                "status": r.status,
                "last_event_at": r.last_event_at.isoformat() if r.last_event_at else None,
                "current_step": r.current_step,
                "current_agent_id": r.current_agent_id,
                "total_cost_usd": float(r.total_cost_usd) if r.total_cost_usd else 0,
                "risk_level": r.risk_level,
                "data_sensitivity": r.data_sensitivity,
                "last_error_code": r.last_error_code,
                "last_error_message_short": r.last_error_message_short,
                "approval_pending": r.approval_pending,
                "summary": r.summary,
            }
            for r in rows
        ],
        "count": len(rows),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  3) GET /admin/traces/{trace_id}  — Timeline drilldown
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/traces/{trace_id}")
async def get_trace_detail(
    trace_id: str,
    user: PermTracesRead,
    db: AsyncSession = Depends(get_db),
):
    """Full timeline for a single trace."""
    # Header from trace_index
    header_q = select(TraceIndex).where(TraceIndex.trace_id == trace_id)
    header = (await db.execute(header_q)).scalar_one_or_none()

    # Department ownership check — non-admin/manager can only view own dept
    if header:
        level = _ROLE_LEVEL.get(user.role, 0)
        if level < 3 and header.department != user.department:
            raise HTTPException(
                status_code=403,
                detail="Access denied: trace belongs to another department",
            )

    # Events timeline from audit_events
    events_q = (
        select(
            AuditEvent.created_at,
            AuditEvent.event_type,
            AuditEvent.agent_id,
            AuditEvent.decision,
            AuditEvent.status,
            AuditEvent.reason,
            AuditEvent.tool_name,
            AuditEvent.model,
            AuditEvent.cost_usd,
            AuditEvent.latency_ms,
            AuditEvent.tokens_in,
            AuditEvent.tokens_out,
            AuditEvent.artifact_ids,
            AuditEvent.approver_id,
            AuditEvent.risk_level,
            AuditEvent.error_code,
            AuditEvent.error_message_short,
        )
        .where(AuditEvent.trace_id == trace_id)
        .order_by(AuditEvent.created_at.asc())
    )
    event_rows = (await db.execute(events_q)).all()

    header_data = None
    if header:
        header_data = {
            "trace_id": header.trace_id,
            "department": header.department,
            "status": header.status,
            "started_at": header.started_at.isoformat() if header.started_at else None,
            "ended_at": header.ended_at.isoformat() if header.ended_at else None,
            "total_cost_usd": float(header.total_cost_usd) if header.total_cost_usd else 0,
            "total_tokens_in": header.total_tokens_in,
            "total_tokens_out": header.total_tokens_out,
            "risk_level": header.risk_level,
            "data_sensitivity": header.data_sensitivity,
            "audit_chain_ok": header.audit_chain_ok,
            "summary": header.summary,
        }

    return {
        "header": header_data,
        "events": [
            _redact_for_role({
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "event_type": r.event_type,
                "agent_id": r.agent_id,
                "decision": r.decision,
                "status": r.status,
                "reason": r.reason,
                "tool_name": r.tool_name,
                "model": r.model,
                "cost_usd": float(r.cost_usd) if r.cost_usd else None,
                "latency_ms": r.latency_ms,
                "tokens_in": r.tokens_in,
                "tokens_out": r.tokens_out,
                "artifact_ids": r.artifact_ids,
                "approver_id": r.approver_id,
                "risk_level": r.risk_level,
                "error_code": r.error_code,
                "error_message_short": r.error_message_short,
            }, user)
            for r in event_rows
        ],
        "event_count": len(event_rows),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  4) GET /admin/approvals  — Approval queue
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/approvals")
async def list_approvals(
    user: PermApprovalsRead,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Approval backlog — traces waiting for approval."""
    query = (
        select(
            TraceIndex.trace_id,
            TraceIndex.department,
            TraceIndex.requester_id,
            TraceIndex.last_event_at,
            TraceIndex.risk_level,
            TraceIndex.current_step,
            TraceIndex.summary,
        )
        .where(TraceIndex.approval_pending == True)
        .order_by(TraceIndex.last_event_at.asc())
        .limit(limit)
    )
    query = _scope_department(query, TraceIndex.department, user)

    rows = (await db.execute(query)).all()

    now = datetime.now(timezone.utc)
    return {
        "approvals": [
            {
                "trace_id": r.trace_id,
                "department": r.department,
                "requester_id": r.requester_id,
                "requested_at": r.last_event_at.isoformat() if r.last_event_at else None,
                "waiting_seconds": int((now - r.last_event_at).total_seconds()) if r.last_event_at else 0,
                "risk_level": r.risk_level,
                "current_step": r.current_step,
                "summary": r.summary,
            }
            for r in rows
        ],
        "count": len(rows),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  5) GET /admin/policies  — Policy violations / denies
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/policies")
async def list_policy_events(
    user: PermPoliciesRead,
    days: int = Query(7, ge=1, le=90),
    decision: Optional[str] = None,
    event_type: Optional[str] = None,
    department: Optional[str] = None,
    tool_name: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """Policy violations, denies, egress blocks, sandbox violations."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    query = (
        select(
            AuditEvent.created_at,
            AuditEvent.trace_id,
            AuditEvent.department,
            AuditEvent.agent_id,
            AuditEvent.event_type,
            AuditEvent.decision,
            AuditEvent.reason,
            AuditEvent.tool_name,
            AuditEvent.resource,
            AuditEvent.risk_level,
        )
        .where(AuditEvent.created_at >= cutoff)
    )

    # Default: show deny + security events
    if decision:
        query = query.where(AuditEvent.decision == decision)
    elif event_type:
        query = query.where(AuditEvent.event_type == event_type)
    else:
        # Default filter: denies + security events
        query = query.where(
            (AuditEvent.decision == "deny")
            | AuditEvent.event_type.in_([
                "egress_blocked",
                "sandbox_violation_detected",
                "policy_evaluated",
                "policy_denied",
                "tool_call_denied",
                "data_access_denied",
            ])
        )

    # Department scoping — lead/contributor see own dept only
    query = _scope_department(query, AuditEvent.department, user, department)
    if tool_name:
        query = query.where(AuditEvent.tool_name == tool_name)

    query = query.order_by(AuditEvent.created_at.desc()).limit(limit)

    rows = (await db.execute(query)).all()

    return {
        "events": [
            {
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "trace_id": r.trace_id,
                "department": r.department,
                "agent_id": r.agent_id,
                "event_type": r.event_type,
                "decision": r.decision,
                "reason": r.reason,
                "tool_name": r.tool_name,
                "resource": r.resource,
                "risk_level": r.risk_level,
            }
            for r in rows
        ],
        "count": len(rows),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  6–9) Agent Configuration (Editable System Prompts)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class PromptUpdateRequest(BaseModel):
    """Request body for updating an agent's system prompt."""
    prompt_text: str
    changed_by: str = "admin"
    change_reason: str | None = None


class PromptRollbackRequest(BaseModel):
    """Request body for rolling back to a specific prompt version."""
    target_version: int
    changed_by: str = "admin"


@router.get("/agents")
async def list_agents(
    user: PermAgentsRead,
    department: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List all agents with prompt override info."""
    query = select(
        Agent.id,
        Agent.name,
        Agent.department,
        Agent.tier,
        Agent.status,
        Agent.description,
        Agent.prompt_version,
        Agent.prompt_updated_at,
        Agent.prompt_updated_by,
    )
    # Add a computed column: has_override
    query = query.add_columns(
        (Agent.system_prompt_override.isnot(None)).label("has_prompt_override"),
    )

    query = _scope_department(query, Agent.department, user, department)

    query = query.order_by(Agent.department, Agent.name)
    rows = (await db.execute(query)).all()

    return {
        "agents": [
            {
                "id": r.id,
                "name": r.name,
                "department": r.department,
                "tier": r.tier,
                "status": r.status,
                "description": r.description,
                "prompt_version": r.prompt_version,
                "prompt_updated_at": r.prompt_updated_at.isoformat() if r.prompt_updated_at else None,
                "prompt_updated_by": r.prompt_updated_by,
                "has_prompt_override": bool(r.has_prompt_override),
            }
            for r in rows
        ],
        "count": len(rows),
    }


@router.get("/agents/{agent_id}/prompt")
async def get_agent_prompt(
    agent_id: str,
    user: PermAgentsPromptRead,
    db: AsyncSession = Depends(get_db),
):
    """Get current prompt + version history for an agent."""
    agent = (await db.execute(
        select(Agent).where(Agent.id == agent_id)
    )).scalar_one_or_none()

    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    # Version history
    history_q = (
        select(PromptHistory)
        .where(PromptHistory.agent_id == agent_id)
        .order_by(PromptHistory.version.desc())
        .limit(20)
    )
    history_rows = (await db.execute(history_q)).scalars().all()

    return {
        "agent_id": agent.id,
        "agent_name": agent.name,
        "department": agent.department,
        "current_prompt": agent.system_prompt_override or agent.system_prompt,
        "has_override": agent.system_prompt_override is not None,
        "default_prompt": agent.system_prompt,
        "prompt_version": agent.prompt_version,
        "prompt_updated_at": agent.prompt_updated_at.isoformat() if agent.prompt_updated_at else None,
        "prompt_updated_by": agent.prompt_updated_by,
        "history": [
            {
                "version": h.version,
                "prompt_text": h.prompt_text,
                "changed_by": h.changed_by,
                "changed_at": h.changed_at.isoformat() if h.changed_at else None,
                "change_reason": h.change_reason,
            }
            for h in history_rows
        ],
    }


@router.put("/agents/{agent_id}/prompt")
async def update_agent_prompt(
    agent_id: str,
    body: PromptUpdateRequest,
    user: PermAgentsPromptEdit,
    db: AsyncSession = Depends(get_db),
):
    """Update an agent's system prompt override."""
    agent = (await db.execute(
        select(Agent).where(Agent.id == agent_id)
    )).scalar_one_or_none()

    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    # Increment version
    new_version = (agent.prompt_version or 0) + 1

    # Save to history
    history_entry = PromptHistory(
        agent_id=agent_id,
        version=new_version,
        prompt_text=body.prompt_text,
        changed_by=body.changed_by,
        change_reason=body.change_reason,
    )
    db.add(history_entry)

    # Update agent
    agent.system_prompt_override = body.prompt_text
    agent.prompt_version = new_version
    agent.prompt_updated_at = datetime.now(timezone.utc)
    agent.prompt_updated_by = body.changed_by
    await db.flush()

    return {
        "status": "updated",
        "agent_id": agent_id,
        "prompt_version": new_version,
        "message": f"Prompt updated to version {new_version}",
    }


@router.post("/agents/{agent_id}/prompt/rollback")
async def rollback_agent_prompt(
    agent_id: str,
    body: PromptRollbackRequest,
    user: PermAgentsPromptRollback,
    db: AsyncSession = Depends(get_db),
):
    """Rollback agent prompt to a specific version."""
    agent = (await db.execute(
        select(Agent).where(Agent.id == agent_id)
    )).scalar_one_or_none()

    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    # Find the target version
    history_entry = (await db.execute(
        select(PromptHistory).where(
            PromptHistory.agent_id == agent_id,
            PromptHistory.version == body.target_version,
        )
    )).scalar_one_or_none()

    if not history_entry:
        raise HTTPException(
            status_code=404,
            detail=f"Version {body.target_version} not found for agent {agent_id}",
        )

    # Create a new version entry for the rollback
    rollback_version = (agent.prompt_version or 0) + 1
    rollback_entry = PromptHistory(
        agent_id=agent_id,
        version=rollback_version,
        prompt_text=history_entry.prompt_text,
        changed_by=body.changed_by,
        change_reason=f"Rollback to version {body.target_version}",
    )
    db.add(rollback_entry)

    # Update agent
    agent.system_prompt_override = history_entry.prompt_text
    agent.prompt_version = rollback_version
    agent.prompt_updated_at = datetime.now(timezone.utc)
    agent.prompt_updated_by = body.changed_by
    await db.flush()

    # If target_version is 0, clear the override (restore hardcoded default)
    if body.target_version == 0:
        agent.system_prompt_override = None
        await db.flush()

    return {
        "status": "rolled_back",
        "agent_id": agent_id,
        "from_version": agent.prompt_version - 1,
        "to_version": rollback_version,
        "restored_from": body.target_version,
        "message": f"Prompt rolled back to version {body.target_version} (saved as v{rollback_version})",
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  10) POST /admin/agents/{agent_id}/test  — Test agent with a prompt
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AgentTestRequest(BaseModel):
    """Request body for testing an agent."""
    message: str
    thread_id: str | None = None


# Model tier mapping per provider
_TIER_MODELS = {
    "google": {
        "nano": "gemini-2.0-flash",
        "standard": "gemini-2.0-flash",
        "advanced": "gemini-2.0-flash",
        "code": "gemini-2.0-flash",
        "vision": "gemini-2.0-flash",
    },
    "openai": {
        "nano": "gpt-4o-mini",
        "standard": "gpt-4o",
        "advanced": "gpt-4o",
        "code": "gpt-4o",
        "vision": "gpt-4o",
    },
}


@router.post("/agents/{agent_id}/test")
async def test_agent(
    agent_id: str,
    body: AgentTestRequest,
    user: PermAgentsTest,
    db: AsyncSession = Depends(get_db),
):
    """Admin-only: Test an agent with a prompt and return the LLM response.

    Calls the configured LLM provider (Gemini or OpenAI) using the
    agent's system prompt and tier-appropriate model. Provider and
    API key are read from Redis first, with env var fallback.
    """
    import uuid
    import httpx
    import os

    # Verify agent exists
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    thread_id = body.thread_id or str(uuid.uuid4())

    # Build system prompt: override → DB → Python class default → generic
    from app.agents.prompt_registry import get_prompt_for_agent
    system_prompt = (
        agent.system_prompt_override
        or agent.system_prompt
        or get_prompt_for_agent(agent.name)
        or (
            f"You are {agent.name}, an AI agent in the {agent.department} department. "
            f"Your tier is '{agent.tier}'. Respond helpfully and concisely."
        )
    )

    # Get provider from Redis (default: google)
    try:
        r = await _get_redis()
        provider = await r.get(f"{SETTINGS_REDIS_PREFIX}provider") or "google"
        await r.close()
    except Exception:
        provider = "google"

    # Get API key (Redis first, then env var)
    api_key = await _get_api_key(provider)

    if not api_key:
        return {
            "agent_id": agent_id,
            "agent_name": agent.name,
            "thread_id": thread_id,
            "response": f"Error: API key for '{provider}' not configured. Go to Settings to set it.",
            "status": "error",
        }

    # Select model based on agent tier and provider
    provider_models = _TIER_MODELS.get(provider, _TIER_MODELS["google"])
    model_name = provider_models.get(agent.tier, list(provider_models.values())[0])

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            if provider == "google":
                # Gemini API
                resp = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}",
                    headers={"Content-Type": "application/json"},
                    json={
                        "system_instruction": {"parts": [{"text": system_prompt}]},
                        "contents": [{"role": "user", "parts": [{"text": body.message}]}],
                        "generationConfig": {"maxOutputTokens": 1024, "temperature": 0.7},
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    response_text = parts[0].get("text", "") if parts else "No response"
                else:
                    response_text = "No response from model"
                usage = data.get("usageMetadata", {})
                usage_out = {
                    "prompt_tokens": usage.get("promptTokenCount", 0),
                    "completion_tokens": usage.get("candidatesTokenCount", 0),
                    "total_tokens": usage.get("totalTokenCount", 0),
                }
            else:
                # OpenAI API
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={
                        "model": model_name,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": body.message},
                        ],
                        "max_tokens": 1024,
                        "temperature": 0.7,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                response_text = data["choices"][0]["message"]["content"]
                usage_out = data.get("usage", {})

        return {
            "agent_id": agent_id,
            "agent_name": agent.name,
            "thread_id": thread_id,
            "response": response_text,
            "status": "ok",
            "model": model_name,
            "provider": provider,
            "usage": usage_out,
        }

    except httpx.HTTPStatusError as e:
        error_body = e.response.text[:300] if e.response else str(e)
        return {
            "agent_id": agent_id,
            "agent_name": agent.name,
            "thread_id": thread_id,
            "response": f"LLM Error ({e.response.status_code}): {error_body}",
            "status": "error",
        }
    except Exception as e:
        return {
            "agent_id": agent_id,
            "agent_name": agent.name,
            "thread_id": thread_id,
            "response": f"Error: {str(e)}",
            "status": "error",
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Redis helpers for runtime settings
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SETTINGS_REDIS_PREFIX = "settings:"


async def _get_redis():
    """Get an aioredis connection."""
    import aioredis
    import os
    redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    return aioredis.from_url(redis_url, decode_responses=True)


async def _get_api_key(provider: str = "google") -> str:
    """Get API key: Redis first, then env var fallback."""
    import os
    redis_key = f"{SETTINGS_REDIS_PREFIX}{provider}_api_key"
    try:
        r = await _get_redis()
        key = await r.get(redis_key)
        await r.close()
        if key:
            return key
    except Exception:
        pass
    # Env var fallback
    env_map = {"google": "GOOGLE_API_KEY", "openai": "OPENAI_API_KEY"}
    return os.environ.get(env_map.get(provider, "GOOGLE_API_KEY"), "")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  11) GET /admin/settings/llm  — Get LLM settings
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/settings/llm")
async def get_llm_settings(user: PermLLMRead):
    """Get current LLM configuration (key is masked)."""
    import os

    # Check Redis for saved provider
    try:
        r = await _get_redis()
        provider = await r.get(f"{SETTINGS_REDIS_PREFIX}provider") or "google"
        await r.close()
    except Exception:
        provider = "google"

    api_key = await _get_api_key(provider)
    masked = f"...{api_key[-8:]}" if len(api_key) > 8 else ("***" if api_key else "")

    # Model config
    model_map = {
        "google": "gemini-2.0-flash",
        "openai": "gpt-4o-mini",
    }

    return {
        "provider": provider,
        "model": model_map.get(provider, "gemini-2.0-flash"),
        "api_key_set": bool(api_key),
        "api_key_masked": masked,
        "available_providers": [
            {"id": "google", "name": "Google Gemini", "models": ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-pro"]},
            {"id": "openai", "name": "OpenAI", "models": ["gpt-4o-mini", "gpt-4o", "o3-mini"]},
        ],
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  12) PUT /admin/settings/llm  — Update LLM settings
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class LLMSettingsUpdate(BaseModel):
    """Request body for updating LLM settings."""
    provider: str | None = None   # "google" or "openai"
    api_key: str | None = None    # The raw API key


@router.put("/settings/llm")
async def update_llm_settings(body: LLMSettingsUpdate, user: PermLLMEdit):
    """Update LLM provider and/or API key. Stored in Redis."""
    try:
        r = await _get_redis()

        if body.provider:
            if body.provider not in ("google", "openai"):
                raise HTTPException(status_code=400, detail="Provider must be 'google' or 'openai'")
            await r.set(f"{SETTINGS_REDIS_PREFIX}provider", body.provider)

        if body.api_key:
            provider = body.provider
            if not provider:
                provider = await r.get(f"{SETTINGS_REDIS_PREFIX}provider") or "google"
            await r.set(f"{SETTINGS_REDIS_PREFIX}{provider}_api_key", body.api_key)

        await r.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save settings: {str(e)}")

    return {"status": "ok", "message": "Settings updated"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  13) POST /admin/agents/sync-prompts  — Sync defaults into DB
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/agents/sync-prompts")
async def sync_agent_prompts(user: PermAgentsSync, db: AsyncSession = Depends(get_db)):
    """Sync agent defaults from Python classes into the database.

    - Creates agents that exist in code but not in DB
    - Fills system_prompt for existing agents where it's NULL
    - Does NOT overwrite admin-edited prompts (system_prompt_override)
    """
    from app.agents.prompt_registry import get_all_agent_info

    agent_infos = get_all_agent_info()

    # Get all existing agents from DB (index by name for lookup)
    result = await db.execute(select(Agent))
    existing = {a.name.lower(): a for a in result.scalars().all()}

    created = []
    updated = []
    skipped = []

    for info in agent_infos:
        key = info.name.lower()
        if key in existing:
            agent = existing[key]
            if not agent.system_prompt:
                agent.system_prompt = info.system_prompt
                updated.append(info.name)
            else:
                skipped.append({"name": info.name, "reason": "already has prompt"})
        else:
            # Create new agent in DB
            new_agent = Agent(
                name=info.name,
                department=info.department,
                tier=info.tier,
                status="idle",
                description=f"{info.class_name} — {info.department} department ({info.role})",
                system_prompt=info.system_prompt,
            )
            db.add(new_agent)
            created.append(info.name)

    await db.commit()

    return {
        "status": "ok",
        "created": created,
        "created_count": len(created),
        "updated": updated,
        "updated_count": len(updated),
        "skipped": skipped,
        "total_classes": len(agent_infos),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  14) GET /admin/users  — List all users
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/users")
async def list_users(
    user: PermUsersRead,
    department: str | None = None,
    role: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List all users, optionally filtered by department or role."""
    from app.models.user import User as UserModel

    q = select(UserModel).order_by(UserModel.role, UserModel.name)
    if department:
        q = q.where(UserModel.department == department)
    if role:
        q = q.where(UserModel.role == role)

    result = await db.execute(q)
    users = result.scalars().all()

    return {
        "users": [
            {
                "id": u.id,
                "email": u.email,
                "name": u.name,
                "department": u.department,
                "role": u.role,
                "is_active": u.is_active,
                "status_label": u.status_label,
                "phone_whatsapp": u.phone_whatsapp,
                "telegram_chat_id": u.telegram_chat_id,
                "notification_channels": u.notification_channels,
                "created_at": u.created_at.isoformat() if hasattr(u, "created_at") and u.created_at else None,
            }
            for u in users
        ],
        "count": len(users),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  15) POST /admin/users  — Create user + invite link
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/users", status_code=201)
async def create_user(
    caller: PermUsersCreate,
    data: dict,
    db: AsyncSession = Depends(get_db),
):
    """Admin creates user and gets an invite link.

    Body: {"email": str, "name": str, "department": str, "role": str}
    Returns: {"user": {...}, "invite_link": "/invite?token=xxx"}
    """
    import hashlib
    from datetime import timedelta
    from uuid import uuid4
    from app.models.user import User as UserModel

    email = data.get("email", "").strip().lower()
    name = data.get("name", "").strip()
    department = data.get("department", "").strip()
    role = data.get("role", "contributor").strip()
    phone_whatsapp = data.get("phone_whatsapp", "").strip() or None
    telegram_chat_id = data.get("telegram_chat_id", "").strip() or None

    if not email or not name or not department:
        raise HTTPException(400, "email, name, and department are required")

    if role not in ("admin", "manager", "lead", "contributor"):
        raise HTTPException(400, f"Invalid role: {role}")

    # Check duplicate
    result = await db.execute(select(UserModel).where(UserModel.email == email))
    if result.scalar_one_or_none():
        raise HTTPException(400, "Email already registered")

    # Generate invite token
    raw_token = uuid4().hex
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires = datetime.now(timezone.utc) + timedelta(days=7)

    user = UserModel(
        email=email,
        name=name,
        department=department,
        role=role,
        is_active=False,
        hashed_password=None,
        phone_whatsapp=phone_whatsapp,
        telegram_chat_id=telegram_chat_id,
        invite_token_hash=token_hash,
        invite_expires_at=expires,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "department": user.department,
            "role": user.role,
            "status_label": user.status_label,
            "phone_whatsapp": user.phone_whatsapp,
            "telegram_chat_id": user.telegram_chat_id,
        },
        "invite_token": raw_token,
        "invite_link": f"/invite?token={raw_token}",
        "expires_at": expires.isoformat(),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  16) DELETE /admin/users/{user_id}  — Deactivate user
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.delete("/users/{user_id}")
async def deactivate_user(
    caller: PermUsersDelete,
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Deactivate a user (soft delete)."""
    from app.models.user import User as UserModel

    result = await db.execute(select(UserModel).where(UserModel.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(404, "User not found")

    user.is_active = False
    user.invite_token_hash = None
    await db.flush()

    return {"status": "ok", "message": f"User {user.email} deactivated"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  17) POST /admin/approvals/{trace_id}/decide  — Approve/Reject
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ApprovalDecisionRequest(BaseModel):
    decision: str  # "approved" or "rejected"
    reason: str | None = None


@router.post("/approvals/{trace_id}/decide")
async def decide_approval(
    trace_id: str,
    body: ApprovalDecisionRequest,
    user: PermApprovalsDecide,
    db: AsyncSession = Depends(get_db),
):
    """Approve or reject a pending approval, recording the user identity."""
    from app.core.deps import ROLE_HIERARCHY

    if body.decision not in ("approved", "rejected"):
        raise HTTPException(400, "decision must be 'approved' or 'rejected'")

    # Minimum role: lead
    user_level = ROLE_HIERARCHY.get(user.role, 0)
    if user_level < 2:
        raise HTTPException(403, "Contributors cannot approve or reject traces")

    # Fetch the trace
    result = await db.execute(
        select(TraceIndex).where(TraceIndex.trace_id == trace_id)
    )
    trace = result.scalar_one_or_none()

    if not trace:
        raise HTTPException(404, "Trace not found")

    if not trace.approval_pending:
        raise HTTPException(400, "This trace is not pending approval")

    # Department scoping: leads/contributors can only decide for their dept
    if user_level < 3 and trace.department != user.department:
        raise HTTPException(403, "You can only approve/reject traces in your department")

    # Apply decision
    now = datetime.now(timezone.utc)
    trace.approval_pending = False
    trace.approval_decision = body.decision
    trace.approved_by = user.email
    trace.approved_at = now

    if body.decision == "approved":
        trace.status = "running"
    else:
        trace.status = "failed"
        trace.last_error_code = "REJECTED"
        trace.last_error_message_short = body.reason or "Rejected by approver"

    # Create audit event
    audit_event = AuditEvent(
        trace_id=trace_id,
        event_type="approval_decision",
        agent_id="system",
        department=trace.department,
        decision=body.decision,
        reason=body.reason,
        approver_id=user.email,
        risk_level=trace.risk_level,
    )
    db.add(audit_event)
    await db.flush()

    # ── Sync decision to ApprovalGate (Redis) ──
    try:
        from app.core.approval_gate import ApprovalGate
        # Find pending approvals for this trace
        pending = await ApprovalGate.get_pending()
        matched = [r for r in pending if r.trace_id == trace_id]
        for req in matched:
            if body.decision == "approved":
                await ApprovalGate.grant(req.approval_id, user.email)
                # Trigger resume if tool context exists
                if req.tool_name:
                    import asyncio
                    from app.api.v1.gateway import _resume_approved_tool
                    asyncio.create_task(_resume_approved_tool(req))
            else:
                await ApprovalGate.reject(req.approval_id, user.email, body.reason or "")
    except Exception as e:
        import structlog
        structlog.get_logger().warning("approval_gate_sync_error", trace_id=trace_id, error=str(e))

    return {
        "status": "ok",
        "trace_id": trace_id,
        "decision": body.decision,
        "decided_by": user.email,
        "decided_at": now.isoformat(),
    }

