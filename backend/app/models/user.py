"""User model — Human employees who supervise agents."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    department: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    role: Mapped[str] = mapped_column(
        String(50), nullable=False, default="contributor",
        comment="admin|manager|lead|contributor",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)

    # Invite token (SHA-256 hash stored; raw token never persisted)
    invite_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    invite_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Communication channels ───────────────────
    phone_whatsapp: Mapped[str | None] = mapped_column(
        String(20), nullable=True,
        comment="WhatsApp number e.g. +6281234567890",
    )
    telegram_chat_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
        comment="Telegram chat ID or @username",
    )
    notification_channels: Mapped[str] = mapped_column(
        String(100), nullable=False, server_default="email",
        comment="Comma-separated: email,whatsapp,telegram",
    )

    # ── SOUL personality ─────────────────────────
    active_soul_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("user_souls.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
        comment="Active SOUL personality for chat responses",
    )

    # ── Helpers ──────────────────────────────────

    ROLE_HIERARCHY = {"admin": 4, "manager": 3, "lead": 2, "contributor": 1}

    @property
    def role_level(self) -> int:
        return self.ROLE_HIERARCHY.get(self.role, 0)

    def has_role(self, minimum: str) -> bool:
        """Check if user's role meets or exceeds the minimum required."""
        return self.role_level >= self.ROLE_HIERARCHY.get(minimum, 99)

    @property
    def status_label(self) -> str:
        if self.is_active:
            return "active"
        if self.invite_token_hash and self.invite_expires_at:
            if self.invite_expires_at > datetime.now(timezone.utc):
                return "pending_invite"
            return "invite_expired"
        return "inactive"

    def __repr__(self) -> str:
        return f"<User {self.email} ({self.department}/{self.role})>"
