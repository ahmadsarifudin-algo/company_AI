"""PromptHistory — Audit trail for agent system prompt changes.

Every time an admin edits an agent's system prompt via the dashboard,
a snapshot is saved here for version history and rollback.
"""

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, generate_uuid


class PromptHistory(Base):
    """One row per prompt version per agent."""

    __tablename__ = "prompt_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id"), nullable=False, index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    changed_by: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="User ID or admin email who made the change",
    )
    changed_at: Mapped[str] = mapped_column(
        DateTime, nullable=False, server_default=func.now(),
    )
    change_reason: Mapped[str | None] = mapped_column(
        String(500), nullable=True,
        comment="Optional reason for the prompt change",
    )

    def __repr__(self) -> str:
        return f"<PromptHistory agent={self.agent_id} v{self.version}>"
