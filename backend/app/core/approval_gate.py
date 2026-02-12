"""
ApprovalGate — State machine for human approval workflows (Redis-backed).
IdempotencyGuard — Ensures side-effect operations execute at most once.

ApprovalGate:
    Integrates with PolicyEngine to check if an action needs approval.
    If approval is needed, execution STOPS (no side effects) until a
    qualified human approves via the approval endpoint.

    Storage: Redis hash per approval, keyed by `approval:{approval_id}`.
    Survives restarts with 24h TTL.

IdempotencyGuard:
    Uses Redis keys `idem:{key}` to ensure that retried operations do not
    produce duplicate side effects. TTL: 7 days.
"""

import json
import os
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Callable, Coroutine
from uuid import uuid4

import structlog

from app.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()

APPROVAL_TTL = 86400      # 24 hours
IDEMPOTENCY_TTL = 604800   # 7 days


class ApprovalStatus(str, Enum):
    """Status of an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    AUTO_APPROVED = "auto_approved"


@dataclass
class ApprovalRequest:
    """A request for human approval.

    Created when PolicyEngine returns REQUIRE_APPROVAL.
    Execution halts until this is resolved.
    """

    approval_id: str
    trace_id: str
    task_id: str
    agent_name: str
    department: str
    action: str
    resource: str
    risk_level: str
    reason: str
    status: str = "pending"
    required_approvers: list[str] | None = None
    actual_approvers: list[str] | None = None
    # ── Resume context (Phase 5) ──
    tool_name: str = ""
    tool_args: str = ""      # JSON-serialized tool arguments
    channel: str = ""        # telegram / whatsapp / email
    sender: str = ""         # who triggered the action
    chat_id: str = ""        # Telegram chat_id or WA phone for reply


@dataclass
class ApprovalResult:
    """Result of an approval check."""

    approved: bool
    approval_id: str = ""
    reason: str = ""
    status: ApprovalStatus = ApprovalStatus.AUTO_APPROVED

    @property
    def needs_approval(self) -> bool:
        return not self.approved


async def _get_redis():
    """Get async Redis connection (lazy, singleton)."""
    import aioredis

    redis_url = os.getenv("REDIS_URL", settings.REDIS_URL)
    return aioredis.from_url(redis_url, decode_responses=True)


def _request_to_dict(req: ApprovalRequest) -> dict:
    """Serialize ApprovalRequest to dict for Redis storage."""
    d = asdict(req)
    # Lists need JSON encoding for Redis hash
    d["required_approvers"] = json.dumps(d.get("required_approvers") or [])
    d["actual_approvers"] = json.dumps(d.get("actual_approvers") or [])
    return d


def _dict_to_request(d: dict) -> ApprovalRequest:
    """Deserialize dict from Redis to ApprovalRequest."""
    d["required_approvers"] = json.loads(d.get("required_approvers", "[]"))
    d["actual_approvers"] = json.loads(d.get("actual_approvers", "[]"))
    return ApprovalRequest(**d)


class ApprovalGate:
    """State machine for approval workflows.

    Flow:
    1. PolicyEngine evaluates action → returns REQUIRE_APPROVAL
    2. ApprovalGate.check() creates an ApprovalRequest → STOPS execution
    3. Human reviews and approves/rejects via API or chat
    4. ApprovalGate.grant() / .reject() updates status
    5. Workflow resumes (or aborts)

    Storage: Redis (survives restarts).
    """

    # In-memory fallback when Redis is unavailable
    _fallback: dict[str, ApprovalRequest] = {}

    @classmethod
    async def check(
        cls,
        trace_id: str,
        task_id: str,
        agent_name: str,
        department: str,
        action: str,
        resource: str,
        risk_level: str,
        policy_reason: str,
        required_approvers: list[str] | None = None,
        tool_name: str = "",
        tool_args: dict | None = None,
        channel: str = "",
        sender: str = "",
        chat_id: str = "",
    ) -> ApprovalResult:
        """Check if an action needs approval and create request if so.

        Args:
            trace_id: Current trace ID.
            task_id: Task being executed.
            agent_name: Agent requesting the action.
            department: Agent's department.
            action: Action type.
            resource: Target resource.
            risk_level: Server-derived risk level.
            policy_reason: Why approval is required (from PolicyDecision).
            required_approvers: Roles required to approve.
            tool_name: Tool that needs approval (for resume).
            tool_args: Tool arguments to replay on approval.
            channel: Original message channel.
            sender: Original message sender.
            chat_id: Chat ID for reply delivery.

        Returns:
            ApprovalResult — if needs_approval is True, execution MUST stop.
        """
        approval_id = f"appr_{uuid4().hex[:12]}"

        request = ApprovalRequest(
            approval_id=approval_id,
            trace_id=trace_id,
            task_id=task_id,
            agent_name=agent_name,
            department=department,
            action=action,
            resource=resource,
            risk_level=risk_level,
            reason=policy_reason,
            required_approvers=required_approvers or [],
            tool_name=tool_name,
            tool_args=json.dumps(tool_args or {}),
            channel=channel,
            sender=sender,
            chat_id=chat_id,
        )

        # Store in Redis
        try:
            redis = await _get_redis()
            key = f"approval:{approval_id}"
            await redis.hset(key, mapping=_request_to_dict(request))
            await redis.expire(key, APPROVAL_TTL)
            # Index by department for fast lookup
            await redis.sadd(f"approval:dept:{department}", approval_id)
            await redis.expire(f"approval:dept:{department}", APPROVAL_TTL)
            # Index by sender for chat-based approval lookup
            if sender:
                await redis.set(f"approval:sender:{sender}", approval_id, ex=APPROVAL_TTL)
            await redis.close()
        except Exception as e:
            logger.warning("approval_redis_fallback", error=str(e))
            cls._fallback[approval_id] = request

        logger.info(
            "approval_requested",
            approval_id=approval_id,
            trace_id=trace_id,
            agent=agent_name,
            action=action,
            resource=resource,
            risk=risk_level,
            reason=policy_reason,
            tool=tool_name,
        )

        return ApprovalResult(
            approved=False,
            approval_id=approval_id,
            reason=policy_reason,
            status=ApprovalStatus.PENDING,
        )

    @classmethod
    async def grant(cls, approval_id: str, approver_id: str) -> ApprovalRequest | None:
        """Grant an approval.

        Args:
            approval_id: The approval to grant.
            approver_id: Who is approving.

        Returns:
            Updated ApprovalRequest, or None if not found.
        """
        request = await cls.get_by_id(approval_id)
        if not request:
            logger.warning("approval_not_found", approval_id=approval_id)
            return None

        if request.actual_approvers is None:
            request.actual_approvers = []
        request.actual_approvers.append(approver_id)
        request.status = ApprovalStatus.APPROVED.value

        # Update Redis
        try:
            redis = await _get_redis()
            key = f"approval:{approval_id}"
            await redis.hset(key, mapping={
                "status": request.status,
                "actual_approvers": json.dumps(request.actual_approvers),
            })
            await redis.close()
        except Exception:
            cls._fallback[approval_id] = request

        logger.info(
            "approval_granted",
            approval_id=approval_id,
            trace_id=request.trace_id,
            approver=approver_id,
            agent=request.agent_name,
        )

        return request

    @classmethod
    async def reject(
        cls, approval_id: str, rejector_id: str, reason: str = ""
    ) -> ApprovalRequest | None:
        """Reject an approval.

        Args:
            approval_id: The approval to reject.
            rejector_id: Who is rejecting.
            reason: Why it was rejected.

        Returns:
            Updated ApprovalRequest, or None if not found.
        """
        request = await cls.get_by_id(approval_id)
        if not request:
            return None

        request.status = ApprovalStatus.REJECTED.value
        request.reason = reason or request.reason

        # Update Redis
        try:
            redis = await _get_redis()
            key = f"approval:{approval_id}"
            await redis.hset(key, mapping={
                "status": request.status,
                "reason": request.reason,
            })
            await redis.close()
        except Exception:
            cls._fallback[approval_id] = request

        logger.info(
            "approval_rejected",
            approval_id=approval_id,
            trace_id=request.trace_id,
            rejector=rejector_id,
            reason=reason,
        )

        return request

    @classmethod
    async def get_pending(cls, department: str | None = None) -> list[ApprovalRequest]:
        """Get all pending approvals, optionally filtered by department."""
        results: list[ApprovalRequest] = []

        try:
            redis = await _get_redis()

            if department:
                # Use department index
                ids = await redis.smembers(f"approval:dept:{department}")
            else:
                # Scan for all approval keys
                ids = set()
                async for key in redis.scan_iter("approval:appr_*"):
                    ids.add(key.replace("approval:", ""))

            for aid in ids:
                data = await redis.hgetall(f"approval:{aid}")
                if data and data.get("status") == "pending":
                    results.append(_dict_to_request(data))

            await redis.close()
        except Exception:
            # Fallback to in-memory
            results = [
                r for r in cls._fallback.values()
                if r.status == ApprovalStatus.PENDING.value
                and (not department or r.department == department)
            ]

        return results

    @classmethod
    async def get_by_id(cls, approval_id: str) -> ApprovalRequest | None:
        """Get an approval request by ID."""
        try:
            redis = await _get_redis()
            data = await redis.hgetall(f"approval:{approval_id}")
            await redis.close()
            if data:
                return _dict_to_request(data)
        except Exception:
            pass

        return cls._fallback.get(approval_id)

    @classmethod
    async def get_pending_for_sender(cls, sender: str) -> ApprovalRequest | None:
        """Get the most recent pending approval linked to a sender.

        Used by gateway to let users approve/reject via chat reply.
        """
        try:
            redis = await _get_redis()
            approval_id = await redis.get(f"approval:sender:{sender}")
            await redis.close()
            if approval_id:
                req = await cls.get_by_id(approval_id)
                if req and req.status == "pending":
                    return req
        except Exception:
            pass

        # Fallback
        for r in cls._fallback.values():
            if r.sender == sender and r.status == "pending":
                return r
        return None

    @classmethod
    async def clear(cls) -> None:
        """Clear all pending approvals. For testing only."""
        try:
            redis = await _get_redis()
            async for key in redis.scan_iter("approval:*"):
                await redis.delete(key)
            await redis.close()
        except Exception:
            pass
        cls._fallback.clear()


class IdempotencyGuard:
    """Ensures side-effect operations execute at most once.

    Uses Redis keys `idem:{key}` to persist across restarts.
    Falls back to in-memory dict if Redis is unavailable.
    """

    _fallback: dict[str, Any] = {}

    @classmethod
    async def execute_once(
        cls,
        key: str,
        handler: Callable[..., Coroutine[Any, Any, Any]],
    ) -> Any:
        """Execute a handler at most once for the given key.

        Args:
            key: Idempotency key (typically "trace_id:step_id").
            handler: Async callable to execute.

        Returns:
            Result of the handler (cached if already executed).
        """
        redis_key = f"idem:{key}"

        # Check Redis first
        try:
            redis = await _get_redis()
            cached = await redis.get(redis_key)
            if cached is not None:
                logger.info("idempotency_cache_hit", key=key)
                await redis.close()
                try:
                    return json.loads(cached)
                except json.JSONDecodeError:
                    return cached
        except Exception:
            # Fall back to in-memory
            if key in cls._fallback:
                logger.info("idempotency_cache_hit", key=key)
                return cls._fallback[key]

        # Execute handler
        logger.info("idempotency_executing", key=key)
        result = await handler()

        # Store result
        try:
            redis = await _get_redis()
            serialized = json.dumps(result) if result is not None else ""
            await redis.set(redis_key, serialized, ex=IDEMPOTENCY_TTL)
            await redis.close()
        except Exception:
            cls._fallback[key] = result

        return result

    @classmethod
    async def has_executed(cls, key: str) -> bool:
        """Check if a key has already been executed."""
        try:
            redis = await _get_redis()
            exists = await redis.exists(f"idem:{key}")
            await redis.close()
            return bool(exists)
        except Exception:
            return key in cls._fallback

    @classmethod
    async def clear(cls) -> None:
        """Clear all idempotency records. For testing only."""
        try:
            redis = await _get_redis()
            async for key in redis.scan_iter("idem:*"):
                await redis.delete(key)
            await redis.close()
        except Exception:
            pass
        cls._fallback.clear()
