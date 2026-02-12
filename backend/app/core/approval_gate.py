"""
ApprovalGate — State machine for human approval workflows.
IdempotencyGuard — Ensures side-effect operations execute at most once.

ApprovalGate:
    Integrates with PolicyEngine to check if an action needs approval.
    If approval is needed, execution STOPS (no side effects) until a
    qualified human approves via the approval endpoint.

IdempotencyGuard:
    Uses Redis keys based on trace_id:step_id to ensure that retried
    operations do not produce duplicate side effects (e.g., sending
    an email twice or processing a payment twice).
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Coroutine
from uuid import uuid4

import structlog

from app.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


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
    status: ApprovalStatus = ApprovalStatus.PENDING
    required_approvers: list[str] | None = None
    actual_approvers: list[str] | None = None


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


class ApprovalGate:
    """State machine for approval workflows.

    Flow:
    1. PolicyEngine evaluates action → returns REQUIRE_APPROVAL
    2. ApprovalGate.check() creates an ApprovalRequest → STOPS execution
    3. Human reviews and approves/rejects via API
    4. ApprovalGate.grant() / .reject() updates status
    5. Workflow resumes (or aborts)

    In-memory store for now; production would use DB + Redis pub/sub.
    """

    _pending: dict[str, ApprovalRequest] = {}

    @classmethod
    def check(
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
    ) -> ApprovalResult:
        """Check if an action needs approval and create request if so.

        This method should be called by the chokepoint gateways when
        PolicyEngine returns REQUIRE_APPROVAL.

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
        )

        cls._pending[approval_id] = request

        logger.info(
            "approval_requested",
            approval_id=approval_id,
            trace_id=trace_id,
            agent=agent_name,
            action=action,
            resource=resource,
            risk=risk_level,
            reason=policy_reason,
        )

        return ApprovalResult(
            approved=False,
            approval_id=approval_id,
            reason=policy_reason,
            status=ApprovalStatus.PENDING,
        )

    @classmethod
    def grant(cls, approval_id: str, approver_id: str) -> ApprovalRequest | None:
        """Grant an approval.

        Args:
            approval_id: The approval to grant.
            approver_id: Who is approving (validated against required_approvers).

        Returns:
            Updated ApprovalRequest, or None if not found.
        """
        request = cls._pending.get(approval_id)
        if not request:
            logger.warning("approval_not_found", approval_id=approval_id)
            return None

        if request.actual_approvers is None:
            request.actual_approvers = []
        request.actual_approvers.append(approver_id)
        request.status = ApprovalStatus.APPROVED

        logger.info(
            "approval_granted",
            approval_id=approval_id,
            trace_id=request.trace_id,
            approver=approver_id,
            agent=request.agent_name,
        )

        return request

    @classmethod
    def reject(cls, approval_id: str, rejector_id: str, reason: str = "") -> ApprovalRequest | None:
        """Reject an approval.

        Args:
            approval_id: The approval to reject.
            rejector_id: Who is rejecting.
            reason: Why it was rejected.

        Returns:
            Updated ApprovalRequest, or None if not found.
        """
        request = cls._pending.get(approval_id)
        if not request:
            return None

        request.status = ApprovalStatus.REJECTED
        request.reason = reason or request.reason

        logger.info(
            "approval_rejected",
            approval_id=approval_id,
            trace_id=request.trace_id,
            rejector=rejector_id,
            reason=reason,
        )

        return request

    @classmethod
    def get_pending(cls, department: str | None = None) -> list[ApprovalRequest]:
        """Get all pending approvals, optionally filtered by department."""
        pending = [r for r in cls._pending.values() if r.status == ApprovalStatus.PENDING]
        if department:
            pending = [r for r in pending if r.department == department]
        return pending

    @classmethod
    def get_by_id(cls, approval_id: str) -> ApprovalRequest | None:
        """Get an approval request by ID."""
        return cls._pending.get(approval_id)

    @classmethod
    def clear(cls) -> None:
        """Clear all pending approvals. For testing only."""
        cls._pending.clear()


class IdempotencyGuard:
    """Ensures side-effect operations execute at most once.

    Uses a key based on trace_id:step_id. If the key already exists
    (from a previous execution), the handler is NOT re-executed and
    the cached result is returned instead.

    In-memory implementation for now; production would use Redis with TTL.
    """

    _executed: dict[str, Any] = {}

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
        if key in cls._executed:
            logger.info("idempotency_cache_hit", key=key)
            return cls._executed[key]

        logger.info("idempotency_executing", key=key)
        result = await handler()
        cls._executed[key] = result

        return result

    @classmethod
    def has_executed(cls, key: str) -> bool:
        """Check if a key has already been executed."""
        return key in cls._executed

    @classmethod
    def clear(cls) -> None:
        """Clear all idempotency records. For testing only."""
        cls._executed.clear()
