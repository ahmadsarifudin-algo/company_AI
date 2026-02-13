"""
Telegram Long Polling — Receives messages without a public URL.

Inspired by OpenClaw's grammY runner approach. Uses Telegram Bot API
`getUpdates` with long polling instead of webhooks.

Usage:
    poller = TelegramPoller(bot_token="123:abc")
    await poller.start()   # runs in background
    await poller.stop()    # graceful shutdown
"""

import asyncio
from datetime import datetime, timezone

import httpx
import structlog

from app.services.orchestration.credential_vault import CredentialVault
from app.services.orchestration.message_gateway import MessageGateway
from app.services.orchestration.task_orchestrator import TaskOrchestrator

logger = structlog.get_logger()

# ── Telegram Bot API helpers ──────────────────────────────────

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"

CHAT_COMMANDS = {
    "/status": "📊 **Status**\n• Bot: online\n• Uptime: {uptime}\n• Mode: polling",
    "/help": (
        "🤖 **Available Commands**\n\n"
        "/status — Bot status & uptime\n"
        "/help — This help message\n"
        "/reset — Reset conversation context\n\n"
        "Or just send any message to chat with the AI assistant."
    ),
    "/reset": "🔄 Conversation context has been reset.",
}


class TelegramPoller:
    """Long-polling worker for Telegram Bot API.

    Continuously calls getUpdates to receive new messages,
    routes them through MessageGateway → TaskOrchestrator,
    and sends typing indicators while the LLM processes.
    """

    def __init__(self) -> None:
        self._offset: int = 0
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._started_at: datetime | None = None
        self._poll_timeout: int = 30  # seconds (Telegram long-poll)
        self._error_backoff: float = 5.0  # seconds between retries on error

    # ── Public API ─────────────────────────────────────────────

    async def start(self) -> None:
        """Start the polling loop as a background task."""
        token = self._get_token()
        if not token:
            logger.warning("telegram_poller_skip", reason="no bot token configured")
            return

        # Delete webhook first so polling works
        await self._delete_webhook(token)

        self._started_at = datetime.now(timezone.utc)
        self._stop_event.clear()
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("telegram_poller_started")

    async def stop(self) -> None:
        """Gracefully stop the polling loop."""
        if self._task and not self._task.done():
            self._stop_event.set()
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            logger.info("telegram_poller_stopped")

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    # ── Core polling loop ──────────────────────────────────────

    async def _poll_loop(self) -> None:
        """Main loop: call getUpdates, process each update."""
        token = self._get_token()
        if not token:
            return

        while not self._stop_event.is_set():
            try:
                updates = await self._get_updates(token)
                for update in updates:
                    await self._handle_update(update, token)
            except asyncio.CancelledError:
                break
            except httpx.TimeoutException:
                # Normal for long-polling — Telegram returns empty after timeout
                continue
            except Exception as e:
                logger.error("telegram_poller_error", error=str(e))
                await asyncio.sleep(self._error_backoff)

    async def _get_updates(self, token: str) -> list[dict]:
        """Call Telegram getUpdates with long polling."""
        url = TELEGRAM_API.format(token=token, method="getUpdates")
        params: dict = {
            "timeout": self._poll_timeout,
            "allowed_updates": '["message"]',
        }
        if self._offset:
            params["offset"] = self._offset

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                params=params,
                timeout=self._poll_timeout + 10,  # HTTP timeout > poll timeout
            )
            data = resp.json()

        if not data.get("ok"):
            logger.error("telegram_getUpdates_failed", response=data)
            return []

        return data.get("result", [])

    # ── Update handling ────────────────────────────────────────

    async def _handle_update(self, update: dict, token: str) -> None:
        """Process a single Telegram Update object."""
        # Track offset for reliable delivery
        update_id = update.get("update_id", 0)
        if update_id >= self._offset:
            self._offset = update_id + 1

        # Only handle message updates
        message = update.get("message")
        if not message:
            return

        text = message.get("text", "").strip()
        chat_id = str(message.get("chat", {}).get("id", ""))

        if not text or not chat_id:
            return

        # ── Handle chat commands ──────────────────────────────
        command = text.split()[0].lower().split("@")[0]  # strip @botname
        if command in CHAT_COMMANDS:
            reply = CHAT_COMMANDS[command]
            if command == "/status":
                uptime = self._format_uptime()
                reply = reply.format(uptime=uptime)
            await self._send_message(token, chat_id, reply)
            logger.info("telegram_command", command=command, chat_id=chat_id)
            return

        # ── Process normal message ───────────────────────────
        # Send typing indicator immediately
        await self._send_typing(token, chat_id)

        # Normalize via MessageGateway
        unified = MessageGateway.from_telegram({"message": message})

        # Submit to orchestrator (this calls LLM and dispatches reply)
        try:
            task = await TaskOrchestrator.submit(unified)
            logger.info(
                "telegram_poller_submitted",
                task_id=task.task_id,
                agent=task.routing.agent,
                chat_id=chat_id,
            )
        except Exception as e:
            logger.error("telegram_poller_submit_error", error=str(e), chat_id=chat_id)
            await self._send_message(
                token,
                chat_id,
                "⚠️ Sorry, I encountered an error processing your message. Please try again.",
            )

    # ── Telegram API methods ──────────────────────────────────

    async def _send_typing(self, token: str, chat_id: str) -> None:
        """Send 'typing...' indicator to the user."""
        url = TELEGRAM_API.format(token=token, method="sendChatAction")
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    url,
                    json={"chat_id": chat_id, "action": "typing"},
                    timeout=5,
                )
        except Exception:
            pass  # Non-critical

    async def _send_message(self, token: str, chat_id: str, text: str) -> None:
        """Send a text message to a Telegram chat."""
        url = TELEGRAM_API.format(token=token, method="sendMessage")
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    url,
                    json={
                        "chat_id": chat_id,
                        "text": text,
                        "parse_mode": "Markdown",
                    },
                    timeout=10,
                )
        except Exception as e:
            logger.error("telegram_send_failed", error=str(e), chat_id=chat_id)

    async def _delete_webhook(self, token: str) -> None:
        """Remove any existing webhook so polling works."""
        url = TELEGRAM_API.format(token=token, method="deleteWebhook")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, timeout=10)
                logger.info("telegram_webhook_deleted", response=resp.json())
        except Exception as e:
            logger.warning("telegram_delete_webhook_failed", error=str(e))

    # ── Helpers ────────────────────────────────────────────────

    @staticmethod
    def _get_token() -> str:
        """Get bot token from CredentialVault."""
        return CredentialVault.get("telegram_bot_token") or ""

    def _format_uptime(self) -> str:
        """Format uptime as human-readable string."""
        if not self._started_at:
            return "unknown"
        delta = datetime.now(timezone.utc) - self._started_at
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m {seconds}s"


# ── Singleton instance ─────────────────────────────────────────
telegram_poller = TelegramPoller()
