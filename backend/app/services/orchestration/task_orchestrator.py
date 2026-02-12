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
from app.services.channels.session_manager import SessionManager
from app.services.channels.department_guard import DepartmentGuard
from app.services.channels.soul_resolver import SoulResolver
from app.services.channels.response_shaper import ResponseShaper

logger = structlog.get_logger()


# ── Routing Bindings (channel/peer → agent) ──────────────
# Explicit mappings checked BEFORE IntentRouter keyword matching.
# Inspired by OpenClaw's binding system with 6 priority levels.

ROUTING_BINDINGS: list[dict] = [
    # Examples (uncomment to activate):
    # {"match": {"channel": "telegram", "peer_id": "-100123"}, "agent": "TechSupervisor", "department": "tech"},
    # {"match": {"channel": "whatsapp"}, "agent": "HRAssistant", "department": "hr"},
    # {"match": {"channel": "email"}, "agent": "FinanceSupervisor", "department": "finance"},
]


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
class ResponseEnvelope:
    """Standardized output from the orchestrator.

    Every orchestrator response MUST be wrapped in this envelope.
    Consumers (NotificationDispatcher, dashboard, API) use this
    instead of raw strings.
    """

    trace_id: str
    run_id: str  # same as task_id for now
    reply_text: str
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    control: dict[str, Any] = field(default_factory=dict)
    # control keys: stop_reason, needs_approval, approval_id
    telemetry: dict[str, Any] = field(default_factory=dict)
    # telemetry keys: latency_ms, tokens_in, tokens_out, provider, model


