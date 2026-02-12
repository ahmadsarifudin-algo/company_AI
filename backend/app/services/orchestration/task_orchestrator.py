"""
TaskOrchestrator — Manages the full lifecycle of user tasks.

Receives a UnifiedMessage, routes it, creates a trace, delegates
to the correct agent, manages approval waits, and sends the response
back via NotificationDispatcher.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

import structlog

from app.services.orchestration.intent_router import IntentRouter, RoutingResult
from app.services.orchestration.message_gateway import UnifiedMessage

logger = structlog.get_logger()


class TaskStatus(str, Enum):
    """Lifecycle states for an orchestrated task."""

    RECEIVED = "received"
    ROUTING = "routing"
    IN_PROGRESS = "in_progress"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass
class OrchestrationTask:
    """Internal representation of a task being orchestrated."""

    task_id: str
    trace_id: str
    message: UnifiedMessage
    routing: RoutingResult
    status: TaskStatus = TaskStatus.RECEIVED
    agent_response: str = ""
    tool_chain: list[dict[str, Any]] = field(default_factory=list)
    approval_id: str = ""
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    error: str = ""


class TaskOrchestrator:
    """Coordinates the full task lifecycle.

    Flow:
    1. Receive UnifiedMessage from MessageGateway
    2. Route via IntentRouter → department + agent
    3. Create trace + task records
    4. Delegate to agent (via existing agent execution pipeline)
    5. Monitor tool chain execution
    6. Handle approval gates (pause/resume)
    7. Collect response and send via NotificationDispatcher

    In-memory task store for now; production uses DB + Redis.
    """

    _tasks: dict[str, OrchestrationTask] = {}

    @classmethod
    async def submit(cls, message: UnifiedMessage) -> OrchestrationTask:
        """Submit a new task from an inbound message.

        Args:
            message: Normalized message from MessageGateway.

        Returns:
            OrchestrationTask tracking the execution.
        """
        task_id = f"task_{uuid4().hex[:12]}"
        trace_id = f"trace_{uuid4().hex[:12]}"

        # Route the message
        routing = IntentRouter.route(
            content=message.content,
            sender_department=message.metadata.get("department", ""),
        )

        task = OrchestrationTask(
            task_id=task_id,
            trace_id=trace_id,
            message=message,
            routing=routing,
            status=TaskStatus.ROUTING,
        )

        cls._tasks[task_id] = task

        logger.info(
            "orchestration_task_created",
            task_id=task_id,
            trace_id=trace_id,
            channel=message.channel,
            sender=message.sender,
            department=routing.department,
            agent=routing.agent,
        )

        # Execute the task
        await cls._execute(task)

        return task

    @classmethod
    async def _execute(cls, task: OrchestrationTask) -> None:
        """Execute the task by delegating to the appropriate agent.

        This connects to the existing BaseAgent.execute() pipeline.
        """
        task.status = TaskStatus.IN_PROGRESS

        try:
            # TODO: Wire to actual agent execution pipeline
            # For now, create a structured response placeholder
            task.agent_response = (
                f"Task received by {task.routing.agent} "
                f"(Department: {task.routing.department}). "
                f"Processing: '{task.message.content[:100]}...'"
            )
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now(timezone.utc)

            logger.info(
                "orchestration_task_completed",
                task_id=task.task_id,
                trace_id=task.trace_id,
                agent=task.routing.agent,
            )

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            logger.error(
                "orchestration_task_failed",
                task_id=task.task_id,
                error=str(e),
            )

    @classmethod
    async def handle_approval(
        cls,
        task_id: str,
        decision: str,
        approver: str,
        reason: str = "",
    ) -> OrchestrationTask | None:
        """Handle approval/rejection for a paused task.

        Args:
            task_id: Task awaiting approval.
            decision: "approved" or "rejected".
            approver: Who made the decision.
            reason: Rejection reason (if rejected).

        Returns:
            Updated task, or None if not found.
        """
        task = cls._tasks.get(task_id)
        if not task or task.status != TaskStatus.WAITING_APPROVAL:
            return None

        if decision == "approved":
            task.status = TaskStatus.IN_PROGRESS
            logger.info(
                "orchestration_approval_granted",
                task_id=task_id,
                approver=approver,
            )
            # Resume execution
            await cls._execute(task)
        else:
            task.status = TaskStatus.REJECTED
            task.error = reason
            task.completed_at = datetime.now(timezone.utc)
            logger.info(
                "orchestration_approval_rejected",
                task_id=task_id,
                approver=approver,
                reason=reason,
            )

        return task

    @classmethod
    def get_task(cls, task_id: str) -> OrchestrationTask | None:
        """Get a task by ID."""
        return cls._tasks.get(task_id)

    @classmethod
    def get_tasks_by_sender(cls, sender: str) -> list[OrchestrationTask]:
        """Get all tasks for a given sender."""
        return [t for t in cls._tasks.values() if t.message.sender == sender]

    @classmethod
    def get_pending_approvals(cls) -> list[OrchestrationTask]:
        """Get all tasks waiting for approval."""
        return [
            t for t in cls._tasks.values()
            if t.status == TaskStatus.WAITING_APPROVAL
        ]
