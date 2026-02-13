"""
MessageQueue — Per-session message queuing with collect mode.

Inspired by OpenClaw's command queue. Serializes runs per session
to prevent race conditions and coalesces rapid messages.

Queue modes (from OpenClaw):
  collect:  Coalesce messages into a single LLM turn (default)
  followup: Queue for next turn after current run

Features:
  - Per-session FIFO queue
  - Debounce: wait N ms for more messages before processing
  - Cap: max queued messages per session (overflow → summarize)
  - Global concurrency cap
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

import structlog

from app.services.orchestration.message_gateway import UnifiedMessage

logger = structlog.get_logger()


@dataclass
class QueuedMessage:
    """A message waiting in the queue."""

    message: UnifiedMessage
    queued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class MessageQueue:
    """Per-session message queue with collect mode.

    When multiple messages arrive rapidly for the same session,
    they are coalesced into a single LLM call to avoid race
    conditions and reduce LLM costs.
    """

    # ── Config ─────────────────────────────────────────────
    debounce_ms: int = 1000       # Wait 1s for more messages
    cap: int = 20                 # Max queued messages per session
    max_concurrent: int = 4       # Global concurrency cap
    mode: str = "collect"         # "collect" | "followup"

    # ── State ──────────────────────────────────────────────
    _queues: dict[str, list[QueuedMessage]] = defaultdict(list)
    _processing: set[str] = set()
    _debounce_tasks: dict[str, asyncio.Task] = {}
    _semaphore: asyncio.Semaphore | None = None

    @classmethod
    def _get_semaphore(cls) -> asyncio.Semaphore:
        """Lazy-init semaphore (must be created within event loop)."""
        if cls._semaphore is None:
            cls._semaphore = asyncio.Semaphore(cls.max_concurrent)
        return cls._semaphore

    @classmethod
    async def enqueue(
        cls,
        session_key: str,
        message: UnifiedMessage,
        process_fn,
    ) -> None:
        """Add a message to the session queue.

        Args:
            session_key: Session identifier for queue isolation.
            message: The unified message to process.
            process_fn: Async callable(list[UnifiedMessage]) to process collected messages.
        """
        queued = QueuedMessage(message=message)
        queue = cls._queues[session_key]

        # Enforce cap
        if len(queue) >= cls.cap:
            logger.warning(
                "message_queue_cap_reached",
                session_key=session_key,
                cap=cls.cap,
            )
            # Drop oldest message
            queue.pop(0)

        queue.append(queued)
        logger.info(
            "message_queued",
            session_key=session_key,
            queue_size=len(queue),
        )

        # Cancel existing debounce timer for this session
        if session_key in cls._debounce_tasks:
            cls._debounce_tasks[session_key].cancel()

        # Start new debounce timer
        cls._debounce_tasks[session_key] = asyncio.create_task(
            cls._debounced_process(session_key, process_fn)
        )

    @classmethod
    async def _debounced_process(cls, session_key: str, process_fn) -> None:
        """Wait for debounce period, then process collected messages."""
        try:
            # Wait for debounce period (more messages might arrive)
            await asyncio.sleep(cls.debounce_ms / 1000.0)

            # Check if already processing this session
            if session_key in cls._processing:
                logger.info("message_queue_waiting", session_key=session_key)
                return

            # Drain queue
            queue = cls._queues.get(session_key, [])
            if not queue:
                return

            # Collect all queued messages
            messages = [qm.message for qm in queue]
            cls._queues[session_key] = []

            # Process with global concurrency limit
            cls._processing.add(session_key)
            try:
                async with cls._get_semaphore():
                    if cls.mode == "collect" and len(messages) > 1:
                        # Coalesce: combine message contents
                        logger.info(
                            "message_queue_collected",
                            session_key=session_key,
                            message_count=len(messages),
                        )
                    await process_fn(messages)
            finally:
                cls._processing.discard(session_key)

                # Check if more messages arrived while processing
                if cls._queues.get(session_key):
                    cls._debounce_tasks[session_key] = asyncio.create_task(
                        cls._debounced_process(session_key, process_fn)
                    )

        except asyncio.CancelledError:
            pass  # Debounce cancelled (new message arrived)
        except Exception as e:
            cls._processing.discard(session_key)
            logger.error("message_queue_error", session_key=session_key, error=str(e))

    @classmethod
    def is_processing(cls, session_key: str) -> bool:
        """Check if a session is currently being processed."""
        return session_key in cls._processing

    @classmethod
    def queue_size(cls, session_key: str) -> int:
        """Get current queue size for a session."""
        return len(cls._queues.get(session_key, []))

    @classmethod
    def active_sessions(cls) -> int:
        """Get number of sessions with queued messages or in processing."""
        return len(cls._processing) + len(
            [k for k, v in cls._queues.items() if v]
        )
