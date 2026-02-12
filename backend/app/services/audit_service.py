"""
Audit Service — Event-sourced immutable logging with hash chain + trace index.

Every LLM call, tool invocation, data access, and agent decision is logged
as an immutable event with SHA-256 hashes. Events within the same trace
are linked via a hash chain for tamper evidence.

Dual-mode: async (for FastAPI endpoints) and sync (for telemetry DB sink).
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.audit import AuditEvent, AuditLog  # AuditLog = backward compat
from app.models.trace_index import TraceIndex

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


# ── Risk escalation map ──────────────────────────
_RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _max_risk(a: str, b: str) -> str:
    """Return the higher risk level."""
    return a if _RISK_ORDER.get(a, 0) >= _RISK_ORDER.get(b, 0) else b


def _max_sensitivity(a: str, b: str) -> str:
    """Return the more sensitive classification."""
    order = {"public": 0, "internal": 1, "confidential": 2, "pii": 3}
    return a if order.get(a, 0) >= order.get(b, 0) else b


# Terminal event types that mark a trace as ended
_TERMINAL_EVENTS = frozenset({
    "workflow_completed", "workflow_failed", "workflow_cancelled",
    "agent_completed", "agent_failed",
})

_FAILURE_STATUSES = frozenset({
    "workflow_failed", "agent_failed", "step_failed",
    "llm_call_failed", "tool_failed",
})


class AuditService:
    """Service for event-sourced audit logging with hash chain.

    Key methods:
    - emit(): Create a new audit event (async) with hash chain + trace index upsert
    - emit_sync(): Same as emit() but synchronous (for telemetry DB sink)
    - log_action(): Legacy method (backward compat), delegates to emit()
    - verify_chain_integrity(): Verify the hash chain for a trace
    """

    def __init__(self, db: AsyncSession | Session):
        self.db = db
        self._is_sync = isinstance(db, Session)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  SYNC path (called from Telemetry._db_sink)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def emit_sync(self, payload: dict[str, Any]) -> AuditEvent:
        """Synchronous emit — inserts audit_event + upserts trace_index.

        Args:
            payload: Full telemetry dict from Telemetry.emit()

        Returns:
            The created AuditEvent.
        """
        assert self._is_sync, "emit_sync requires a synchronous Session"
        db: Session = self.db  # type: ignore

        trace_id = payload.get("trace_id", "")
        event_type = payload.get("event_type", "")

        # Build hash fields
        hash_fields = {
            "event_type": event_type,
            "agent_id": payload.get("agent_id"),
            "department": payload.get("department"),
            "trace_id": trace_id,
            "span_id": payload.get("span_id"),
            "tool_name": payload.get("tool_name"),
            "tool_args_hash": payload.get("tool_args_hash"),
            "prompt_hash": payload.get("prompt_hash"),
            "resource": payload.get("resource"),
            "data_access_scope": payload.get("data_access_scope"),
            "cost_usd": payload.get("cost_usd"),
        }
        event_hash = _compute_hash(_canonical_json(hash_fields))

        # Get previous event in this trace for hash chain
        prev_event_hash = None
        if trace_id:
            prev = (
                db.query(AuditEvent)
                .filter(AuditEvent.trace_id == trace_id)
                .order_by(AuditEvent.created_at.desc())
                .first()
            )
            if prev:
                prev_event_hash = prev.event_hash

        # Insert audit event (APPEND-ONLY)
        entry = AuditEvent(
            trace_id=trace_id,
            span_id=payload.get("span_id"),
            parent_span_id=payload.get("parent_span_id"),
            department=payload.get("department", ""),
            agent_id=payload.get("agent_id", ""),
            agent_role=payload.get("agent_role", "agent"),
            requester_id=payload.get("requester_id"),
            environment=payload.get("environment", "prod"),
            event_type=event_type,
            status=payload.get("status"),
            decision=payload.get("decision"),
            risk_level=payload.get("risk_level", "low"),
            data_sensitivity=payload.get("data_sensitivity", "internal"),
            reason=payload.get("reason"),
            error_code=payload.get("error_code"),
            error_class=payload.get("error_class"),
            error_message_short=payload.get("error_message_short"),
            provider=payload.get("provider"),
            model=payload.get("model"),
            tokens_in=payload.get("tokens_in"),
            tokens_out=payload.get("tokens_out"),
            cost_usd=payload.get("cost_usd"),
            latency_ms=payload.get("latency_ms"),
            tool_name=payload.get("tool_name"),
            tool_risk_level=payload.get("tool_risk_level"),
            tool_args_hash=payload.get("tool_args_hash"),
            egress_domain=payload.get("egress_domain"),
            sandbox_violation=payload.get("sandbox_violation"),
            resource=payload.get("resource"),
            data_access_scope=payload.get("data_access_scope"),
            row_count=payload.get("row_count"),
            approval_required_roles=payload.get("approval_required_roles"),
            approval_chain=payload.get("approval_chain"),
            approver_id=payload.get("approver_id"),
            approval_request_id=payload.get("approval_request_id"),
            approval_latency_ms=payload.get("approval_latency_ms"),
            artifact_ids=payload.get("artifact_ids"),
            artifact_types=payload.get("artifact_types"),
            artifact_hashes=payload.get("artifact_hashes"),
            artifact_sensitivity=payload.get("artifact_sensitivity"),
            prev_event_hash=prev_event_hash,
            event_hash=event_hash,
            prompt_hash=payload.get("prompt_hash"),
        )
        db.add(entry)
        db.flush()

        # Upsert trace_index
        self._upsert_trace_index_sync(db, payload, event_type)

        logger.info(
            "audit_event_persisted",
            event_type=event_type,
            agent_id=payload.get("agent_id"),
            trace_id=trace_id,
            event_hash=event_hash[:16],
        )

        return entry

    def _upsert_trace_index_sync(
        self,
        db: Session,
        payload: dict[str, Any],
        event_type: str,
    ) -> None:
        """Upsert trace_index row on every event (sync path)."""
        trace_id = payload.get("trace_id", "")
        if not trace_id:
            return

        now = datetime.now(timezone.utc)
        cost = payload.get("cost_usd") or 0
        tokens_in = payload.get("tokens_in") or 0
        tokens_out = payload.get("tokens_out") or 0

        # Derive trace-level status
        is_terminal = event_type in _TERMINAL_EVENTS
        is_failure = event_type in _FAILURE_STATUSES
        is_approval = event_type == "approval_requested"
        is_approval_resolved = event_type in ("approval_granted", "approval_denied")
        is_deny = payload.get("decision") == "deny"

        existing = db.query(TraceIndex).filter(TraceIndex.trace_id == trace_id).first()

        if existing is None:
            # First event for this trace — INSERT
            status = "running"
            if is_failure:
                status = "failed"
            elif is_approval:
                status = "needs_approval"
            elif is_terminal:
                status = "completed" if not is_failure else "failed"

            row = TraceIndex(
                trace_id=trace_id,
                department=payload.get("department", ""),
                requester_id=payload.get("requester_id"),
                environment=payload.get("environment", "prod"),
                started_at=now,
                last_event_at=now,
                status=status,
                current_step=payload.get("current_step"),
                current_agent_id=payload.get("agent_id"),
                last_event_type=event_type,
                last_error_code=payload.get("error_code"),
                last_error_message_short=payload.get("error_message_short"),
                risk_level=payload.get("risk_level", "low"),
                data_sensitivity=payload.get("data_sensitivity", "internal"),
                total_cost_usd=cost,
                total_tokens_in=tokens_in,
                total_tokens_out=tokens_out,
                tool_calls=1 if event_type.startswith("tool_") else 0,
                denied_calls=1 if is_deny else 0,
                approval_pending=is_approval,
                summary=payload.get("summary"),
            )
            db.add(row)
        else:
            # Subsequent event — UPDATE aggregates
            existing.last_event_at = now
            existing.last_event_type = event_type
            existing.current_step = payload.get("current_step") or existing.current_step
            existing.current_agent_id = payload.get("agent_id") or existing.current_agent_id
            existing.total_cost_usd = float(existing.total_cost_usd or 0) + cost
            existing.total_tokens_in = (existing.total_tokens_in or 0) + tokens_in
            existing.total_tokens_out = (existing.total_tokens_out or 0) + tokens_out

            # Risk / sensitivity escalation (never downgrade)
            existing.risk_level = _max_risk(
                existing.risk_level, payload.get("risk_level", "low"),
            )
            existing.data_sensitivity = _max_sensitivity(
                existing.data_sensitivity, payload.get("data_sensitivity", "internal"),
            )

            # Tool count
            if event_type.startswith("tool_"):
                existing.tool_calls = (existing.tool_calls or 0) + 1
            if is_deny:
                existing.denied_calls = (existing.denied_calls or 0) + 1

            # Status transitions
            if is_approval:
                existing.status = "needs_approval"
                existing.approval_pending = True
            elif is_approval_resolved:
                existing.approval_pending = False
                existing.status = "running"
            elif is_failure:
                existing.status = "failed"
                existing.last_error_code = payload.get("error_code")
                existing.last_error_message_short = payload.get("error_message_short")
            elif is_terminal:
                existing.status = "completed"
                existing.ended_at = now

            # Summary update
            if payload.get("summary"):
                existing.summary = payload["summary"]

        db.flush()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  ASYNC path (original — for FastAPI endpoints)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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
    ) -> AuditEvent:
        """Emit an immutable audit event with hash chain linking.

        This is the primary async method for all audit logging. It:
        1. Computes the event hash (SHA-256 of canonical JSON)
        2. Links to the previous event in the same trace (hash chain)
        3. Inserts the event (APPEND-ONLY, never updated)
        """
        if not action_type:
            action_type = event_type

        # Build canonical fields for hashing
        hash_fields = {
            "event_type": event_type,
            "agent_id": agent_name,
            "department": department,
            "trace_id": trace_id,
            "span_id": span_id,
            "tool_name": tool_name,
            "tool_args_hash": tool_args_hash,
            "prompt_hash": prompt_hash,
            "resource": resource_scope,
            "data_access_scope": data_access_scope,
            "cost_usd": cost_estimate,
        }

        event_hash = _compute_hash(_canonical_json(hash_fields))

        # Get previous event in this trace for hash chain
        prev_event_hash = None
        if trace_id:
            prev = await self._get_last_event(trace_id)
            if prev:
                prev_event_hash = prev.event_hash

        # Create entry (APPEND-ONLY)
        entry = AuditEvent(
            trace_id=trace_id,
            span_id=span_id,
            department=department,
            agent_id=agent_name,
            event_type=event_type,
            resource=resource_scope,
            reason=details,
            prompt_hash=prompt_hash,
            tool_name=tool_name,
            tool_args_hash=tool_args_hash,
            data_access_scope=data_access_scope,
            approver_id=approver_id,
            approval_chain=approval_chain if isinstance(approval_chain, (dict, list)) else None,
            artifact_ids=artifact_ids,
            cost_usd=cost_estimate,
            latency_ms=int(execution_time_ms) if execution_time_ms else None,
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
    ) -> AuditEvent:
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
        """
        events = await self._get_events_ordered(trace_id)

        if not events:
            return ChainVerification(valid=True, total_events=0, message="No events found")

        for i, event in enumerate(events):
            hash_fields = {
                "event_type": event.event_type,
                "agent_id": event.agent_id,
                "department": event.department,
                "trace_id": event.trace_id,
                "span_id": event.span_id,
                "tool_name": event.tool_name,
                "tool_args_hash": event.tool_args_hash,
                "prompt_hash": event.prompt_hash,
                "resource": event.resource,
                "data_access_scope": event.data_access_scope,
                "cost_usd": float(event.cost_usd) if event.cost_usd else None,
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

    async def _get_last_event(self, trace_id: str) -> AuditEvent | None:
        """Get the most recent event in a trace (for chain linking)."""
        query = (
            select(AuditEvent)
            .where(AuditEvent.trace_id == trace_id)
            .order_by(AuditEvent.created_at.desc())
            .limit(1)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _get_events_ordered(self, trace_id: str) -> list[AuditEvent]:
        """Get all events in a trace, ordered by creation time."""
        query = (
            select(AuditEvent)
            .where(AuditEvent.trace_id == trace_id)
            .order_by(AuditEvent.created_at.asc())
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_agent_history(
        self,
        agent_name: str,
        limit: int = 50,
        action_type: str | None = None,
    ) -> list[AuditEvent]:
        """Retrieve audit trail for a specific agent."""
        query = select(AuditEvent).where(AuditEvent.agent_id == agent_name)
        if action_type:
            query = query.where(AuditEvent.event_type == action_type)
        query = query.order_by(AuditEvent.created_at.desc()).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_department_history(
        self,
        department: str,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """Retrieve audit trail for an entire department."""
        query = (
            select(AuditEvent)
            .where(AuditEvent.department == department)
            .order_by(AuditEvent.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_cost_summary(self, department: str | None = None) -> dict:
        """Get cost summary, optionally filtered by department."""
        query = select(AuditEvent)
        if department:
            query = query.where(AuditEvent.department == department)

        result = await self.db.execute(query)
        entries = list(result.scalars().all())

        total_cost = sum(float(e.cost_usd or 0) for e in entries)
        by_type: dict[str, dict] = {}
        for entry in entries:
            key = entry.event_type
            if key not in by_type:
                by_type[key] = {"count": 0, "cost": 0.0}
            by_type[key]["count"] += 1
            by_type[key]["cost"] += float(entry.cost_usd or 0)

        return {
            "total_entries": len(entries),
            "total_cost_usd": round(total_cost, 6),
            "by_event_type": by_type,
        }