@dataclass
class OrchestrationTask:
    """Internal representation of a task being orchestrated."""

    task_id: str
    trace_id: str
    message: UnifiedMessage
    routing: RoutingResult
    status: TaskStatus = TaskStatus.RECEIVED
    agent_response: str = ""
    response_envelope: ResponseEnvelope | None = None
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

        # ── 1. Check routing bindings first (OpenClaw pattern) ──
        routing = cls._resolve_binding(message)

        # ── 2. Fallback to IntentRouter keyword matching ──
        if routing is None:
            routing = IntentRouter.route(
                content=message.content,
                sender_department=message.metadata.get("department", ""),
            )

        # ── 2b. Department Guard (chat channels only) ──
        user_department = message.metadata.get("department") or None
        routing = DepartmentGuard.enforce(
            channel=message.channel,
            user_department=user_department,
            intent_result=routing,
        )

        # ── 3. Get or create session for conversation context ──
        chat_type = message.metadata.get("telegram_chat_type", "private")
        group_id = ""
        if chat_type in ("group", "supergroup"):
            group_id = message.sender  # chat_id is the group

        session = await SessionManager.get_or_create(
            channel=message.channel,
            peer_id=message.sender,
            agent=routing.agent,
            chat_type="group" if group_id else "dm",
            group_id=group_id,
        )

        # Add user message to session history
        session.add_message("user", message.content)
        await SessionManager.save_session(session)

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
            session_key=session.key,
            history_len=len(session.history),
        )

        # Execute the task (with session context)
        await cls._execute(task, session)

        return task

    @classmethod
    def _resolve_binding(cls, message: UnifiedMessage) -> RoutingResult | None:
        """Check explicit routing bindings (OpenClaw pattern).

        Priority order:
        1. Exact peer match (channel + peer_id)
        2. Channel match (any peer on this channel)
        """
        for binding in ROUTING_BINDINGS:
            match = binding["match"]
            if match.get("channel") != message.channel:
                continue
            # If peer_id specified, must match exactly
            if "peer_id" in match and match["peer_id"] != message.sender:
                continue
            return RoutingResult(
                department=binding.get("department", "general"),
                agent=binding["agent"],
                intent="binding_match",
                confidence=1.0,
                routing_method="binding",
            )
        return None

    @classmethod
    async def _execute(cls, task: OrchestrationTask, session=None) -> None:
        """Execute the task by calling the agent pipeline and replying via the same channel.

        Execution priority:
        1. Try AgentExecutorService (real LangGraph pipeline with RAG + memory)
        2. Fallback: direct LLM call (current behavior, no tools/RAG)
        """
        import asyncio
        import os
        import httpx

        task.status = TaskStatus.IN_PROGRESS

        try:
            # ── 0. Try real agent executor (Phase 2) ──────────
            agent_result = await cls._try_agent_executor(task)
            if agent_result is not None:
                task.agent_response = agent_result
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.now(timezone.utc)

                # Build envelope
                latency_ms = 0
                if task.completed_at and task.started_at:
                    latency_ms = int(
                        (task.completed_at - task.started_at).total_seconds() * 1000
                    )
                task.response_envelope = ResponseEnvelope(
                    trace_id=task.trace_id,
                    run_id=task.task_id,
                    reply_text=task.agent_response,
                    control={"stop_reason": "completed", "executor": "agent_executor"},
                    telemetry={
                        "latency_ms": latency_ms,
                        "routing_method": task.routing.routing_method,
                        "execution_path": "agent_executor",
                    },
                )

                if session:
                    session.add_message("assistant", task.agent_response)
                    await SessionManager.save_session(session)

                logger.info(
                    "orchestration_task_completed",
                    task_id=task.task_id,
                    trace_id=task.trace_id,
                    agent=task.routing.agent,
                    execution_path="agent_executor",
                    latency_ms=latency_ms,
                )

                await cls._dispatch_reply(task)
                return

            # ── 1. Fallback: Direct LLM call ──────────────────
            logger.info(
                "orchestration_fallback_direct_llm",
                task_id=task.task_id,
                reason="agent_executor_unavailable",
            )

            # ── 1a. Build system prompt ──────────────────────────
            is_chat_channel = task.message.channel in ("telegram", "whatsapp")

            if is_chat_channel:
                # Build user object stub for SoulResolver
                user_stub = type("UserStub", (), {
                    "name": task.message.metadata.get("user_name"),
                    "department": task.message.metadata.get("department"),
                    "active_soul_id": task.message.metadata.get("active_soul_id"),
                })()
                # If no department info, treat as unknown user
                if not user_stub.department:
                    user_stub = None

                system_prompt = SoulResolver.resolve(
                    user=user_stub,
                    channel=task.message.channel,
                )
                # Add dual-output format instruction
                system_prompt += ResponseShaper.build_dual_output_instruction()
            else:
                # Dashboard/API: use prompt_registry (structured JSON)
                system_prompt = (
                    f"You are {task.routing.agent}, a helpful AI assistant in the "
                    f"{task.routing.department} department.\n"
                )
                try:
                    from app.agents.prompt_registry import get_prompt_for_agent
                    custom_prompt = get_prompt_for_agent(task.routing.agent)
                    if custom_prompt:
                        system_prompt = custom_prompt
                except Exception:
                    pass  # Use default prompt

            # ── 2. Get LLM provider + API key ────────────────
            provider = "google"
            api_key = ""
            fallback_provider = ""
            fallback_key = ""

            try:
                import aioredis
                redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
                r = aioredis.from_url(redis_url, decode_responses=True)
                provider = await r.get("settings:provider") or "google"
                key_from_redis = await r.get(f"settings:{provider}_api_key")
                if key_from_redis:
                    api_key = key_from_redis
                await r.close()
            except Exception:
                pass

            if not api_key:
                env_map = {"google": "GOOGLE_API_KEY", "openai": "OPENAI_API_KEY"}
                api_key = os.environ.get(env_map.get(provider, "GOOGLE_API_KEY"), "")

            # Prepare fallback provider
            if provider == "google":
                fallback_provider = "openai"
                fallback_key = os.environ.get("OPENAI_API_KEY", "")
            else:
                fallback_provider = "google"
                fallback_key = os.environ.get("GOOGLE_API_KEY", "")

            if not api_key:
                task.agent_response = (
                    f"⚠️ No API key configured for '{provider}'. "
                    "Please set one in the Configurations page."
                )
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.now(timezone.utc)
                await cls._dispatch_reply(task)
                return

            # ── 3. Call LLM (with retry + fallback) ──────────
            user_content = task.message.content

            # Build conversation history from session
            history_messages = []
            if session and len(session.history) > 1:
                for msg in session.history[:-1]:
                    history_messages.append(msg)

            response_text = await cls._call_llm_with_fallback(
                provider=provider,
                api_key=api_key,
                fallback_provider=fallback_provider,
                fallback_key=fallback_key,
                system_prompt=system_prompt,
                history=history_messages,
                user_content=user_content,
            )

            # ── 4. Shape response (dual-output for chat) ─────
            if is_chat_channel:
                shaped = ResponseShaper.shape(response_text)
                task.agent_response = shaped.human_reply
                # Log the structured agent intent
                if shaped.agent_intent:
                    logger.info(
                        "agent_intent_captured",
                        task_id=task.task_id,
                        intent=shaped.agent_intent.get("intent"),
                        department=shaped.agent_intent.get("department"),
                        action=shaped.agent_intent.get("action"),
                        needs_agent=shaped.agent_intent.get("needs_agent"),
                        confidence=shaped.agent_intent.get("confidence"),
                        parse_success=shaped.parse_success,
                    )
            else:
                task.agent_response = response_text

            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now(timezone.utc)

            # ── 5. Build ResponseEnvelope ─────────────────────
            latency_ms = 0
            if task.completed_at and task.started_at:
                latency_ms = int(
                    (task.completed_at - task.started_at).total_seconds() * 1000
                )
            task.response_envelope = ResponseEnvelope(
                trace_id=task.trace_id,
                run_id=task.task_id,
                reply_text=task.agent_response,
                control={"stop_reason": "completed"},
                telemetry={
                    "latency_ms": latency_ms,
                    "provider": provider,
                    "routing_method": task.routing.routing_method,
                },
            )

            # Save assistant response to session history
            if session:
                session.add_message("assistant", task.agent_response)
                await SessionManager.save_session(session)

            logger.info(
                "orchestration_task_completed",
                task_id=task.task_id,
                trace_id=task.trace_id,
                agent=task.routing.agent,
                department=task.routing.department,
                routing_method=task.routing.routing_method,
                response_len=len(task.agent_response),
                latency_ms=latency_ms,
            )

            # ── 6. Send reply back to user ───────────────────
            await cls._dispatch_reply(task)

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            logger.error(
                "orchestration_task_failed",
                task_id=task.task_id,
                error=str(e),
            )
            # Try to notify the user of the error
            task.agent_response = f"⚠️ Sorry, something went wrong: {str(e)[:200]}"
            try:
                await cls._dispatch_reply(task)
            except Exception:
                pass

    @classmethod
    async def _call_llm_with_fallback(
        cls,
        provider: str,
        api_key: str,
        fallback_provider: str,
        fallback_key: str,
        system_prompt: str,
        history: list[dict],
        user_content: str,
    ) -> str:
        """Call LLM with retry (3x backoff) and auto-fallback on 429."""
        import asyncio
        import httpx

        max_retries = 3

        # Try primary provider with retries
        for attempt in range(max_retries):
            try:
                result = await cls._call_llm(
                    provider, api_key, system_prompt, history, user_content
                )
                return result
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    if attempt < max_retries - 1:
                        wait = (2 ** attempt) + 1  # 1s, 3s, 5s
                        logger.warning(
                            "llm_rate_limited",
                            provider=provider,
                            attempt=attempt + 1,
                            retry_in=wait,
                        )
                        await asyncio.sleep(wait)
                    else:
                        # All retries exhausted → try fallback
                        if fallback_key:
                            logger.warning(
                                "llm_fallback",
                                from_provider=provider,
                                to_provider=fallback_provider,
                            )
                            return await cls._call_llm(
                                fallback_provider, fallback_key,
                                system_prompt, history, user_content,
                            )
                        raise
                else:
                    raise

        return "No response (all retries exhausted)"

    @classmethod
    async def _call_llm(
        cls,
        provider: str,
        api_key: str,
        system_prompt: str,
        history: list[dict],
        user_content: str,
    ) -> str:
        """Make a single LLM API call."""
        import httpx

        async with httpx.AsyncClient(timeout=60.0) as client:
            if provider == "google":
                contents = []
                for hist_msg in history:
                    role = "user" if hist_msg["role"] == "user" else "model"
                    contents.append({"role": role, "parts": [{"text": hist_msg["content"]}]})
                contents.append({"role": "user", "parts": [{"text": user_content}]})

                resp = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}",
                    headers={"Content-Type": "application/json"},
                    json={
                        "system_instruction": {"parts": [{"text": system_prompt}]},
                        "contents": contents,
                        "generationConfig": {"maxOutputTokens": 1024, "temperature": 0.7},
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    return parts[0].get("text", "") if parts else "No response"
                return "No response from model"

            else:  # openai
                messages = [{"role": "system", "content": system_prompt}]
                for hist_msg in history:
                    messages.append({"role": hist_msg["role"], "content": hist_msg["content"]})
                messages.append({"role": "user", "content": user_content})

                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={
                        "model": "gpt-4o-mini",
                        "messages": messages,
                        "max_tokens": 1024,
                        "temperature": 0.7,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]

    @classmethod
    async def _dispatch_reply(cls, task: OrchestrationTask) -> None:
        """Send the agent response back to the user via the same channel.

        Uses ResponseEnvelope if available, falls back to raw agent_response.
        """
        from app.services.orchestration.notification_dispatcher import NotificationDispatcher

        channel = task.message.channel
        recipient = task.message.sender

        # Use envelope if available, fallback to raw response
        reply_text = (
            task.response_envelope.reply_text
            if task.response_envelope
            else task.agent_response
        )
        if not reply_text:
            return

        await NotificationDispatcher.send(
            channel=channel,
            recipient=recipient,
            content=reply_text,
            trace_id=task.trace_id,
            task_id=task.task_id,
        )

        logger.info(
            "dispatch_reply_sent",
            task_id=task.task_id,
            trace_id=task.trace_id,
            channel=channel,
            has_envelope=task.response_envelope is not None,
        )

    @classmethod
    async def _try_agent_executor(
        cls, task: OrchestrationTask
    ) -> str | None:
        """Attempt to execute via AgentExecutorService (full LangGraph pipeline).

        Returns the response text on success, or None to trigger fallback.
        """
        try:
            from app.core.deps import async_session
            from app.services.agent_executor import AgentExecutorService
            from sqlalchemy import select
            from app.models.agent import Agent

            async with async_session() as db:
                # Resolve agent_id from routed agent name
                result = await db.execute(
                    select(Agent).where(
                        Agent.name == task.routing.agent,
                        Agent.department == task.routing.department,
                    )
                )
                agent = result.scalars().first()

                if not agent:
                    logger.info(
                        "agent_executor_skip_no_agent",
                        agent_name=task.routing.agent,
                        department=task.routing.department,
                    )
                    return None

                executor = AgentExecutorService(db)
                result = await executor.chat_with_agent(
                    agent_id=agent.id,
                    message=task.message.content,
                    thread_id=task.trace_id,
                )

                if result.get("status") == "failed":
                    logger.warning(
                        "agent_executor_failed",
                        error=result.get("error"),
                        agent_id=agent.id,
                    )
                    return None

                return result.get("response", "")

        except ImportError:
            logger.debug("agent_executor_import_unavailable")
            return None
        except Exception as e:
            logger.warning(
                "agent_executor_exception",
                error=str(e),
                task_id=task.task_id,
            )
            return None

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
