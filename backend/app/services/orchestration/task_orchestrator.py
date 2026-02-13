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
import asyncio

import structlog

from app.services.orchestration.intent_router import IntentRouter, RoutingResult
from app.services.orchestration.message_gateway import UnifiedMessage
from app.services.orchestration.task_extractor import TaskExtractor
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
    CANCELLED = "cancelled"


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
    _processed_messages: set[str] = set()  # Dedup fallback: channel+msg_id
    _dedup_lock = asyncio.Lock()  # Prevent asyncio race in dedup check

    @classmethod
    async def _is_duplicate(cls, msg_key: str) -> bool:
        """Atomic dedup check: Redis SETNX first, fallback to in-memory set.

        Returns True if this message was already processed (skip it).
        """
        # Try Redis SETNX (atomic, survives restarts)
        try:
            import redis.asyncio as aioredis
            from app.core.config import get_settings
            settings = get_settings()
            r = aioredis.from_url(settings.REDIS_URL)
            # SETNX: returns True only if key was SET (first time)
            was_new = await r.set(f"dedup:{msg_key}", "1", nx=True, ex=300)
            await r.aclose()
            if not was_new:
                return True  # Already processed
            return False
        except Exception:
            pass

        # Fallback: in-memory with lock (no race condition)
        async with cls._dedup_lock:
            if msg_key in cls._processed_messages:
                return True
            cls._processed_messages.add(msg_key)
            # Keep set bounded (max 500)
            if len(cls._processed_messages) > 500:
                cls._processed_messages = set(list(cls._processed_messages)[-250:])
            return False

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

        # ── 0. Deduplicate messages (atomic via Redis or Lock) ──
        raw_msg_id = message.metadata.get("telegram_message_id") or message.metadata.get("message_id") or ""
        if raw_msg_id:
            msg_key = f"{message.channel}:{raw_msg_id}:{message.sender}"
            if await cls._is_duplicate(msg_key):
                logger.info(
                    "orchestration_dedup_skip",
                    msg_key=msg_key,
                    task_id=task_id,
                )
                # Return a dummy cancelled task
                return OrchestrationTask(
                    task_id=task_id,
                    trace_id=trace_id,
                    message=message,
                    routing=RoutingResult(agent="none", department="", confidence=0),
                    status=TaskStatus.CANCELLED,
                )

        # ── 1. Check routing bindings first (OpenClaw pattern) ──
        routing = cls._resolve_binding(message)

        # ── 2. Fallback to IntentRouter keyword matching ──
        if routing is None:
            routing = await IntentRouter.route(
                content=message.content,
                sender_department=message.metadata.get("department", ""),
            )

        # ── 2a. Resolve user identity for chat channels ──
        if message.channel in ("telegram", "whatsapp"):
            user_record = await cls._resolve_chat_user(message)
            if user_record:
                message.metadata["department"] = user_record.department
                message.metadata["user_name"] = user_record.name
                message.metadata["user_id"] = user_record.id
                message.sender_name = user_record.name
                logger.info(
                    "user_identity_resolved",
                    channel=message.channel,
                    user_name=user_record.name,
                    department=user_record.department,
                    sender=message.sender,
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

        # ── 4. Classify message & persist task to DB ──
        db_task_id = None
        is_chat_channel = message.channel in ("telegram", "whatsapp")
        if is_chat_channel:
            try:
                # Pass session history for context-aware classification
                session_messages = session.get_llm_messages()[-6:] if hasattr(session, 'get_llm_messages') else []

                extraction = await TaskExtractor.classify_and_extract(
                    message_content=message.content,
                    sender_name=message.sender_name or message.metadata.get("user_name", ""),
                    department=routing.department or "",
                    session_history=session_messages,
                )
                message_type = extraction.get("type", "task")
                ready_to_create = extraction.get("ready_to_create", False)
                needs_clarification = extraction.get("needs_clarification", False)

                # Only persist to DB when task is READY (all info collected + confirmed)
                if message_type == "task" and ready_to_create and not needs_clarification:
                    db_task_id = await cls._persist_task(
                        task_id=task_id,
                        trace_id=trace_id,
                        title=extraction.get("title", message.content[:100]),
                        description=extraction.get("description", message.content),
                        priority=extraction.get("priority", "P2"),
                        department=routing.department or "general",
                        agent=routing.agent,
                        channel=message.channel,
                        sender_name=message.sender_name or message.metadata.get("user_name", ""),
                        sender_identifier=message.sender,
                        original_message=message.content,
                        submitted_by=message.metadata.get("user_id"),
                    )
                    task.message.metadata["db_task_id"] = db_task_id
                    logger.info(
                        "task_persisted_to_db",
                        task_id=task_id,
                        db_task_id=db_task_id,
                        title=extraction.get("title", "")[:50],
                        message_type=message_type,
                    )
                elif message_type == "task" and needs_clarification:
                    logger.info(
                        "task_needs_clarification",
                        task_id=task_id,
                        message_type=message_type,
                        content_preview=message.content[:50],
                    )
                else:
                    logger.info(
                        "message_classified_non_task",
                        task_id=task_id,
                        message_type=message_type,
                        ready_to_create=ready_to_create,
                        content_preview=message.content[:50],
                    )
            except Exception as e:
                logger.warning("task_extraction_failed", error=str(e), task_id=task_id)

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

        # ── 5. Update DB task with result after execution ──
        if db_task_id:
            try:
                await cls._update_task_result(
                    db_task_id=db_task_id,
                    status="completed" if task.status == TaskStatus.COMPLETED else "failed",
                    agent_response=task.agent_response,
                    result_json={
                        "output": task.agent_response[:2000] if task.agent_response else "",
                        "agent": task.routing.agent,
                        "error": task.error if task.error else None,
                    },
                )
            except Exception as e:
                logger.warning("task_db_update_failed", error=str(e), db_task_id=db_task_id)

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
    async def _resolve_chat_user(cls, message: UnifiedMessage):
        """Look up user identity from chat channel (Telegram/WhatsApp).

        Queries the users table by telegram_chat_id or phone_whatsapp
        to identify the sender and retrieve their department.

        Returns:
            User record if found, None otherwise.
        """
        try:
            from app.core.deps import async_session
            from sqlalchemy import select
            from app.models.user import User

            async with async_session() as db:
                field_map = {
                    "telegram": User.telegram_chat_id,
                    "whatsapp": User.phone_whatsapp,
                }
                column = field_map.get(message.channel)
                if column is None:
                    return None

                result = await db.execute(
                    select(User).where(
                        column == message.sender,
                        User.is_active == True,
                    )
                )
                user = result.scalars().first()

                if user:
                    logger.info(
                        "chat_user_resolved",
                        channel=message.channel,
                        sender=message.sender,
                        user_name=user.name,
                        department=user.department,
                    )
                else:
                    logger.info(
                        "chat_user_unknown",
                        channel=message.channel,
                        sender=message.sender,
                    )
                return user

        except Exception as e:
            logger.warning(
                "chat_user_resolve_error",
                error=str(e),
                channel=message.channel,
                sender=message.sender,
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

            # ── 1. Fallback: Direct LLM call (with tools) ────────
            logger.info(
                "orchestration_fallback_direct_llm",
                task_id=task.task_id,
                reason="agent_executor_unavailable",
            )

            # ── Telemetry: init + workflow_started ────────────
            import uuid as _uuid
            from app.core.telemetry import Telemetry, EventType, now_ms
            _tele = Telemetry(
                agent_id=task.routing.agent or "orchestrator",
                department=task.routing.department or "general",
            )
            _workflow_span = str(_uuid.uuid4())
            _workflow_start_ms = now_ms()
            _tele.emit(
                trace_id=task.trace_id,
                span_id=_workflow_span,
                event_type=EventType.WORKFLOW_STARTED,
                status="running",
                current_step="direct_llm_with_tools",
                summary=f"Orchestrator handling message via direct LLM",
                requester_id=task.message.sender,
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

            # ── 1b. Get available tools ──────────────────────────
            tool_definitions = []
            broker = None
            agent_ctx = None
            try:
                from app.core.tool_broker import get_tool_broker
                from app.core.llm_client import AgentContext

                broker = get_tool_broker()
                tool_definitions = broker.get_available_tools(
                    role=task.routing.agent or "agent",
                    department=task.routing.department,
                )
                agent_ctx = AgentContext(
                    agent_id=task.routing.agent,
                    agent_name=task.routing.agent,
                    department=task.routing.department,
                    trace_id=task.trace_id,
                    task_id=task.task_id,
                )
                logger.info(
                    "tools_loaded",
                    task_id=task.task_id,
                    tool_count=len(tool_definitions),
                )
            except Exception as e:
                logger.debug("tools_load_failed", error=str(e))

            # ── 2. Get LLM provider + API key ────────────────
            provider = "google"
            api_key = ""
            fallback_provider = ""
            fallback_key = ""

            try:
                import redis.asyncio as aioredis
                redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
                r = aioredis.from_url(redis_url, decode_responses=True)
                provider = await r.get("settings:provider") or "google"
                key_from_redis = await r.get(f"settings:{provider}_api_key")
                if key_from_redis:
                    api_key = key_from_redis
                await r.aclose()
            except Exception:
                pass

            if not api_key:
                from app.core.config import get_settings
                _settings = get_settings()
                env_map = {"google": "GOOGLE_API_KEY", "openai": "OPENAI_API_KEY"}
                api_key = getattr(_settings, env_map.get(provider, "GOOGLE_API_KEY"), "") or os.environ.get(env_map.get(provider, "GOOGLE_API_KEY"), "")

            # Prepare fallback provider
            if provider == "google":
                fallback_provider = "openai"
                from app.core.config import get_settings
                _settings = get_settings()
                fallback_key = _settings.OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY", "")
            else:
                fallback_provider = "google"
                from app.core.config import get_settings
                _settings = get_settings()
                fallback_key = _settings.GOOGLE_API_KEY or os.environ.get("GOOGLE_API_KEY", "")

            if not api_key:
                task.agent_response = (
                    f"⚠️ No API key configured for '{provider}'. "
                    "Please set one in the Configurations page."
                )
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.now(timezone.utc)
                await cls._dispatch_reply(task)
                return

            # ── 3. Call LLM (with tools + execution loop) ────
            user_content = task.message.content

            # ── Guard rail: input length cap ──
            MAX_INPUT_LENGTH = 4000
            if len(user_content) > MAX_INPUT_LENGTH:
                logger.warning(
                    "input_truncated",
                    task_id=task.task_id,
                    original_len=len(user_content),
                    max_len=MAX_INPUT_LENGTH,
                )
                user_content = user_content[:MAX_INPUT_LENGTH] + "\n[... truncated]"

            # Build conversation history from session
            history_messages = []
            if session and len(session.history) > 1:
                for msg in session.history[:-1]:
                    history_messages.append(msg)

            # ── Guard rail: history truncation ──
            MAX_HISTORY_MESSAGES = 20
            if len(history_messages) > MAX_HISTORY_MESSAGES:
                history_messages = history_messages[-MAX_HISTORY_MESSAGES:]

            # Initial LLM call
            llm_response = await cls._call_llm_with_fallback(
                provider=provider,
                api_key=api_key,
                fallback_provider=fallback_provider,
                fallback_key=fallback_key,
                system_prompt=system_prompt,
                history=history_messages,
                user_content=user_content,
                tools=tool_definitions if tool_definitions else None,
            )

            # ── 3a. Tool execution loop ──────────────────────
            # Budget controls
            MAX_TOOL_ITERATIONS = 5
            MAX_TOOL_CALLS = 10
            MAX_TOOL_TIMEOUT_S = 60
            total_tool_calls = 0
            tool_start_time = datetime.now(timezone.utc)
            tool_messages = []  # accumulate tool call/result messages
            approval_pending = False

            for iteration in range(MAX_TOOL_ITERATIONS):
                tool_calls = cls._extract_tool_calls(llm_response, provider)
                if not tool_calls:
                    break

                logger.info(
                    "tool_calls_received",
                    task_id=task.task_id,
                    iteration=iteration + 1,
                    tool_count=len(tool_calls),
                    tools=[tc["name"] for tc in tool_calls],
                )

                for tc in tool_calls:
                    # Budget check
                    total_tool_calls += 1
                    if total_tool_calls > MAX_TOOL_CALLS:
                        logger.warning("tool_budget_exceeded", task_id=task.task_id, limit="max_calls")
                        tool_messages.append({
                            "role": "tool",
                            "tool_call_id": tc.get("id", ""),
                            "name": tc["name"],
                            "content": "Error: Tool call budget exceeded (max 10 calls per request).",
                        })
                        break

                    # Timeout check
                    elapsed = (datetime.now(timezone.utc) - tool_start_time).total_seconds()
                    if elapsed > MAX_TOOL_TIMEOUT_S:
                        logger.warning("tool_timeout", task_id=task.task_id, elapsed_s=elapsed)
                        tool_messages.append({
                            "role": "tool",
                            "tool_call_id": tc.get("id", ""),
                            "name": tc["name"],
                            "content": "Error: Tool execution timeout exceeded (60s).",
                        })
                        break

                    # Execute tool via ToolBroker (safety chokepoint)
                    if broker and agent_ctx:
                        try:
                            _tool_start = now_ms()
                            result = await broker.execute(agent_ctx, tc["name"], tc.get("args", {}))
                            _tool_dur = now_ms() - _tool_start

                            if result.status == "needs_approval":
                                approval_pending = True
                                tool_messages.append({
                                    "role": "tool",
                                    "tool_call_id": tc.get("id", ""),
                                    "name": tc["name"],
                                    "content": f"⏳ Tool '{tc['name']}' requires human approval (approval_id: {result.approval_id}). Execution paused.",
                                })
                                # Telemetry: approval_requested
                                _tele.emit(
                                    trace_id=task.trace_id,
                                    span_id=str(_uuid.uuid4()),
                                    parent_span_id=_workflow_span,
                                    event_type=EventType.APPROVAL_REQUESTED,
                                    tool_name=tc["name"],
                                    approval_request_id=result.approval_id,
                                    latency_ms=_tool_dur,
                                )
                                logger.info(
                                    "tool_approval_required",
                                    task_id=task.task_id,
                                    tool=tc["name"],
                                    approval_id=result.approval_id,
                                )

                                # ── Component 4: Notify approver ──
                                try:
                                    from app.services.orchestration.notification_dispatcher import NotificationDispatcher
                                    notify_msg = (
                                        f"🔔 **Approval Required**\n\n"
                                        f"**Tool:** {tc['name']}\n"
                                        f"**Agent:** {agent_ctx.agent_name}\n"
                                        f"**Department:** {agent_ctx.department}\n"
                                        f"**Approval ID:** {result.approval_id}\n"
                                        f"**Trace:** {task.trace_id}\n\n"
                                        f"Reply **approve** or **reject** to this message."
                                    )
                                    # Send to supervisor channel (Telegram)
                                    supervisor_chat = os.environ.get("SUPERVISOR_CHAT_ID", "")
                                    if supervisor_chat:
                                        await NotificationDispatcher.send(
                                            channel="telegram",
                                            recipient=supervisor_chat,
                                            content=notify_msg,
                                            trace_id=task.trace_id,
                                        )
                                except Exception as notify_err:
                                    logger.warning(
                                        "approver_notify_failed",
                                        error=str(notify_err),
                                    )

                                break  # Stop processing more tool calls

                            # Telemetry: tool_call event
                            _tele.emit(
                                trace_id=task.trace_id,
                                span_id=str(_uuid.uuid4()),
                                parent_span_id=_workflow_span,
                                event_type=EventType.TOOL_CALLED if result.success else EventType.TOOL_FAILED,
                                tool_name=tc["name"],
                                latency_ms=_tool_dur,
                                status="success" if result.success else "failed",
                                error_message_short=result.error[:200] if result.error else None,
                            )

                            # Successful tool execution
                            tool_output = str(result.output) if result.success else f"Error: {result.error}"
                            tool_messages.append({
                                "role": "tool",
                                "tool_call_id": tc.get("id", ""),
                                "name": tc["name"],
                                "content": tool_output[:2000],  # Truncate large outputs
                            })
                            logger.info(
                                "tool_executed",
                                task_id=task.task_id,
                                tool=tc["name"],
                                success=result.success,
                                time_ms=result.execution_time_ms,
                            )

                        except Exception as e:
                            tool_messages.append({
                                "role": "tool",
                                "tool_call_id": tc.get("id", ""),
                                "name": tc["name"],
                                "content": f"Error executing tool: {str(e)[:500]}",
                            })
                            logger.warning(
                                "tool_execution_error",
                                task_id=task.task_id,
                                tool=tc["name"],
                                error=str(e),
                            )
                    else:
                        tool_messages.append({
                            "role": "tool",
                            "tool_call_id": tc.get("id", ""),
                            "name": tc["name"],
                            "content": "Error: Tool broker unavailable.",
                        })

                if approval_pending:
                    break

                # Re-call LLM with tool results
                llm_response = await cls._call_llm_with_fallback(
                    provider=provider,
                    api_key=api_key,
                    fallback_provider=fallback_provider,
                    fallback_key=fallback_key,
                    system_prompt=system_prompt,
                    history=history_messages,
                    user_content=user_content,
                    tools=tool_definitions if tool_definitions else None,
                    tool_messages=tool_messages,
                )

            # ── 4. Extract final text response ───────────────
            response_text = cls._extract_text_response(llm_response, provider)

            # If approval is pending, prepend info
            if approval_pending:
                response_text = (
                    "⏳ Aksi ini membutuhkan approval dari supervisor. "
                    "Saya akan melanjutkan setelah approval diberikan.\n\n"
                    + response_text
                )

            # ── 5. Shape response (dual-output for chat) ─────
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

            # ── 6. Build ResponseEnvelope ─────────────────────
            latency_ms = 0
            if task.completed_at and task.started_at:
                latency_ms = int(
                    (task.completed_at - task.started_at).total_seconds() * 1000
                )
            task.response_envelope = ResponseEnvelope(
                trace_id=task.trace_id,
                run_id=task.task_id,
                reply_text=task.agent_response,
                control={
                    "stop_reason": "completed",
                    "tool_calls_total": total_tool_calls,
                    "approval_pending": approval_pending,
                },
                telemetry={
                    "latency_ms": latency_ms,
                    "provider": provider,
                    "routing_method": task.routing.routing_method,
                    "execution_path": "direct_llm_with_tools",
                    "tool_iterations": min(iteration + 1, MAX_TOOL_ITERATIONS) if tool_definitions else 0,
                },
            )

            # Save assistant response to session history
            if session:
                session.add_message("assistant", task.agent_response)
                await SessionManager.save_session(session)

            # Telemetry: workflow_completed
            _tele.emit(
                trace_id=task.trace_id,
                span_id=_workflow_span,
                event_type=EventType.WORKFLOW_COMPLETED,
                status="completed",
                latency_ms=latency_ms,
                summary=f"Completed with {total_tool_calls} tool calls",
                provider=provider,
            )

            logger.info(
                "orchestration_task_completed",
                task_id=task.task_id,
                trace_id=task.trace_id,
                agent=task.routing.agent,
                department=task.routing.department,
                routing_method=task.routing.routing_method,
                response_len=len(task.agent_response),
                latency_ms=latency_ms,
                tool_calls_total=total_tool_calls,
            )

            # ── 7. Send reply back to user ───────────────────
            await cls._dispatch_reply(task)

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)

            # Telemetry: workflow_failed
            try:
                _tele.emit(
                    trace_id=task.trace_id,
                    span_id=_workflow_span,
                    event_type=EventType.WORKFLOW_FAILED,
                    status="failed",
                    latency_ms=now_ms() - _workflow_start_ms,
                    error_class=type(e).__name__,
                    error_message_short=str(e)[:200],
                )
            except Exception:
                pass  # Telemetry failure itself must not break error handling

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
        tools: list[dict] | None = None,
        tool_messages: list[dict] | None = None,
    ) -> dict:
        """Call LLM with retry (3x backoff) and auto-fallback on 429.

        Returns raw response data (dict) to support tool call extraction.
        """
        import asyncio
        import httpx

        max_retries = 3

        # Try primary provider with retries
        for attempt in range(max_retries):
            try:
                result = await cls._call_llm(
                    provider, api_key, system_prompt, history,
                    user_content, tools, tool_messages,
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
                                tools, tool_messages,
                            )
                        raise
                else:
                    raise

        return {"text": "No response (all retries exhausted)", "provider": provider}

    @classmethod
    async def _call_llm(
        cls,
        provider: str,
        api_key: str,
        system_prompt: str,
        history: list[dict],
        user_content: str,
        tools: list[dict] | None = None,
        tool_messages: list[dict] | None = None,
    ) -> dict:
        """Make a single LLM API call.

        Returns a dict with structure:
        - {"text": "...", "provider": "..."} for text responses
        - {"tool_calls": [...], "provider": "..."} for tool call responses
        """
        import httpx
        import json

        async with httpx.AsyncClient(timeout=60.0) as client:
            if provider == "google":
                contents = []
                for hist_msg in history:
                    role = "user" if hist_msg["role"] == "user" else "model"
                    contents.append({"role": role, "parts": [{"text": hist_msg["content"]}]})
                contents.append({"role": "user", "parts": [{"text": user_content}]})

                # Add tool call/result history for multi-turn tool use
                if tool_messages:
                    for tm in tool_messages:
                        if tm["role"] == "tool":
                            # Gemini uses functionResponse parts
                            contents.append({
                                "role": "user",
                                "parts": [{
                                    "functionResponse": {
                                        "name": tm["name"],
                                        "response": {"result": tm["content"]},
                                    }
                                }],
                            })

                # Build request body
                request_body: dict = {
                    "system_instruction": {"parts": [{"text": system_prompt}]},
                    "contents": contents,
                    "generationConfig": {"maxOutputTokens": 1024, "temperature": 0.7},
                }

                # Add tools if available
                if tools:
                    gemini_tools = []
                    for t in tools:
                        func = t.get("function", {})
                        func_decl: dict = {
                            "name": func.get("name", ""),
                            "description": func.get("description", ""),
                        }
                        params = func.get("parameters")
                        if params and params.get("properties"):
                            func_decl["parameters"] = params
                        gemini_tools.append(func_decl)

                    if gemini_tools:
                        request_body["tools"] = [{"function_declarations": gemini_tools}]

                resp = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}",
                    headers={"Content-Type": "application/json"},
                    json=request_body,
                )
                resp.raise_for_status()
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    # Check for function calls
                    function_calls = [
                        p["functionCall"] for p in parts
                        if "functionCall" in p
                    ]
                    if function_calls:
                        tool_calls = []
                        for i, fc in enumerate(function_calls):
                            tool_calls.append({
                                "id": f"call_{i}",
                                "name": fc.get("name", ""),
                                "args": fc.get("args", {}),
                            })
                        return {"tool_calls": tool_calls, "provider": "google"}

                    # Text response
                    text = parts[0].get("text", "") if parts else "No response"
                    return {"text": text, "provider": "google"}
                return {"text": "No response from model", "provider": "google"}

            else:  # openai
                messages = [{"role": "system", "content": system_prompt}]
                for hist_msg in history:
                    messages.append({"role": hist_msg["role"], "content": hist_msg["content"]})
                messages.append({"role": "user", "content": user_content})

                # Add tool call/result history
                if tool_messages:
                    for tm in tool_messages:
                        messages.append(tm)

                request_body = {
                    "model": "gpt-4o-mini",
                    "messages": messages,
                    "max_tokens": 1024,
                    "temperature": 0.7,
                }

                # Add tools if available
                if tools:
                    request_body["tools"] = tools

                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=request_body,
                )
                resp.raise_for_status()
                data = resp.json()
                msg = data["choices"][0]["message"]

                # Check for tool calls
                if msg.get("tool_calls"):
                    tool_calls = []
                    for tc in msg["tool_calls"]:
                        args_str = tc.get("function", {}).get("arguments", "{}")
                        try:
                            args = json.loads(args_str)
                        except json.JSONDecodeError:
                            args = {}
                        tool_calls.append({
                            "id": tc.get("id", ""),
                            "name": tc.get("function", {}).get("name", ""),
                            "args": args,
                        })
                    return {"tool_calls": tool_calls, "provider": "openai"}

                return {"text": msg.get("content", ""), "provider": "openai"}

    # ── Tool response helpers ─────────────────────────────────
    @staticmethod
    def _extract_tool_calls(llm_response: dict, provider: str) -> list[dict]:
        """Extract tool calls from LLM response.

        Returns list of {"id": "...", "name": "...", "args": {...}}
        """
        return llm_response.get("tool_calls", [])

    @staticmethod
    def _extract_text_response(llm_response: dict, provider: str) -> str:
        """Extract final text from LLM response."""
        return llm_response.get("text", "")


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

        # Prepend task ID notification for chat-originated tasks
        db_task_id = task.message.metadata.get("db_task_id")
        if db_task_id and channel in ("telegram", "whatsapp"):
            reply_text = f"\u2705 Task #{db_task_id[:8]} tercatat.\n\n{reply_text}"

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

    # ── DB Persistence Helpers ────────────────────────────────

    @classmethod
    async def _persist_task(
        cls,
        task_id: str,
        trace_id: str,
        title: str,
        description: str,
        priority: str,
        department: str,
        agent: str,
        channel: str,
        sender_name: str,
        sender_identifier: str,
        original_message: str,
        submitted_by: str | None = None,
    ) -> str:
        """Insert a new Task record into the database.

        Returns the DB task ID.
        """
        from app.core.deps import async_session
        from app.models.task import Task
        from sqlalchemy import select
        from app.models.agent import Agent

        async with async_session() as db:
            # Try to resolve agent ID
            agent_id = None
            try:
                result = await db.execute(
                    select(Agent.id).where(Agent.name == agent)
                )
                row = result.scalar_one_or_none()
                if row:
                    agent_id = row
            except Exception:
                pass

            db_task = Task(
                id=task_id,
                title=title,
                description=description,
                priority=priority,
                department=department,
                status="running",
                assigned_agent_id=agent_id,
                submitted_by=submitted_by,
                channel=channel,
                sender_name=sender_name,
                sender_identifier=sender_identifier,
                trace_id=trace_id,
                original_message=original_message,
            )
            db.add(db_task)
            await db.commit()

            logger.info(
                "task_db_inserted",
                task_id=task_id,
                title=title[:50],
                department=department,
                channel=channel,
            )
            return task_id

    @classmethod
    async def _update_task_result(
        cls,
        db_task_id: str,
        status: str,
        agent_response: str,
        result_json: dict | None = None,
    ) -> None:
        """Update an existing Task with execution results."""
        from app.core.deps import async_session
        from app.models.task import Task
        from sqlalchemy import select

        async with async_session() as db:
            result = await db.execute(
                select(Task).where(Task.id == db_task_id)
            )
            db_task = result.scalar_one_or_none()
            if not db_task:
                logger.warning("task_db_update_not_found", db_task_id=db_task_id)
                return

            db_task.status = status
            db_task.agent_response = agent_response
            if result_json:
                db_task.result_json = result_json
            await db.commit()

            logger.info(
                "task_db_updated",
                db_task_id=db_task_id,
                status=status,
                response_len=len(agent_response) if agent_response else 0,
            )

    @classmethod
    def get_pending_approvals(cls) -> list[OrchestrationTask]:
        """Get all tasks waiting for approval."""
        return [
            t for t in cls._tasks.values()
            if t.status == TaskStatus.WAITING_APPROVAL
        ]
