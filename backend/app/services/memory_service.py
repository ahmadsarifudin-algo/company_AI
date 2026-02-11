"""
Memory Service — Session and long-term memory for agents.

- Session Memory: Redis-backed conversation state (TTL-based)
- Long-Term Memory: Key decisions ingested into knowledge base for future RAG
"""

import json
from typing import Any

import redis.asyncio as aioredis
import structlog

from app.core.config import get_settings
from app.services.knowledge_service import KnowledgeService

logger = structlog.get_logger()
settings = get_settings()


class MemoryService:
    """Manages agent session memory (Redis) and long-term memory (knowledge base)."""

    def __init__(self, knowledge_service: KnowledgeService | None = None):
        self._redis: aioredis.Redis | None = None
        self._knowledge = knowledge_service

    async def _get_redis(self) -> aioredis.Redis:
        """Lazy-init Redis connection."""
        if self._redis is None:
            self._redis = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
            )
        return self._redis

    # ── Session Memory (Redis) ───────────────────

    async def save_session(
        self,
        thread_id: str,
        messages: list[dict[str, str]],
        max_messages: int = 50,
    ) -> None:
        """Save conversation messages to Redis.

        Keeps only the last `max_messages` messages. Automatically
        expires after MEMORY_TTL seconds.

        Args:
            thread_id: Conversation thread identifier.
            messages: List of message dicts with 'role' and 'content'.
            max_messages: Max messages to retain.
        """
        r = await self._get_redis()
        key = f"session:{thread_id}"

        # Keep only recent messages
        trimmed = messages[-max_messages:]
        await r.set(key, json.dumps(trimmed), ex=settings.MEMORY_TTL)

        logger.info("session_saved", thread_id=thread_id, messages=len(trimmed))

    async def load_session(self, thread_id: str) -> list[dict[str, str]]:
        """Load conversation messages from Redis.

        Args:
            thread_id: Conversation thread identifier.

        Returns:
            List of message dicts, or empty list if no session exists.
        """
        r = await self._get_redis()
        key = f"session:{thread_id}"

        data = await r.get(key)
        if data is None:
            return []

        messages: list[dict[str, str]] = json.loads(data)
        logger.info("session_loaded", thread_id=thread_id, messages=len(messages))
        return messages

    async def clear_session(self, thread_id: str) -> bool:
        """Clear a conversation session from Redis.

        Args:
            thread_id: Thread to clear.

        Returns:
            True if session existed and was deleted.
        """
        r = await self._get_redis()
        key = f"session:{thread_id}"
        deleted = await r.delete(key)
        logger.info("session_cleared", thread_id=thread_id, existed=bool(deleted))
        return bool(deleted)

    async def append_to_session(
        self,
        thread_id: str,
        message: dict[str, str],
    ) -> None:
        """Append a single message to an existing session.

        If no session exists, creates one with just this message.

        Args:
            thread_id: Conversation thread.
            message: Message dict with 'role' and 'content'.
        """
        messages = await self.load_session(thread_id)
        messages.append(message)
        await self.save_session(thread_id, messages)

    # ── Long-Term Memory (Knowledge Base) ────────

    async def save_long_term_memory(
        self,
        agent_name: str,
        department: str,
        content: str,
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Save a key decision or outcome to the knowledge base.

        This allows agents to learn from past executions. Decisions are
        stored as doc_type="decision" and can be retrieved via RAG.

        Args:
            agent_name: Name of the agent that made the decision.
            department: Department scope.
            content: The decision/outcome text.
            title: Optional title (defaults to auto-generated).
            metadata: Extra metadata.

        Returns:
            Ingestion result dict, or None if knowledge service unavailable.
        """
        if self._knowledge is None:
            logger.warning("no_knowledge_service", agent=agent_name)
            return None

        doc_title = title or f"Decision by {agent_name}"
        doc_metadata = {
            "agent": agent_name,
            "memory_type": "long_term",
            **(metadata or {}),
        }

        result = await self._knowledge.ingest_document(
            title=doc_title,
            content=content,
            department=department,
            doc_type="decision",
            source=f"agent:{agent_name}",
            metadata=doc_metadata,
        )

        logger.info(
            "long_term_memory_saved",
            agent=agent_name,
            department=department,
            doc_id=result.get("parent_doc_id"),
        )
        return result

    # ── Cleanup ──────────────────────────────────

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
