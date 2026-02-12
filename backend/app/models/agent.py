"""Agent model — AI agents in the enterprise system."""

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class Agent(Base, TimestampMixin):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    department: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    tier: Mapped[str] = mapped_column(String(20), nullable=False, default="standard")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="idle")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    tools_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    paired_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )

    # ── Prompt override fields (editable via admin dashboard) ─────
    system_prompt_override: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Admin-editable override; takes precedence over hardcoded prompt",
    )
    prompt_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0",
        comment="Incremented on each prompt edit via dashboard",
    )
    prompt_updated_at: Mapped[str | None] = mapped_column(
        DateTime, nullable=True,
        comment="Timestamp of last prompt change",
    )
    prompt_updated_by: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="User who last edited the prompt",
    )

    def __repr__(self) -> str:
        return f"<Agent {self.name} ({self.department}/{self.tier})>"
