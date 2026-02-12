"""
Telemetry — Structured event emitter for dashboard timeline.

Emits lifecycle events that map to audit_events + trace_index tables.
Each event carries full context for:
- Dashboard timeline (trace/span tree)
- Cost analytics (tokens, cost_usd, latency)
- Error categorization (error_code, error_class)
- Approval flow (approval_required_roles, approval_chain)

Usage:
    telemetry = Telemetry(agent_id="accounting_agent", department="finance")
    telemetry.emit(trace_id=..., span_id=..., event_type="step_started", ...)
"""

from __future__ import annotations

import time
from typing import Any, Optional

import structlog

logger = structlog.get_logger()


# ═══════════════════════════════════════════════════════════════
#  EVENT TYPE TAXONOMY (40+ events)
# ═══════════════════════════════════════════════════════════════

class EventType:
    """Standard lifecycle event types for agent telemetry.

    Flat, prefix-consistent naming for UI timeline + KPI.
    """

    # ── Workflow lifecycle ────────────────────────
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"
    WORKFLOW_CANCELLED = "workflow_cancelled"

    # ── Step lifecycle ────────────────────────────
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"
    STEP_RETRIED = "step_retried"
    STEP_SKIPPED = "step_skipped"

    # ── Agent lifecycle (backward compat) ─────────
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"
    AGENT_FAILED = "agent_failed"

    # ── Policy & security ─────────────────────────
    POLICY_EVALUATED = "policy_evaluated"
    POLICY_DENIED = "policy_denied"
    SANDBOX_VIOLATION_DETECTED = "sandbox_violation_detected"
    EGRESS_BLOCKED = "egress_blocked"

    # ── LLM ───────────────────────────────────────
    LLM_CALL_STARTED = "llm_call_started"
    LLM_CALL_COMPLETED = "llm_call_completed"
    LLM_CALL_FAILED = "llm_call_failed"
    LLM_PROVIDER_FALLBACK_USED = "llm_provider_fallback_used"

    # ── Tools ─────────────────────────────────────
    TOOL_CALL_REQUESTED = "tool_call_requested"
    TOOL_CALL_ALLOWED = "tool_call_allowed"
    TOOL_CALL_DENIED = "tool_call_denied"
    TOOL_CALLED = "tool_called"
    TOOL_FAILED = "tool_failed"

    # ── Approvals ─────────────────────────────────
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_DENIED = "approval_denied"
    APPROVAL_EXPIRED = "approval_expired"

    # ── Data access ───────────────────────────────
    DATA_ACCESS_REQUESTED = "data_access_requested"
    DATA_ACCESS_ALLOWED = "data_access_allowed"
    DATA_ACCESS_DENIED = "data_access_denied"

    # ── Artifacts ─────────────────────────────────
    ARTIFACT_CREATED = "artifact_created"
    ARTIFACT_ACCESSED = "artifact_accessed"
    ARTIFACT_STORED = "artifact_stored"  # backward compat

    # ── Budget ────────────────────────────────────
    BUDGET_RESERVED = "budget_reserved"
    BUDGET_RELEASED = "budget_released"
    BUDGET_EXCEEDED = "budget_exceeded"

    # ── Integrity ─────────────────────────────────
    AUDIT_CHAIN_VERIFIED = "audit_chain_verified"
    AUDIT_CHAIN_BROKEN = "audit_chain_broken"

    # ── MVP minimum set (for quick reference) ─────
    # workflow_started/completed/failed
    # step_started/completed/failed
    # policy_evaluated
    # llm_call_completed/failed
    # tool_call_denied
    # approval_requested/granted/denied
    # artifact_created


# ── Helper for workflow terminal events ──────────
_TERMINAL_EVENTS = frozenset({
    EventType.WORKFLOW_COMPLETED,
    EventType.WORKFLOW_FAILED,
    EventType.WORKFLOW_CANCELLED,
    EventType.AGENT_COMPLETED,
    EventType.AGENT_FAILED,
})

_FAILURE_EVENTS = frozenset({
    EventType.WORKFLOW_FAILED,
    EventType.STEP_FAILED,
    EventType.AGENT_FAILED,
    EventType.LLM_CALL_FAILED,
    EventType.TOOL_FAILED,
})

_DENY_EVENTS = frozenset({
    EventType.POLICY_DENIED,
    EventType.TOOL_CALL_DENIED,
    EventType.DATA_ACCESS_DENIED,
    EventType.APPROVAL_DENIED,
    EventType.EGRESS_BLOCKED,
    EventType.SANDBOX_VIOLATION_DETECTED,
})


def now_ms() -> int:
    """Current time in milliseconds (epoch)."""
    return int(time.time() * 1000)


