"""
NotificationDispatcher — Sends agent responses back to users.

Routes outbound messages to the correct channel (WhatsApp, Email,
Dashboard) based on the original inbound channel or user preferences.
"""

import structlog

from app.core.config import get_settings
from app.services.orchestration.credential_vault import CredentialVault

logger = structlog.get_logger()
settings = get_settings()


class NotificationDispatcher:
    """Sends responses back to users via their preferred channel.

    Channel selection priority:
    1. Reply via same channel as inbound message
    2. User's notification_channels preference
    3. Email (default fallback)
    """

    @classmethod
    async def send(
        cls,
        channel: str,
        recipient: str,
        content: str,
        subject: str = "",
        attachments: list[str] | None = None,
        trace_id: str = "",
        task_id: str = "",
    ) -> dict:
        """Send a message via the specified channel.

        Args:
            channel: "whatsapp" | "email" | "dashboard" | "google_chat"
            recipient: Phone number, email, or user ID.
            content: Message body.
            subject: Email subject (email only).
            attachments: File paths or URLs.
            trace_id: For correlation.
            task_id: For correlation.

        Returns:
            Dict with status and external message ID.
        """
        handlers = {
            "whatsapp": cls._send_whatsapp,
            "email": cls._send_email,
            "dashboard": cls._send_dashboard,
            "google_chat": cls._send_google_chat,
        }

        handler = handlers.get(channel)
        if handler is None:
            logger.warning("dispatcher_unknown_channel", channel=channel)
            return {"status": "error", "error": f"Unknown channel: {channel}"}

        try:
            result = await handler(
                recipient=recipient,
                content=content,
                subject=subject,
                attachments=attachments or [],
            )
            logger.info(
                "dispatcher_sent",
                channel=channel,
                recipient=recipient,
                trace_id=trace_id,
                status=result.get("status", "unknown"),
            )
            return result

        except Exception as e:
            logger.error(
                "dispatcher_error",
                channel=channel,
                recipient=recipient,
                error=str(e),
            )
            return {"status": "failed", "error": str(e)}

    @classmethod
    async def _send_whatsapp(
        cls,
        recipient: str,
        content: str,
        subject: str = "",
        attachments: list[str] | None = None,
    ) -> dict:
        """Send WhatsApp message via Twilio."""
        if not CredentialVault.is_configured("twilio"):
            return {"status": "skipped", "reason": "Twilio not configured"}

        # Actual Twilio implementation
        account_sid = CredentialVault.get("twilio_account_sid")
        auth_token = CredentialVault.get("twilio_auth_token")
        from_number = CredentialVault.get("twilio_whatsapp_from")

        try:
            from twilio.rest import Client
            client = Client(account_sid, auth_token)
            message = client.messages.create(
                body=content,
                from_=f"whatsapp:{from_number}",
                to=f"whatsapp:{recipient}",
            )
            return {"status": "sent", "sid": message.sid}
        except ImportError:
            logger.warning("twilio_not_installed")
            return {"status": "skipped", "reason": "twilio package not installed"}

    @classmethod
    async def _send_email(
        cls,
        recipient: str,
        content: str,
        subject: str = "",
        attachments: list[str] | None = None,
    ) -> dict:
        """Send email via SMTP or Gmail API."""
        if CredentialVault.is_configured("google_gmail"):
            return await cls._send_gmail(recipient, content, subject, attachments)

        if CredentialVault.is_configured("smtp"):
            return await cls._send_smtp(recipient, content, subject)

        return {"status": "skipped", "reason": "No email service configured"}

    @classmethod
    async def _send_gmail(
        cls,
        recipient: str,
        content: str,
        subject: str = "",
        attachments: list[str] | None = None,
    ) -> dict:
        """Send email via Gmail API with service account."""
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
            import base64
            from email.mime.text import MIMEText

            creds_dict = CredentialVault.get_google_credentials()
            if not creds_dict:
                return {"status": "failed", "error": "Invalid Google credentials"}

            delegated_email = CredentialVault.get("google_delegated_email")
            credentials = service_account.Credentials.from_service_account_info(
                creds_dict,
                scopes=["https://www.googleapis.com/auth/gmail.send"],
                subject=delegated_email,
            )

            service = build("gmail", "v1", credentials=credentials)

            message = MIMEText(content)
            message["to"] = recipient
            message["from"] = delegated_email
            message["subject"] = subject or "Agent Response"

            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            result = service.users().messages().send(
                userId="me",
                body={"raw": raw},
            ).execute()

            return {"status": "sent", "message_id": result.get("id", "")}

        except ImportError:
            logger.warning("google_api_not_installed")
            return {"status": "skipped", "reason": "google-api-python-client not installed"}

    @classmethod
    async def _send_smtp(
        cls,
        recipient: str,
        content: str,
        subject: str = "",
    ) -> dict:
        """Send email via SMTP."""
        try:
            import aiosmtplib
            from email.mime.text import MIMEText

            msg = MIMEText(content)
            msg["Subject"] = subject or "Agent Response"
            msg["From"] = CredentialVault.get("smtp_from")
            msg["To"] = recipient

            await aiosmtplib.send(
                msg,
                hostname=CredentialVault.get("smtp_host"),
                port=CredentialVault.get("smtp_port"),
                username=CredentialVault.get("smtp_user"),
                password=CredentialVault.get("smtp_password"),
                use_tls=CredentialVault.get("smtp_use_tls", True),
            )
            return {"status": "sent"}

        except ImportError:
            logger.warning("aiosmtplib_not_installed")
            return {"status": "skipped", "reason": "aiosmtplib not installed"}

    @classmethod
    async def _send_dashboard(
        cls,
        recipient: str,
        content: str,
        subject: str = "",
        attachments: list[str] | None = None,
    ) -> dict:
        """Push response to dashboard via WebSocket / Redis pub-sub."""
        # TODO: Implement Redis pub-sub for real-time dashboard updates
        logger.info("dispatcher_dashboard", recipient=recipient, content_len=len(content))
        return {"status": "sent", "method": "dashboard"}

    @classmethod
    async def _send_google_chat(
        cls,
        recipient: str,
        content: str,
        subject: str = "",
        attachments: list[str] | None = None,
    ) -> dict:
        """Send message to Google Chat space."""
        if not CredentialVault.is_configured("google"):
            return {"status": "skipped", "reason": "Google not configured"}

        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            creds_dict = CredentialVault.get_google_credentials()
            credentials = service_account.Credentials.from_service_account_info(
                creds_dict,
                scopes=["https://www.googleapis.com/auth/chat.bot"],
            )
            service = build("chat", "v1", credentials=credentials)

            result = service.spaces().messages().create(
                parent=recipient,  # spaces/{space_id}
                body={"text": content},
            ).execute()

            return {"status": "sent", "message_name": result.get("name", "")}

        except ImportError:
            logger.warning("google_chat_api_not_installed")
            return {"status": "skipped", "reason": "google-api-python-client not installed"}
