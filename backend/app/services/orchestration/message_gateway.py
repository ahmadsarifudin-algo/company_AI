"""
MessageGateway — Normalizes inbound messages from all channels.

Converts WhatsApp webhooks, Email payloads, and dashboard API calls
into a unified UnifiedMessage format for processing.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import structlog

logger = structlog.get_logger()


@dataclass
class UnifiedMessage:
    """Channel-agnostic message format.

    All inbound messages (WhatsApp, Email, Dashboard) are converted
    to this format before routing to IntentRouter.
    """

    id: str
    channel: str  # "whatsapp" | "email" | "dashboard"
    sender: str  # email or phone number
    sender_name: str = ""
    content: str = ""
    subject: str = ""  # email subject or empty
    attachments: list[str] = field(default_factory=list)
    reply_to_trace: str = ""  # if continuing a conversation
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class MessageGateway:
    """Inbound message handler.

    Receives raw payloads from channel webhooks and normalizes them
    into UnifiedMessage format.

    Usage:
        gw = MessageGateway()
        msg = gw.from_whatsapp(twilio_payload)
        msg = gw.from_email(gmail_payload)
        msg = gw.from_dashboard(api_request)
    """

    @staticmethod
    def from_whatsapp(payload: dict) -> UnifiedMessage:
        """Parse incoming Twilio WhatsApp webhook payload."""
        msg = UnifiedMessage(
            id=f"msg_{uuid4().hex[:12]}",
            channel="whatsapp",
            sender=payload.get("From", "").replace("whatsapp:", ""),
            sender_name=payload.get("ProfileName", ""),
            content=payload.get("Body", ""),
            attachments=[
                payload[f"MediaUrl{i}"]
                for i in range(int(payload.get("NumMedia", 0)))
                if f"MediaUrl{i}" in payload
            ],
            metadata={
                "twilio_sid": payload.get("MessageSid", ""),
                "wa_id": payload.get("WaId", ""),
            },
        )
        logger.info(
            "gateway_whatsapp_received",
            msg_id=msg.id,
            sender=msg.sender,
            content_len=len(msg.content),
        )
        return msg

    @staticmethod
    def from_email(payload: dict) -> UnifiedMessage:
        """Parse incoming email (Gmail push notification or parsed format).

        Args:
            payload: Dict with keys: from, subject, body, attachments, message_id
        """
        msg = UnifiedMessage(
            id=f"msg_{uuid4().hex[:12]}",
            channel="email",
            sender=payload.get("from", ""),
            sender_name=payload.get("from_name", ""),
            content=payload.get("body", ""),
            subject=payload.get("subject", ""),
            attachments=payload.get("attachments", []),
            metadata={
                "message_id": payload.get("message_id", ""),
                "thread_id": payload.get("thread_id", ""),
                "in_reply_to": payload.get("in_reply_to", ""),
            },
        )

        # Check if this is a reply to an existing trace
        if payload.get("in_reply_to"):
            msg.reply_to_trace = payload.get("trace_id", "")

        logger.info(
            "gateway_email_received",
            msg_id=msg.id,
            sender=msg.sender,
            subject=msg.subject,
        )
        return msg

    @staticmethod
    def from_dashboard(
        user_email: str,
        user_name: str,
        content: str,
        trace_id: str = "",
        attachments: list[str] | None = None,
    ) -> UnifiedMessage:
        """Create message from dashboard / API request."""
        msg = UnifiedMessage(
            id=f"msg_{uuid4().hex[:12]}",
            channel="dashboard",
            sender=user_email,
            sender_name=user_name,
            content=content,
            reply_to_trace=trace_id,
            attachments=attachments or [],
        )
        logger.info(
            "gateway_dashboard_received",
            msg_id=msg.id,
            sender=msg.sender,
            content_len=len(msg.content),
        )
        return msg

    @staticmethod
    def from_telegram(payload: dict) -> UnifiedMessage:
        """Parse incoming Telegram Bot API Update payload.

        Args:
            payload: Telegram Update object with 'message' key.
        """
        tg_message = payload.get("message", {})
        from_user = tg_message.get("from", {})
        chat = tg_message.get("chat", {})

        # Collect photo/document attachments
        attachments: list[str] = []
        if tg_message.get("photo"):
            # Telegram sends array of photo sizes, take largest
            largest = tg_message["photo"][-1]
            attachments.append(f"tg_file:{largest.get('file_id', '')}")
        if tg_message.get("document"):
            attachments.append(f"tg_file:{tg_message['document'].get('file_id', '')}")

        msg = UnifiedMessage(
            id=f"msg_{uuid4().hex[:12]}",
            channel="telegram",
            sender=str(chat.get("id", "")),
            sender_name=(
                f"{from_user.get('first_name', '')} {from_user.get('last_name', '')}".strip()
                or from_user.get("username", "")
            ),
            content=tg_message.get("text", tg_message.get("caption", "")),
            attachments=attachments,
            metadata={
                "telegram_message_id": tg_message.get("message_id", ""),
                "telegram_chat_type": chat.get("type", ""),
                "telegram_user_id": from_user.get("id", ""),
                "telegram_username": from_user.get("username", ""),
            },
        )
        logger.info(
            "gateway_telegram_received",
            msg_id=msg.id,
            sender=msg.sender,
            content_len=len(msg.content),
        )
        return msg

