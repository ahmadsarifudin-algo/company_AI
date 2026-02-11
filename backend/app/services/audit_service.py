"""
Audit Service — Immutable action logging for agent activities.

Every LLM call, tool invocation, and agent decision is logged to the
audit_log table for compliance, debugging, and cost tracking.
"""

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog

logger = structlog.get_logger()


class AuditService:
    """Service for writing and querying immutable audit logs."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_action(
        self,
        agent_name: str,
        department: str,
        action_type: str,
        details: str | None = None,
        resource_scope: str | None = None,
        approval_chain: str | None = None,
        cost_estimate: float | None = None,
        risk_score: float | None = None,
        execution_time_ms: float | None = None,
    ) -> AuditLog:
        """Write an immutable audit log entry.

        Args:
            agent_name: Name of the agent performing the action.
            department: Department scope.
            action_type: Type of action (e.g., "llm_call", "tool_invoke", "task_complete").
            details: JSON or text description of what happened.
            resource_scope: What resource was accessed/modified.
            approval_chain: Who approved this action (if applicable).
            cost_estimate: Estimated cost in USD.
            risk_score: Risk score 0.0-1.0 for the action.
            execution_time_ms: How long the action took.

        Returns:
            The created AuditLog entry.
        """
        entry = AuditLog(
            agent_name=agent_name,
            department=department,
            action_type=action_type,
            details=details,
            resource_scope=resource_scope,
            approval_chain=approval_chain,
            cost_estimate=cost_estimate,
            risk_score=risk_score,
            execution_time_ms=execution_time_ms,
        )
        self.db.add(entry)
        await self.db.flush()

        logger.info(
            "audit_logged",
            agent=agent_name,
            department=department,
            action=action_type,
            cost=cost_estimate,
        )
        return entry

    async def get_agent_history(
        self,
        agent_name: str,
        limit: int = 50,
        action_type: str | None = None,
    ) -> list[AuditLog]:
        """Retrieve audit trail for a specific agent.

        Args:
            agent_name: Agent to query history for.
            limit: Max number of entries to return.
            action_type: Optional filter by action type.

        Returns:
            List of AuditLog entries, newest first.
        """
        query = select(AuditLog).where(AuditLog.agent_name == agent_name)
        if action_type:
            query = query.where(AuditLog.action_type == action_type)
        query = query.order_by(AuditLog.created_at.desc()).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_department_history(
        self,
        department: str,
        limit: int = 100,
    ) -> list[AuditLog]:
        """Retrieve audit trail for an entire department.

        Args:
            department: Department to query.
            limit: Max entries.

        Returns:
            List of AuditLog entries, newest first.
        """
        query = (
            select(AuditLog)
            .where(AuditLog.department == department)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_cost_summary(self, department: str | None = None) -> dict:
        """Get cost summary, optionally filtered by department.

        Returns:
            Dict with total_cost, action_count, and breakdown by action_type.
        """
        query = select(AuditLog)
        if department:
            query = query.where(AuditLog.department == department)

        result = await self.db.execute(query)
        entries = list(result.scalars().all())

        total_cost = sum(e.cost_estimate or 0.0 for e in entries)
        by_action = {}
        for entry in entries:
            key = entry.action_type
            if key not in by_action:
                by_action[key] = {"count": 0, "cost": 0.0}
            by_action[key]["count"] += 1
            by_action[key]["cost"] += entry.cost_estimate or 0.0

        return {
            "total_entries": len(entries),
            "total_cost_usd": round(total_cost, 6),
            "by_action_type": by_action,
        }
