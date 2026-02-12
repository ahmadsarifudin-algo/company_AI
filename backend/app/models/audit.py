"""Audit log model — Event-sourced immutable action tracking with hash chain."""

from sqlalchemy import Float, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class AuditLog(Base, TimestampMixin):
    """Immutable audit event with tamper-evident hash chain.

    Every action in the system (LLM calls, tool executions, data access,
    approvals) produces an AuditLog entry. Entries are APPEND-ONLY —
    never updated or deleted.

    Hash chain: each event stores SHA-256 of its own fields (event_hash)
    plus the hash of the previous event in the same trace (prev_event_hash).
    This creates a tamper-evident linked list per workflow trace.
    """

    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    department: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    agent_name: Mapped[str] = mapped_column(String(255), nullable=False)
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_scope: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_chain: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    execution_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── Event-sourcing fields (Module 4) ──────────
    event_type: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True,
        comment="llm_call | tool_call | data_read | data_write | approval_requested | ..."
    )
    trace_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True,
        comment="Workflow-scoped trace ID for correlation"
    )
    span_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True,
        comment="Step-scoped span ID within the trace"
    )
    prompt_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
        comment="SHA-256 hash of the LLM prompt"
    )
    tool_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="Tool that was called (if action is tool_call)"
    )
    tool_args_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
        comment="SHA-256 hash of tool arguments"
    )
    data_access_scope: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Resource + filters for data access events"
    )
    approver_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True,
        comment="User who approved (for approval events)"
    )
    artifact_ids: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="List of artifact IDs produced by this event"
    )
    idempotency_key: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True,
        comment="trace_id:step_id for idempotency enforcement"
    )

    # ── Hash chain fields ─────────────────────────
    event_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
        comment="SHA-256 of canonical JSON of this event's fields"
    )
    prev_event_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
        comment="Hash of the previous event in the same trace (chain link)"
    )

    def __repr__(self) -> str:
        return f"<AuditLog {self.agent_name}: {self.action_type} [{self.event_type}]>"
