"""Audit Event model — Expanded event-sourced immutable action log.

Replaces the original AuditLog with the full audit_events schema
for dashboard, forensics, and hash-chain verification.
"""

from sqlalchemy import Boolean, Float, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class AuditEvent(Base, TimestampMixin):
    """Immutable audit event with tamper-evident hash chain.

    Every action in the system (LLM calls, tool executions, data access,
    approvals) produces an AuditEvent entry. Entries are APPEND-ONLY —
    never updated or deleted.

    Hash chain: each event stores SHA-256 of its own fields (event_hash)
    plus the hash of the previous event in the same trace (prev_event_hash).
    """

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    # ── Correlation ──────────────────────────────
    trace_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    span_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    parent_span_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # ── Who / Where ──────────────────────────────
    department: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    agent_role: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="agent",
        comment='e.g. "agent"|"supervisor"|"admin"',
    )
    requester_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    environment: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="prod",
        comment="dev|staging|prod",
    )

    # ── What happened ────────────────────────────
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    status: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="success|failed|pending|blocked|...",
    )
    decision: Mapped[str | None] = mapped_column(
        String(50), nullable=True, index=True,
        comment="allow|deny|require_approval|...",
    )

    # ── Classification ───────────────────────────
    risk_level: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="low",
        comment="low|medium|high|critical",
    )
    data_sensitivity: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="internal",
        comment="public|internal|confidential|pii",
    )

    # ── Details ──────────────────────────────────
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_class: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message_short: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ── LLM fields ───────────────────────────────
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Tool fields ──────────────────────────────
    tool_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tool_risk_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tool_args_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    egress_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sandbox_violation: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # ── Data access fields ───────────────────────
    resource: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment='e.g. "table:employee_pii" / "tool:send_email"',
    )
    data_access_scope: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment='e.g. "employee_pii.columns:[nik,bank]"',
    )
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Approvals ────────────────────────────────
    approval_required_roles: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    approval_chain: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    approver_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approval_request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approval_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Artifacts ────────────────────────────────
    artifact_ids: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    artifact_types: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    artifact_hashes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    artifact_sensitivity: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # ── Tamper-evident audit ─────────────────────
    prev_event_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # ── Idempotency ──────────────────────────────
    idempotency_key: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True,
    )

    def __repr__(self) -> str:
        return f"<AuditEvent {self.agent_id}: {self.event_type} [{self.status}]>"


# Backward-compat alias
AuditLog = AuditEvent