class Telemetry:
    """Structured event emitter for agent lifecycle tracking.

    On emit():
      1) INSERT INTO audit_events(...)       via _db_sink()
      2) UPSERT trace_index(...)             via _db_sink()
      3) Fallback: structlog                 always
    """

    __slots__ = ("agent_id", "department", "environment")

    def __init__(self, agent_id: str, department: str, environment: str = "prod") -> None:
        self.agent_id = agent_id
        self.department = department
        self.environment = environment

    def emit(
        self,
        *,
        trace_id: str,
        span_id: str,
        parent_span_id: Optional[str] = None,
        event_type: str,
        status: Optional[str] = None,
        # policy
        decision: Optional[str] = None,
        reason: Optional[str] = None,
        risk_level: str = "low",
        data_sensitivity: str = "internal",
        requester_id: Optional[str] = None,
        resource: Optional[str] = None,
        # LLM
        provider: Optional[str] = None,
        model: Optional[str] = None,
        tokens_in: Optional[int] = None,
        tokens_out: Optional[int] = None,
        cost_usd: Optional[float] = None,
        latency_ms: Optional[int] = None,
        # artifacts
        artifact_ids: Optional[list[str]] = None,
        artifact_types: Optional[list[str]] = None,
        # tool
        tool_name: Optional[str] = None,
        tool_risk_level: Optional[str] = None,
        tool_args_hash: Optional[str] = None,
        egress_domain: Optional[str] = None,
        sandbox_violation: Optional[bool] = None,
        # data access
        data_access_scope: Optional[str] = None,
        row_count: Optional[int] = None,
        # errors
        error_code: Optional[str] = None,
        error_class: Optional[str] = None,
        error_message_short: Optional[str] = None,
        # context
        current_step: Optional[str] = None,
        summary: Optional[str] = None,
        approval_required_roles: Optional[list[str]] = None,
        approval_chain: Optional[list[str]] = None,
        approver_id: Optional[str] = None,
        approval_request_id: Optional[str] = None,
        approval_latency_ms: Optional[int] = None,
        # hashes
        prompt_hash: Optional[str] = None,
        artifact_hashes: Optional[list[str]] = None,
        artifact_sensitivity: Optional[str] = None,
    ) -> None:
        """Emit a structured telemetry event.

        All fields are optional except trace_id, span_id, and event_type.
        None/empty values are stripped before logging.
        """
        payload: dict[str, Any] = {
            "trace_id": trace_id,
            "span_id": span_id,
            "parent_span_id": parent_span_id,
            "department": self.department,
            "agent_id": self.agent_id,
            "agent_role": "agent",
            "environment": self.environment,
            "event_type": event_type,
            "status": status,
            "decision": decision,
            "reason": reason,
            "risk_level": risk_level,
            "data_sensitivity": data_sensitivity,
            "requester_id": requester_id,
            "resource": resource,
            "provider": provider,
            "model": model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": cost_usd,
            "latency_ms": latency_ms,
            "artifact_ids": artifact_ids or [],
            "artifact_types": artifact_types or [],
            "artifact_hashes": artifact_hashes or [],
            "artifact_sensitivity": artifact_sensitivity,
            "tool_name": tool_name,
            "tool_risk_level": tool_risk_level,
            "tool_args_hash": tool_args_hash,
            "egress_domain": egress_domain,
            "sandbox_violation": sandbox_violation,
            "data_access_scope": data_access_scope,
            "row_count": row_count,
            "error_code": error_code,
            "error_class": error_class,
            "error_message_short": error_message_short,
            "current_step": current_step,
            "summary": summary,
            "approval_required_roles": approval_required_roles or [],
            "approval_chain": approval_chain or [],
            "approver_id": approver_id,
            "approval_request_id": approval_request_id,
            "approval_latency_ms": approval_latency_ms,
            "prompt_hash": prompt_hash,
        }

        # Strip None/empty values for cleaner logs
        clean = {k: v for k, v in payload.items() if v not in (None, "", [], {})}

        # ── DB sink (async-safe, fire-and-forget) ─────
        try:
            self._db_sink(payload)
        except Exception:
            pass  # DB failures are non-fatal; structlog is the fallback

        # ── Structlog fallback (always) ───────────────
        logger.info("telemetry_event", **clean)

    def _db_sink(self, payload: dict[str, Any]) -> None:
        """Insert audit_event + upsert trace_index.

        Uses synchronous DB session within the existing event loop.
        If the DB is unavailable, this is a no-op (swallowed above).
        """
        try:
            from app.core.deps import get_sync_session
            from app.services.audit_service import AuditService

            session = get_sync_session()
            try:
                svc = AuditService(session)
                svc.emit_sync(payload)
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        except ImportError:
            # Dependencies not available (e.g. during testing)
            pass

    def emit_lifecycle(
        self,
        event_type: str,
        ctx: Any,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """High-level convenience for agent lifecycle events.

        Bridges from ``(event_type, AgentContext, payload)`` to the
        full ``emit()`` signature.  This is the method that
        ``BaseAgent._emit_lifecycle()`` calls.
        """
        data = payload or {}
        self.emit(
            trace_id=getattr(ctx, "trace_id", None) or data.get("trace_id", ""),
            span_id=getattr(ctx, "span_id", None) or data.get("span_id", ""),
            parent_span_id=getattr(ctx, "parent_span", None),
            event_type=event_type,
            status=data.get("status"),
            latency_ms=data.get("duration_ms"),
            artifact_ids=data.get("artifact_ids"),
            summary=data.get("summary"),
            current_step=data.get("agent", self.agent_id),
        )
