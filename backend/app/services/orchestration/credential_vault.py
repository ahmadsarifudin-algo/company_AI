"""
CredentialVault — Secure storage and retrieval of integration credentials.

Stores API keys, service account files, and tokens in the database (encrypted).
Only ToolBroker and orchestration services can access credentials.
Agents never have direct access to credential values.
"""

import json
from typing import Any

import structlog

from app.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


class CredentialVault:
    """Secure credential storage for integrations.

    Credentials are stored in the database `integration_credentials` table.
    In-memory cache (per-process) avoids repeated DB lookups.

    Usage:
        vault = CredentialVault()
        await vault.load(db_session)
        gmail_creds = vault.get("google_service_account")
    """

    _cache: dict[str, Any] = {}
    _loaded: bool = False

    @classmethod
    async def load(cls, db=None) -> None:
        """Load credentials from database into memory cache.

        Falls back to environment variables if DB is not available.
        """
        # Phase 1: Load from environment variables (config.py)
        cls._cache = {
            # SMTP
            "smtp_host": settings.SMTP_HOST,
            "smtp_port": settings.SMTP_PORT,
            "smtp_user": settings.SMTP_USER,
            "smtp_password": settings.SMTP_PASSWORD,
            "smtp_from": settings.SMTP_FROM,
            "smtp_use_tls": settings.SMTP_USE_TLS,
            # Twilio WhatsApp
            "twilio_account_sid": settings.TWILIO_ACCOUNT_SID,
            "twilio_auth_token": settings.TWILIO_AUTH_TOKEN,
            "twilio_whatsapp_from": settings.TWILIO_WHATSAPP_FROM,
            # Telegram
            "telegram_bot_token": settings.TELEGRAM_BOT_TOKEN,
            "telegram_webhook_secret": settings.TELEGRAM_WEBHOOK_SECRET,
            # Google Workspace
            "google_service_account_json": settings.GOOGLE_SERVICE_ACCOUNT_JSON,
            "google_delegated_email": settings.GOOGLE_DELEGATED_EMAIL,
            "google_calendar_id": settings.GOOGLE_CALENDAR_ID,
            "google_drive_folder_id": settings.GOOGLE_DRIVE_FOLDER_ID,
            # Channels
            "notification_channels": settings.NOTIFICATION_CHANNELS,
            "callback_base_url": settings.CHANNEL_CALLBACK_BASE_URL,
            "allowed_email_domains": settings.ALLOWED_EMAIL_DOMAINS,
        }

        # Phase 2: Override with DB-stored credentials if available
        if db is not None:
            try:
                from sqlalchemy import text
                result = await db.execute(
                    text("SELECT key, value FROM integration_credentials WHERE is_active = true")
                )
                for row in result.fetchall():
                    cls._cache[row[0]] = row[1]
                logger.info("credential_vault_loaded_from_db", count=result.rowcount)
            except Exception as e:
                logger.warning("credential_vault_db_fallback", error=str(e))

        cls._loaded = True
        logger.info("credential_vault_loaded", source_count=len(cls._cache))

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        """Get a credential by key."""
        if not cls._loaded:
            # Auto-load from env if not yet loaded
            cls._cache = {
                "smtp_host": settings.SMTP_HOST,
                "smtp_port": settings.SMTP_PORT,
                "smtp_user": settings.SMTP_USER,
                "smtp_password": settings.SMTP_PASSWORD,
                "smtp_from": settings.SMTP_FROM,
                "smtp_use_tls": settings.SMTP_USE_TLS,
                "twilio_account_sid": settings.TWILIO_ACCOUNT_SID,
                "twilio_auth_token": settings.TWILIO_AUTH_TOKEN,
                "twilio_whatsapp_from": settings.TWILIO_WHATSAPP_FROM,
                "telegram_bot_token": settings.TELEGRAM_BOT_TOKEN,
                "telegram_webhook_secret": settings.TELEGRAM_WEBHOOK_SECRET,
                "google_service_account_json": settings.GOOGLE_SERVICE_ACCOUNT_JSON,
                "google_delegated_email": settings.GOOGLE_DELEGATED_EMAIL,
                "google_calendar_id": settings.GOOGLE_CALENDAR_ID,
                "google_drive_folder_id": settings.GOOGLE_DRIVE_FOLDER_ID,
                "notification_channels": settings.NOTIFICATION_CHANNELS,
                "callback_base_url": settings.CHANNEL_CALLBACK_BASE_URL,
                "allowed_email_domains": settings.ALLOWED_EMAIL_DOMAINS,
            }
            cls._loaded = True
        return cls._cache.get(key, default)

    @classmethod
    def get_google_credentials(cls) -> dict:
        """Get Google service account credentials as a dict."""
        json_path = cls.get("google_service_account_json", "")
        if not json_path:
            return {}
        try:
            with open(json_path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error("google_credentials_load_error", error=str(e))
            return {}

    @classmethod
    def is_configured(cls, service: str) -> bool:
        """Check if a service has minimum required credentials.

        Args:
            service: One of "smtp", "twilio", "google", "google_calendar",
                     "google_drive", "google_gmail".

        Returns:
            True if the service has enough config to function.
        """
        checks = {
            "smtp": lambda: bool(cls.get("smtp_host") and cls.get("smtp_user")),
            "twilio": lambda: bool(
                cls.get("twilio_account_sid") and cls.get("twilio_auth_token")
            ),
            "telegram": lambda: bool(cls.get("telegram_bot_token")),
            "google": lambda: bool(cls.get("google_service_account_json")),
            "google_calendar": lambda: bool(
                cls.get("google_service_account_json") and cls.get("google_calendar_id")
            ),
            "google_drive": lambda: bool(
                cls.get("google_service_account_json") and cls.get("google_drive_folder_id")
            ),
            "google_gmail": lambda: bool(
                cls.get("google_service_account_json") and cls.get("google_delegated_email")
            ),
        }
        checker = checks.get(service)
        if checker is None:
            return False
        return checker()

    @classmethod
    async def set(cls, key: str, value: str, db=None) -> None:
        """Set a credential value (updates cache and optionally DB).

        Args:
            key: Credential key.
            value: Credential value.
            db: Optional database session to persist.
        """
        cls._cache[key] = value

        if db is not None:
            try:
                from sqlalchemy import text
                await db.execute(
                    text(
                        "INSERT INTO integration_credentials (key, value, is_active) "
                        "VALUES (:key, :value, true) "
                        "ON CONFLICT (key) DO UPDATE SET value = :value"
                    ),
                    {"key": key, "value": value},
                )
                await db.commit()
                logger.info("credential_vault_saved", key=key)
            except Exception as e:
                logger.error("credential_vault_save_error", key=key, error=str(e))

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the in-memory cache. For testing."""
        cls._cache.clear()
        cls._loaded = False
