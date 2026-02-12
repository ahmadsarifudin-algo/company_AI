"""
Audit Service — Event-sourced immutable logging with hash chain integrity.

Every LLM call, tool invocation, data access, and agent decision is logged
as an immutable event with SHA-256 hashes. Events within the same trace
are linked via a hash chain for tamper evidence.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog

logger = structlog.get_logger()


@dataclass
class ChainVerification:
    """Result of a hash chain integrity check."""

    valid: bool
    total_events: int = 0
    broken_at: int | None = None
    break_type: str | None = None  # "hash_mismatch" | "chain_break"
    message: str = ""


def _canonical_json(fields: dict[str, Any]) -> str:
    """Create a canonical JSON string for hashing.

    Keys are sorted, None values excluded, consistent formatting.
    """
    filtered = {k: v for k, v in sorted(fields.items()) if v is not None}
    return json.dumps(filtered, sort_keys=True, ensure_ascii=False, default=str)


def _compute_hash(data: str) -> str:
    """Compute SHA-256 hash of a string."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


class AuditService:
    """Service for event-sourced audit logging with hash chain.

    Key methods:
    - emit(): Create a new audit event with automatic hash chain linking
    - log_action(): Legacy method (backward compat), delegates to emit()
    - verify_chain_integrity(): Verify the hash chain for a trace
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def emit(
        self,
        event_type: str,
        agent_name: str,
        department: str,
        trace_id: str = "",
        span_id: str = "",
        action_type: str = "",
        resource_scope: str | None = None,
        details: str | None = None,
        prompt_hash: str | None = None,
        tool_name: str | None = None,
        tool_args_hash: str | None = None,
        data_access_scope: str | None = None,
        approver_id: str | None = None,
        approval_chain: str | None = None,
        artifact_ids: list[str] | None = None,
        cost_estimate: float | None = None,
        risk_score: float | None = None,
        execution_time_ms: float | None = None,
        idempotency_key: str | None = None,
    ) -> AuditLog:
        """Emit an immutable audit event with hash chain linking.

        This is the primary method for all audit logging. It:
        1. Computes the event hash (SHA-256 of canonical JSON)
        2. Links to the previous event in the same trace (hash chain)
        3. Inserts the event (APPEND-ONLY, never updated)

        Args:
            event_type: Type of event (llm_call, tool_call, data_read, etc.)
            agent_name: Agent that triggered this event.
            department: Department scope.
            trace_id: Workflow trace ID for correlation.
            span_id: Step span ID within the trace.
            action_type: Legacy action type field.
            ... (other fields as needed)

        Returns:
            The created AuditLog entry with computed hashes.
        """
        if not action_type:
            action_type = event_type

        # Build canonical fields for hashing
        hash_fields = {
            "event_type": event_type,
            "agent_name": agent_name,
            "department": department,
            "trace_id": trace_id,
            "span_id": span_id,
            "action_type": action_type,
            "resource_scope": resource_scope,
            "details": details,
            "prompt_hash": prompt_hash,
            "tool_name": tool_name,
            "tool_args_hash": tool_args_hash,
            "data_access_scope": data_access_scope,
            "cost_estimate": cost_estimate,
            "risk_score": risk_score,
        }

        event_hash = _compute_hash(_canonical_json(hash_fields))

        # Get previous event in this trace for hash chain
        prev_event_hash = None
        if trace_id:
            prev = await self._get_last_event(trace_id)
            if prev:
                prev_event_hash = prev.event_hash

        # Create entry (APPEND-ONLY)
        entry = AuditLog(
            agent_name=agent_name,
            department=department,
            action_type=action_type,
            event_type=event_type,
            resource_scope=resource_scope,
            details=details,
            trace_id=trace_id,
            span_id=span_id,
            prompt_hash=prompt_hash,
            tool_name=tool_name,
            tool_args_hash=tool_args_hash,
            data_access_scope=data_access_scope,
            approver_id=approver_id,
            approval_chain=approval_chain,
            artifact_ids=artifact_ids,
            cost_estimate=cost_estimate,
            risk_score=risk_score,
            execution_time_ms=execution_time_ms,
            idempotency_key=idempotency_key,
            event_hash=event_hash,
            prev_event_hash=prev_event_hash,
        )
        self.db.add(entry)
        await self.db.flush()

        logger.info(
            "audit_event",
            event_type=event_type,
            agent=agent_name,
            department=department,
            trace_id=trace_id,
            event_hash=event_hash[:16],
            chain_linked=prev_event_hash is not None,
        )

        return entry

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
        """Legacy method — delegates to emit() for backward compatibility."""
        return await self.emit(
            event_type=action_type,
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

    async def verify_chain_integrity(self, trace_id: str) -> ChainVerification:
        """Verify the hash chain for an entire trace.

        Recomputes each event's hash and checks the chain linkage.

        Args:
            trace_id: The workflow trace to verify.

        Returns:
            ChainVerification with valid/invalid status and break point.
        """
        events = await self._get_events_ordered(trace_id)

        if not events:
            return ChainVerification(valid=True, total_events=0, message="No events found")

        for i, event in enumerate(events):
            # Recompute the event hash from canonical fields
            hash_fields = {
                "event_type": event.event_type,
                "agent_name": event.agent_name,
                "department": event.department,
                "trace_id": event.trace_id,
                "span_id": event.span_id,
                "action_type": event.action_type,
                "resource_scope": event.resource_scope,
                "details": event.details,
                "prompt_hash": event.prompt_hash,
                "tool_name": event.tool_name,
                "tool_args_hash": event.tool_args_hash,
                "data_access_scope": event.data_access_scope,
                "cost_estimate": event.cost_estimate,
                "risk_score": event.risk_score,
            }
            recomputed = _compute_hash(_canonical_json(hash_fields))

            if recomputed != event.event_hash:
                return ChainVerification(
                    valid=False,
                    total_events=len(events),
                    broken_at=i,
                    break_type="hash_mismatch",
                    message=f"Event {i} hash mismatch: stored={event.event_hash[:16]}... recomputed={recomputed[:16]}...",
                )

            # Check chain linkage (except first event)
            if i > 0 and event.prev_event_hash != events[i - 1].event_hash:
                return ChainVerification(
                    valid=False,
                    total_events=len(events),
                    broken_at=i,
                    break_type="chain_break",
                    message=f"Event {i} chain break: prev_hash doesn't match event {i - 1}",
                )

        return ChainVerification(
            valid=True,
            total_events=len(events),
            message=f"All {len(events)} events verified, chain intact",
        )

    async def _get_last_event(self, trace_id: str) -> AuditLog | None:
        """Get the most recent event in a trace (for chain linking)."""
        query = (
            select(AuditLog)
            .where(AuditLog.trace_id == trace_id)
            .order_by(AuditLog.created_at.desc())
            .limit(1)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _get_events_ordered(self, trace_id: str) -> list[AuditLog]:
        """Get all events in a trace, ordered by creation time."""
        query = (
            select(AuditLog)
            .where(AuditLog.trace_id == trace_id)
            .order_by(AuditLog.created_at.asc())
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_agent_history(
        self,
        agent_name: str,
        limit: int = 50,
        action_type: str | None = None,
    ) -> list[AuditLog]:
        """Retrieve audit trail for a specific agent."""
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
        """Retrieve audit trail for an entire department."""
        query = (
            select(AuditLog)
            .where(AuditLog.department == department)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_cost_summary(self, department: str | None = None) -> dict:
        """Get cost summary, optionally filtered by department."""
        query = select(AuditLog)
        if department:
            query = query.where(AuditLog.department == department)

        result = await self.db.execute(query)
        entries = list(result.scalars().all())

        total_cost = sum(e.cost_estimate or 0.0 for e in entries)
        by_action: dict[str, dict] = {}
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
