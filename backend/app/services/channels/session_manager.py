"""
SessionManager — Manages conversation sessions per channel/user.

Inspired by OpenClaw's session key model. Each conversation gets
a session key that isolates context by agent, channel, and peer.

Session keys:
  DM:    agent:<agentId>:<channel>:dm:<peerId>
  Group: agent:<agentId>:<channel>:group:<groupId>

Features:
  - Conversation history per session (for LLM context)
  - Redis persistence (survive restart)
  - Daily reset (configurable hour)
  - Idle timeout reset
  - /reset command support
  - Cross-channel identity linking
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

import structlog

logger = structlog.get_logger()

# Max messages to keep in session history (sliding window)
MAX_HISTORY_SIZE = 20

# Redis key prefix + TTL
REDIS_PREFIX = "session:"
REDIS_TTL_SECONDS = 7200  # 2 hours — matches idle_minutes


@dataclass
class Session:
    """A single conversation session."""

    key: str
    agent: str = ""
    channel: str = ""
    peer_id: str = ""
    history: list[dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_active: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = field(default_factory=dict)

    def add_message(self, role: str, content: str) -> None:
        """Add a message to history (sliding window)."""
        self.history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        # Keep only last N messages
        if len(self.history) > MAX_HISTORY_SIZE:
            self.history = self.history[-MAX_HISTORY_SIZE:]
        self.last_active = datetime.now(timezone.utc)

    def get_llm_messages(self) -> list[dict]:
        """Get history formatted for LLM API calls.

        Returns list of {"role": "user"|"assistant", "content": "..."}
        """
        return [
            {"role": msg["role"], "content": msg["content"]}
            for msg in self.history
        ]

    def reset(self) -> None:
        """Clear conversation history."""
        self.history = []
        self.created_at = datetime.now(timezone.utc)
        self.last_active = datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        """Serialize session for Redis storage."""
        return {
            "key": self.key,
            "agent": self.agent,
            "channel": self.channel,
            "peer_id": self.peer_id,
            "history": self.history,
            "created_at": self.created_at.isoformat(),
            "last_active": self.last_active.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Session:
        """Deserialize session from Redis storage."""
        return cls(
            key=data["key"],
            agent=data.get("agent", ""),
            channel=data.get("channel", ""),
            peer_id=data.get("peer_id", ""),
            history=data.get("history", []),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(timezone.utc),
            last_active=datetime.fromisoformat(data["last_active"]) if data.get("last_active") else datetime.now(timezone.utc),
            metadata=data.get("metadata", {}),
        )


class SessionManager:
    """Manages all active sessions.

    Uses in-memory dict as primary store with optional Redis
    persistence for survive-restart.
    """

    _sessions: dict[str, Session] = {}
    _redis = None  # Lazy-initialized Redis connection

    # ── Config ──────────────────────────────────────────────
    reset_hour: int = 4         # Daily reset at 4:00 AM UTC
    idle_minutes: int = 120     # Reset after 2 hours idle

    # ── Identity links: maps channel-prefixed IDs to canonical ──
    # e.g. {"telegram:12345": "user@company.com", "whatsapp:+628xxx": "user@company.com"}
    identity_links: dict[str, str] = {}

    # ── Redis integration ──────────────────────────────────

    @classmethod
    async def _get_redis(cls):
        """Lazy-initialize Redis connection. Returns None if unavailable."""
        if cls._redis is not None:
            return cls._redis
        try:
            import os
            import aioredis
            redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
            cls._redis = aioredis.from_url(redis_url, decode_responses=True)
            # Test connection
            await cls._redis.ping()
            logger.info("session_redis_connected", url=redis_url)
            return cls._redis
        except Exception as e:
            logger.debug("session_redis_unavailable", error=str(e))
            cls._redis = None
            return None

    @classmethod
    async def _save_to_redis(cls, session: Session) -> None:
        """Persist session to Redis with TTL."""
        redis = await cls._get_redis()
        if not redis:
            return
        try:
            redis_key = f"{REDIS_PREFIX}{session.key}"
            await redis.set(
                redis_key,
                json.dumps(session.to_dict()),
                ex=REDIS_TTL_SECONDS,
            )
        except Exception as e:
            logger.debug("session_redis_save_error", error=str(e))

    @classmethod
    async def _load_from_redis(cls, key: str) -> Session | None:
        """Load session from Redis if available."""
        redis = await cls._get_redis()
        if not redis:
            return None
        try:
            redis_key = f"{REDIS_PREFIX}{key}"
            data = await redis.get(redis_key)
            if data:
                session = Session.from_dict(json.loads(data))
                logger.debug("session_restored_from_redis", key=key)
                return session
        except Exception as e:
            logger.debug("session_redis_load_error", error=str(e))
        return None

    @classmethod
    async def _delete_from_redis(cls, key: str) -> None:
        """Delete session from Redis."""
        redis = await cls._get_redis()
        if not redis:
            return
        try:
            await redis.delete(f"{REDIS_PREFIX}{key}")
        except Exception:
            pass

    # ── Core session methods ───────────────────────────────

    @classmethod
    async def get_or_create(
        cls,
        channel: str,
        peer_id: str,
        agent: str = "default",
        chat_type: str = "dm",
        group_id: str = "",
    ) -> Session:
        """Get existing session or create new one.

        Session key format (from OpenClaw):
          DM:    agent:<agent>:<channel>:dm:<peerId>
          Group: agent:<agent>:<channel>:group:<groupId>
        """
        # Resolve peer identity across channels
        canonical_peer = cls._resolve_identity(channel, peer_id)

        # Build session key
        if chat_type == "group" and group_id:
            key = f"agent:{agent}:{channel}:group:{group_id}"
        else:
            key = f"agent:{agent}:{channel}:dm:{canonical_peer}"

        session = cls._sessions.get(key)

        # If not in memory, try loading from Redis
        if not session:
            session = await cls._load_from_redis(key)
            if session:
                cls._sessions[key] = session

        if session:
            # Check if session should be reset
            if cls._should_reset(session):
                logger.info("session_auto_reset", key=key, reason="expired")
                session.reset()
                await cls._save_to_redis(session)
            return session

        # Create new session
        session = Session(
            key=key,
            agent=agent,
            channel=channel,
            peer_id=canonical_peer,
        )
        cls._sessions[key] = session
        await cls._save_to_redis(session)
        logger.info("session_created", key=key, channel=channel, peer_id=canonical_peer)
        return session

    @classmethod
    async def save_session(cls, session: Session) -> None:
        """Explicitly save session to Redis (call after adding messages)."""
        await cls._save_to_redis(session)

    @classmethod
    async def reset_session(cls, channel: str, peer_id: str, agent: str = "default") -> bool:
        """Manually reset a session (e.g. /reset command)."""
        canonical_peer = cls._resolve_identity(channel, peer_id)
        key = f"agent:{agent}:{channel}:dm:{canonical_peer}"
        session = cls._sessions.get(key)
        if session:
            session.reset()
            await cls._save_to_redis(session)
            logger.info("session_manual_reset", key=key)
            return True
        # Also try clearing from Redis
        await cls._delete_from_redis(key)
        return False

    @classmethod
    def get_session_count(cls) -> int:
        """Get number of active sessions."""
        return len(cls._sessions)

    @classmethod
    def get_all_sessions(cls) -> list[Session]:
        """Get all active sessions."""
        return list(cls._sessions.values())

    @classmethod
    def _should_reset(cls, session: Session) -> bool:
        """Check if session should be auto-reset.

        Resets on:
        1. Daily reset: if session predates today's reset hour
        2. Idle timeout: if session has been idle too long
        """
        now = datetime.now(timezone.utc)

        # Idle timeout
        if cls.idle_minutes > 0:
            idle_threshold = now - timedelta(minutes=cls.idle_minutes)
            if session.last_active < idle_threshold:
                return True

        # Daily reset
        today_reset = now.replace(
            hour=cls.reset_hour, minute=0, second=0, microsecond=0,
        )
        if now.hour < cls.reset_hour:
            today_reset -= timedelta(days=1)
        if session.last_active < today_reset:
            return True

        return False

    @classmethod
    def _resolve_identity(cls, channel: str, peer_id: str) -> str:
        """Resolve cross-channel identity.

        If a user messages from Telegram and WhatsApp with linked IDs,
        they share the same session context.
        """
        prefixed = f"{channel}:{peer_id}"
        return cls.identity_links.get(prefixed, peer_id)

    @classmethod
    def link_identity(cls, channel: str, peer_id: str, canonical: str) -> None:
        """Link a channel-specific ID to a canonical identity."""
        cls.identity_links[f"{channel}:{peer_id}"] = canonical
        logger.info(
            "identity_linked",
            channel=channel,
            peer_id=peer_id,
            canonical=canonical,
        )
