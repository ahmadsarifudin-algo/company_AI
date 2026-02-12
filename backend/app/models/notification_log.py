"""NotificationLog model — tracks every notification sent by agents."""

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class NotificationLog(Base, TimestampMixin):
    """Tracks every outbound notification sent through channels.

    Used for audit, delivery tracking, and linking replies
    back to the original message context.
    """

    __tablename__ = "notification_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)

    # ── Correlation ──────────────────────────
    trace_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    # ── Channel ──────────────────────────────
    channel: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True,
        comment="email|whatsapp|dashboard|google_chat",
    )
    direction: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="outbound",
        comment="inbound|outbound",
    )

    # ── Message ──────────────────────────────
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body_preview: Mapped[str | None] = mapped_column(String(500), nullable=True)
    template: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="approval_request|task_report|feedback|general",
    )

    # ── Delivery ─────────────────────────────
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="queued",
        comment="queued|sent|delivered|failed|replied",
    )
    external_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Twilio SID / Gmail message ID / etc.",
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Reply tracking ───────────────────────
    replied_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reply_content: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Metrics ──────────────────────────────
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    def __repr__(self) -> str:
        return f"<NotificationLog {self.channel}:{self.status} → {self.recipient}>"
