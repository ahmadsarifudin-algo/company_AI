"""
EmailPoller — IMAP-based inbound email processing.

Polls an IMAP mailbox for new messages and routes them through
the orchestrator. Works with any IMAP provider (Gmail, Outlook, etc.).

Inspired by OpenClaw's email channel:
  - History-based new email detection (only process unseen)
  - Parse → UnifiedMessage normalization
  - Hook into gateway → orchestrator

Config (via CredentialVault):
  imap_host:     IMAP server host
  imap_port:     IMAP port (default: 993)
  imap_user:     Email address / username
  imap_password: App password or OAuth token
"""

from __future__ import annotations

import asyncio
import email
import imaplib
from datetime import datetime, timezone
from email.header import decode_header

import structlog

from app.services.orchestration.credential_vault import CredentialVault

logger = structlog.get_logger()

# Poll interval in seconds
POLL_INTERVAL = 60  # Every 60 seconds


class EmailPoller:
    """Polls IMAP mailbox for new emails and routes to orchestrator."""

    def __init__(self):
        self._task: asyncio.Task | None = None
        self.is_running = False
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        """Start the email polling loop."""
        if not self._is_configured():
            logger.info("email_poller_skipped", reason="IMAP not configured")
            return

        self._stop_event.clear()
        self._task = asyncio.create_task(self._poll_loop())
        self.is_running = True
        logger.info("email_poller_started")

    async def stop(self) -> None:
        """Stop the polling loop."""
        if not self.is_running:
            return
        self._stop_event.set()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.is_running = False
        logger.info("email_poller_stopped")

    def _is_configured(self) -> bool:
        """Check if IMAP credentials are available."""
        return bool(
            CredentialVault.get("imap_host")
            and CredentialVault.get("imap_user")
            and CredentialVault.get("imap_password")
        )

    async def _poll_loop(self) -> None:
        """Main polling loop."""
        while not self._stop_event.is_set():
            try:
                # Run IMAP operations in thread pool (imaplib is blocking)
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._check_mailbox)
            except Exception as e:
                logger.error("email_poll_error", error=str(e))

            # Wait for next poll or stop signal
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=POLL_INTERVAL,
                )
                break  # Stop event was set
            except asyncio.TimeoutError:
                pass  # Continue polling

    def _check_mailbox(self) -> None:
        """Check for new (unseen) emails via IMAP."""
        host = CredentialVault.get("imap_host")
        port = int(CredentialVault.get("imap_port") or "993")
        user = CredentialVault.get("imap_user")
        password = CredentialVault.get("imap_password")

        if not all([host, user, password]):
            return

        try:
            # Connect to IMAP server
            mail = imaplib.IMAP4_SSL(host, port)
            mail.login(user, password)
            mail.select("INBOX")

            # Search for unseen messages
            status, data = mail.search(None, "UNSEEN")
            if status != "OK" or not data[0]:
                mail.logout()
                return

            email_ids = data[0].split()
            logger.info("email_new_messages", count=len(email_ids))

            for email_id in email_ids:
                try:
                    self._process_email(mail, email_id)
                except Exception as e:
                    logger.error("email_process_error", email_id=email_id, error=str(e))

            mail.logout()

        except imaplib.IMAP4.error as e:
            logger.error("imap_connection_error", error=str(e))

    def _process_email(self, mail: imaplib.IMAP4_SSL, email_id: bytes) -> None:
        """Process a single email and route through orchestrator."""
        from app.services.orchestration.message_gateway import MessageGateway
        from app.services.orchestration.task_orchestrator import TaskOrchestrator

        status, data = mail.fetch(email_id, "(RFC822)")
        if status != "OK":
            return

        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)

        # Parse headers
        sender = self._decode_header(msg.get("From", ""))
        subject = self._decode_header(msg.get("Subject", ""))
        message_id = msg.get("Message-ID", "")

        # Parse body
        body = self._extract_body(msg)
        if not body:
            return

        logger.info(
            "email_received",
            sender=sender,
            subject=subject,
            message_id=message_id,
        )

        # Normalize via gateway (pass dict payload as from_email expects)
        unified = MessageGateway.from_email({
            "from": sender,
            "subject": subject,
            "body": f"[Subject: {subject}]\n\n{body}" if subject else body,
            "message_id": message_id,
        })

        # Route through orchestrator (async from sync context)
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(TaskOrchestrator.submit(unified))
        except Exception as e:
            logger.error("email_gateway_error", error=str(e))

    @staticmethod
    def _decode_header(value: str) -> str:
        """Decode email header (handles encoded words like =?UTF-8?...)."""
        if not value:
            return ""
        decoded_parts = decode_header(value)
        result = []
        for part, charset in decoded_parts:
            if isinstance(part, bytes):
                result.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                result.append(part)
        return " ".join(result)

    @staticmethod
    def _extract_body(msg: email.message.Message) -> str:
        """Extract plain text body from email message."""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        return payload.decode(charset, errors="replace")
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
        return ""


# Singleton
email_poller = EmailPoller()
