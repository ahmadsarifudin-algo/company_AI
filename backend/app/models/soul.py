"""Soul models — per-user personality configuration for AI responses."""

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, generate_uuid


class SoulTemplate(Base):
    """Preset personality templates available for all users."""

    __tablename__ = "soul_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    tone: Mapped[str] = mapped_column(String(50), nullable=False, default="friendly")
    language_style: Mapped[str] = mapped_column(String(50), nullable=False, default="auto")
    personality: Mapped[str] = mapped_column(Text, nullable=False)
    boundaries: Mapped[str | None] = mapped_column(Text, nullable=True)
    greeting: Mapped[str | None] = mapped_column(String(500), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(10), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def to_prompt(self) -> str:
        """Compile this template into a system prompt section."""
        parts = [self.personality]
        if self.boundaries:
            parts.append(f"\nBOUNDARIES:\n{self.boundaries}")
        return "\n".join(parts)


class UserSoul(Base, TimestampMixin):
    """Per-user custom or cloned personality configuration."""

    __tablename__ = "user_souls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    tone: Mapped[str] = mapped_column(String(50), nullable=False, default="friendly")
    language_style: Mapped[str] = mapped_column(String(50), nullable=False, default="auto")
    personality: Mapped[str] = mapped_column(Text, nullable=False)
    boundaries: Mapped[str | None] = mapped_column(Text, nullable=True)
    greeting: Mapped[str | None] = mapped_column(String(500), nullable=True)
    template_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("soul_templates.id", ondelete="SET NULL"), nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationships
    template = relationship("SoulTemplate", lazy="selectin")

    def to_prompt(self) -> str:
        """Compile this soul into a system prompt section."""
        parts = [self.personality]
        if self.boundaries:
            parts.append(f"\nBOUNDARIES:\n{self.boundaries}")
        return "\n".join(parts)

    def __repr__(self) -> str:
        return f"<UserSoul {self.name} (user={self.user_id}, active={self.is_active})>"
