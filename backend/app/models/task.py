"""Task model — Work items submitted to agents."""

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    department: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending, running, waiting_approval, completed, failed
    priority: Mapped[str] = mapped_column(String(5), nullable=False, default="P2")
    plan_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    assigned_agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agents.id"), nullable=True
    )
    submitted_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )

    # ── Chat-originated task fields ──────────
    channel: Mapped[str | None] = mapped_column(
        String(20), nullable=True, index=True
    )  # telegram, whatsapp, email, dashboard
    sender_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sender_identifier: Mapped[str | None] = mapped_column(String(200), nullable=True)
    agent_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    original_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<Task {self.title[:30]} ({self.status})>"
