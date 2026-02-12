"""IntegrationCredential model — stores API keys and service config."""

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class IntegrationCredential(Base, TimestampMixin):
    """Stores integration credentials set via Settings panel.

    Values are stored as plain text in DB; production deployments
    should encrypt at-rest via pgcrypto or application-layer encryption.
    """

    __tablename__ = "integration_credentials"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    service: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True,
        comment="google|twilio|smtp",
    )
    is_secret: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    def __repr__(self) -> str:
        return f"<IntegrationCredential {self.key} ({self.service})>"
