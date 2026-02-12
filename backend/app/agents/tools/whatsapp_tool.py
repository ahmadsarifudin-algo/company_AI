"""
WhatsApp Tool — Send messages via Twilio WhatsApp API.

Registered as `send_whatsapp` in the ToolRegistry.
Risk: HIGH — requires human approval before sending.
"""

from typing import Any

import structlog

from app.services.orchestration.credential_vault import CredentialVault

logger = structlog.get_logger()


async def send_whatsapp_handler(
    to: str,
    message: str,
    media_url: str = "",
) -> dict[str, Any]:
    """Send a WhatsApp message via Twilio.

    Args:
        to: Recipient phone number (e.g. "+6281234567890").
        message: Message text.
        media_url: Optional URL to media attachment.

    Returns:
        Dict with status, Twilio SID, and delivery info.
    """
    if not CredentialVault.is_configured("twilio"):
        return {"status": "error", "error": "Twilio not configured"}

    account_sid = CredentialVault.get("twilio_account_sid")
    auth_token = CredentialVault.get("twilio_auth_token")
    from_number = CredentialVault.get("twilio_whatsapp_from")

    try:
        from twilio.rest import Client

        client = Client(account_sid, auth_token)

        kwargs: dict[str, Any] = {
            "body": message,
            "from_": f"whatsapp:{from_number}",
            "to": f"whatsapp:{to}",
        }

        if media_url:
            kwargs["media_url"] = [media_url]

        tw_message = client.messages.create(**kwargs)

        logger.info(
            "whatsapp_sent",
            to=to,
            sid=tw_message.sid,
            status=tw_message.status,
        )

        return {
            "status": "sent",
            "sid": tw_message.sid,
            "to": to,
            "message_status": tw_message.status,
        }

    except ImportError:
        return {"status": "error", "error": "twilio package not installed"}
    except Exception as e:
        logger.error("whatsapp_send_error", to=to, error=str(e))
        return {"status": "error", "error": str(e)}
