"""Trace Index model — 1 row per trace for fast dashboard queries.

Purpose: enable fast filtering/sorting of traces without scanning
the full audit_events table. Updated via UPSERT on every event emission.
"""

from sqlalchemy import Boolean, Integer, Numeric, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import func
from datetime import datetime


from app.models.base import Base


class TraceIndex(Base):
    """One row per workflow trace — updated via UPSERT on each event.

    Provides the fast-query layer for:
    - GET /admin/dashboard  (status counts, cost, approval backlog)
    - GET /admin/traces     (filterable trace list)
    - GET /admin/approvals  (pending approvals queue)
    """

    __tablename__ = "trace_index"

    trace_id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # ── Identity ─────────────────────────────────
    department: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    requester_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    environment: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="prod",
    )

    # ── Lifecycle ────────────────────────────────
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    last_event_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="running", index=True,
        comment="running|needs_approval|completed|failed|blocked",
    )
    current_step: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_agent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_event_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_error_message_short: Mapped[str | None] = mapped_column(
        String(500), nullable=True,
    )

    # ── Rollup metrics ───────────────────────────
    risk_level: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="low",
    )
    data_sensitivity: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="internal",
    )
    total_cost_usd: Mapped[float] = mapped_column(
        Numeric(12, 6), nullable=False, server_default="0",
    )
    total_tokens_in: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0",
    )
    total_tokens_out: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0",
    )
    tool_calls: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0",
    )
    denied_calls: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0",
    )
    approval_pending: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", index=True,
    )
    approval_decision: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="approved|rejected",
    )
    approved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # ── Integrity ────────────────────────────────
    audit_chain_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    audit_chain_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # ── Search ───────────────────────────────────
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<TraceIndex {self.trace_id}: {self.status}>"
