"""
Telegram Tool — Send messages via Telegram Bot API.

Registered as `send_telegram` in the ToolRegistry.
Risk: HIGH — requires human approval before sending.
"""

from typing import Any

import structlog

from app.services.orchestration.credential_vault import CredentialVault

logger = structlog.get_logger()


async def send_telegram_handler(
    chat_id: str,
    message: str,
    parse_mode: str = "",
    photo_url: str = "",
) -> dict[str, Any]:
    """Send a Telegram message via Bot API.

    Args:
        chat_id: Target chat ID or @channel_username.
        message: Message text.
        parse_mode: Optional "HTML" or "Markdown".
        photo_url: Optional photo URL to send with caption.

    Returns:
        Dict with status, message_id, and chat info.
    """
    if not CredentialVault.is_configured("telegram"):
        return {"status": "error", "error": "Telegram bot not configured"}

    bot_token = CredentialVault.get("telegram_bot_token")
    base_url = f"https://api.telegram.org/bot{bot_token}"

    try:
        import httpx

        async with httpx.AsyncClient(timeout=15) as client:
            if photo_url:
                # Send photo with caption
                payload: dict[str, Any] = {
                    "chat_id": chat_id,
                    "photo": photo_url,
                    "caption": message,
                }
                if parse_mode:
                    payload["parse_mode"] = parse_mode
                resp = await client.post(f"{base_url}/sendPhoto", json=payload)
            else:
                # Send text message
                payload = {
                    "chat_id": chat_id,
                    "text": message,
                }
                if parse_mode:
                    payload["parse_mode"] = parse_mode
                resp = await client.post(f"{base_url}/sendMessage", json=payload)

            data = resp.json()

            if not data.get("ok"):
                error_desc = data.get("description", "Unknown error")
                logger.error("telegram_send_error", chat_id=chat_id, error=error_desc)
                return {"status": "error", "error": error_desc}

            result_msg = data.get("result", {})
            logger.info(
                "telegram_sent",
                chat_id=chat_id,
                message_id=result_msg.get("message_id"),
            )

            return {
                "status": "sent",
                "message_id": result_msg.get("message_id"),
                "chat_id": chat_id,
            }

    except ImportError:
        return {"status": "error", "error": "httpx package not installed"}
    except Exception as e:
        logger.error("telegram_send_error", chat_id=chat_id, error=str(e))
        return {"status": "error", "error": str(e)}
