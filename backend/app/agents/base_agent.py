"""
BaseAgent — Abstract base class for all enterprise agents.

Every specialist agent (Tech, Finance, HR, etc.) inherits from this class.

IMPORTANT — Single Chokepoint Architecture:
  Agents may ONLY interact with external systems through 3 injected gateways:
  - self._llm    → LLMClient  (all LLM calls)
  - self._broker → ToolBroker (all tool executions)
  - self._dal    → DataAccessLayer (all data access)

  Direct imports of httpx, requests, psycopg, or sqlalchemy in agent code
  are FORBIDDEN and will be caught by CI lint checks.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from abc import ABC, abstractmethod
from collections import Counter
from typing import Any, Type

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError

from app.agents.state import AgentState
from app.core.artifact_store import get_artifact_store
from app.core.config import get_settings
from app.core.llm_client import AgentContext, LLMClient, LLMResponse
from app.core.policy_engine import (
    PolicyAction,
    PolicyContext,
    PolicyDecision,
    get_policy_engine,
)
from app.core.telemetry import Telemetry, now_ms

logger = structlog.get_logger()
settings = get_settings()


class RateLimitExceeded(Exception):
    """Raised when an agent exceeds its configured rate limits."""

    def __init__(self, limit_type: str, current: int, maximum: int):
        self.limit_type = limit_type
        self.current = current
        self.maximum = maximum
        super().__init__(f"{limit_type} limit exceeded: {current}/{maximum}")


class LoopDetected(Exception):
    """Raised when an agent is stuck in a repetitive loop."""

    def __init__(self, tool_name: str, count: int):
        self.tool_name = tool_name
        self.count = count
        super().__init__(f"Loop detected: tool '{tool_name}' called {count} times with similar args")


class BaseAgent(ABC):
    """Abstract base class for enterprise agents.

    Subclasses must implement:
        - get_system_prompt() -> str
        - process(state: AgentState) -> AgentState

    Agents interact with the world ONLY through:
        - self.call_llm()  → routes to LLMClient
        - self.call_tool() → routes to ToolBroker
        - self._dal        → DataAccessLayer (for direct DB if needed)
    """

    def __init__(
        self,
        agent_id: str,
        name: str,
        department: str,
        tier: str = "standard",
        config: dict[str, Any] | None = None,
        llm_client: LLMClient | None = None,
        tool_broker: "ToolBroker | None" = None,
        dal: "DataAccessLayer | None" = None,
    ):
        self.agent_id = agent_id
        self.name = name
        self.department = department
        self.tier = tier
        self.config = config or {}

        # ── Injected chokepoint gateways ──
        self._llm = llm_client
        self._broker = tool_broker
        self._dal = dal

        # Rate limiting defaults (can be overridden per-agent via config)
        self.max_tool_calls: int = int(
            self.config.get("max_tool_calls", settings.AGENT_MAX_TOOL_CALLS)
        )
        self.max_tokens: int = int(
            self.config.get("max_tokens", settings.AGENT_MAX_TOKENS)
        )
        self.max_execution_time: int = int(
            self.config.get("max_execution_time", settings.AGENT_MAX_EXECUTION_TIME)
        )
        self.loop_threshold: int = int(
            self.config.get("loop_threshold", settings.AGENT_LOOP_DETECTION_THRESHOLD)
        )

        # ── Prompt override from DB (set by admin dashboard) ──
        self._prompt_override: str | None = self.config.get("system_prompt_override")

        # Internal tracking
        self._tool_call_hashes: Counter = Counter()
        self._start_time: float | None = None

        self.log = logger.bind(agent=self.name, department=self.department)

    def get_context(
        self,
        task_id: str = "",
        trace_id: str = "",
        span_id: str = "",
        department: str = "",
        role: str = "",
        risk_level: str = "",
        requester_id: str = "",
    ) -> AgentContext:
        """Create an AgentContext for this agent.

        Used by call_llm() and call_tool() for tracing and policy.
        Accepts optional overrides for department, role, risk_level.
        """
        return AgentContext(
            agent_id=self.agent_id,
            agent_name=self.name,
            department=department or self.department,
            tier=self.tier,
            role=role or "agent",
            task_id=task_id,
            trace_id=trace_id or "",
            span_id=span_id or "",
            requester_id=requester_id or "",
        )

    # ── System prompt with DB override ──────────────

    def get_system_prompt(self) -> str:
        """Return the system prompt for this agent.

        Priority:
        1. DB override (set by admin via dashboard)
        2. Subclass default (hardcoded in each agent)
        """
        if self._prompt_override:
            self.log.debug("using_db_prompt_override", agent=self.name)
            return self._prompt_override
        return self._default_system_prompt()

    @abstractmethod
    def _default_system_prompt(self) -> str:
        """Return the hardcoded default system prompt.

        Subclasses implement this instead of get_system_prompt().
        The admin dashboard can override this at runtime via DB.
        """
        ...

    @abstractmethod
    async def process(self, state: AgentState) -> AgentState:
        """Process the current state and return updated state.

        This is the main execution logic of the agent. Subclasses implement
        their specific behavior here (code generation, analysis, etc.).
        """
        ...

    # ── LLM Interaction (via LLMClient chokepoint) ───

    async def call_llm(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        ctx: AgentContext | None = None,
    ) -> LLMResponse:
        """Call LLM via the LLMClient chokepoint.

        All budget, audit, and tracing controls are enforced by LLMClient.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            tools: Optional tool definitions for function calling.
            temperature: Sampling temperature.
            ctx: Optional explicit AgentContext (auto-created if not provided).

        Returns:
            Structured LLMResponse with content, tokens, cost.

        Raises:
            RuntimeError: If LLMClient is not injected.
        """
        if self._llm is None:
            from app.core.llm_client import get_llm_client
            self._llm = get_llm_client()

        if ctx is None:
            ctx = self.get_context()

        return await self._llm.call(ctx, messages, tools, temperature)

    # ── Tool Execution (via ToolBroker chokepoint) ───

    async def call_tool(
        self,
        tool_name: str,
        args: dict[str, Any],
        ctx: AgentContext | None = None,
    ) -> "ToolResult":
        """Execute a tool via the ToolBroker chokepoint.

        All registry, policy, egress, and sandbox checks are enforced
        by ToolBroker. Agents cannot bypass this.

        Args:
            tool_name: Name of the registered tool.
            args: Arguments to pass to the tool handler.
            ctx: Optional explicit AgentContext.

        Returns:
            ToolResult with output, success status, and artifacts.

        Raises:
            ToolNotFound: If tool is not in the registry.
            ToolAccessDenied: If this agent can't use the tool.
            RuntimeError: If ToolBroker is not injected.
        """
        if self._broker is None:
            from app.core.tool_broker import get_tool_broker
            self._broker = get_tool_broker()

        if ctx is None:
            ctx = self.get_context()

        return await self._broker.execute(ctx, tool_name, args)

    # ── Rate Limiting ────────────────────────────

    def check_rate_limits(self, state: AgentState) -> None:
        """Check all rate limits and raise if any are exceeded.

        Args:
            state: Current agent state with counters.

        Raises:
            RateLimitExceeded: If any limit is exceeded.
        """
        # Tool call limit
        if state["tool_call_count"] >= state["max_tool_calls"]:
            raise RateLimitExceeded(
                "tool_calls", state["tool_call_count"], state["max_tool_calls"]
            )

        # Token budget
        if state["token_usage"] >= state["max_tokens"]:
            raise RateLimitExceeded(
                "tokens", state["token_usage"], state["max_tokens"]
            )

        # Execution time
        if self._start_time is not None:
            elapsed = time.time() - self._start_time
            if elapsed >= self.max_execution_time:
                raise RateLimitExceeded(
                    "execution_time", int(elapsed), self.max_execution_time
                )

    def check_loop_detection(self, tool_name: str, tool_args: dict) -> None:
        """Detect if agent is stuck calling the same tool repeatedly.

        Args:
            tool_name: Name of the tool being called.
            tool_args: Arguments passed to the tool.

        Raises:
            LoopDetected: If the same tool+args pattern exceeds threshold.
        """
        # Hash the tool call signature for comparison
        call_sig = f"{tool_name}:{hashlib.md5(str(sorted(tool_args.items())).encode()).hexdigest()}"
        self._tool_call_hashes[call_sig] += 1

        if self._tool_call_hashes[call_sig] >= self.loop_threshold:
            raise LoopDetected(tool_name, self._tool_call_hashes[call_sig])

    # ── Execution Pipeline ───────────────────────

    async def execute(self, state: AgentState) -> AgentState:
        """Full execution pipeline with safety checks.

        Pipeline: start_timer → check_limits → process → update_state

        Args:
            state: Initial agent state.

        Returns:
            Updated agent state after execution.
        """
        self._start_time = time.time()
        state["status"] = "running"

        self.log.info(
            "agent_execution_start",
            task=state["current_task"],
            task_id=state["task_id"],
            trace_id=state.get("trace_id", ""),
        )

        try:
            # Check rate limits before processing
            self.check_rate_limits(state)

            # Run the agent's main processing logic
            state = await self.process(state)

            # Mark as completed if still running (not waiting for approval)
            if state["status"] == "running":
                state["status"] = "completed"

        except RateLimitExceeded as e:
            self.log.warning("rate_limit_exceeded", error=str(e))
            state["status"] = "failed"
            state["errors"] = state.get("errors", []) + [str(e)]

        except LoopDetected as e:
            self.log.warning("loop_detected", error=str(e))
            state["status"] = "failed"
            state["errors"] = state.get("errors", []) + [str(e)]

        except Exception as e:
            self.log.error("agent_execution_error", error=str(e), exc_info=True)
            state["status"] = "failed"
            state["errors"] = state.get("errors", []) + [f"Unexpected error: {str(e)}"]

        finally:
            elapsed = time.time() - self._start_time if self._start_time is not None else 0.0
            self.log.info(
                "agent_execution_end",
                status=state["status"],
                elapsed_ms=int(elapsed * 1000),
                tool_calls=state["tool_call_count"],
                tokens=state["token_usage"],
                trace_id=state.get("trace_id", ""),
            )

        return state

    # ── Helpers ──────────────────────────────────

    def build_messages(self, state: AgentState) -> list[dict[str, str]]:
        """Convert AgentState messages to LiteLLM-compatible format.

        Prepends the system prompt and converts LangChain message objects
        to simple dicts.
        """
        messages = [{"role": "system", "content": self.get_system_prompt()}]

        for msg in state.get("messages", []):
            if isinstance(msg, SystemMessage):
                messages.append({"role": "system", "content": str(msg.content)})
            elif isinstance(msg, HumanMessage):
                messages.append({"role": "user", "content": str(msg.content)})
            elif isinstance(msg, AIMessage):
                messages.append({"role": "assistant", "content": str(msg.content)})
            elif isinstance(msg, dict):
                messages.append(msg)

        return messages

    # ── V3 Production Helpers ─────────────────────

    @staticmethod
    def mask_fields(text: str, fields: list[str]) -> str:
        """Mask sensitive fields in text before sending to LLM.

        Replaces patterns like `"field_name": "value"` with `"field_name": "[MASKED]"`.
        Also masks simple `field_name: value` patterns.
        """
        masked = text
        for field in fields:
            # JSON-style: "field": "value"
            masked = re.sub(
                rf'"{re.escape(field)}"\s*:\s*"[^"]*"',
                f'"{field}": "[MASKED]"',
                masked,
            )
            # YAML/text-style: field: value
            masked = re.sub(
                rf'{re.escape(field)}\s*:\s*\S+',
                f'{field}: [MASKED]',
                masked,
            )
        return masked

    def _create_telemetry(self) -> Telemetry:
        """Create a Telemetry instance for this agent."""
        return Telemetry(agent_id=self.name, department=self.department)

    def _policy_gate(
        self,
        state: dict[str, Any],
        *,
        trace_id: str,
        span_id: str,
        parent_span_id: str | None,
        telemetry: Telemetry,
        current_step: str,
    ) -> tuple[PolicyDecision, dict[str, Any] | None]:
        """Run ABAC policy check. Returns (decision, early_return_state_or_None).

        If decision is DENY or REQUIRE_APPROVAL, returns a pre-built state
        dict that the caller should return immediately. Otherwise returns None
        as the second element, meaning the caller can proceed.
        """
        risk_level = state.get("risk_level", "medium")
        data_sensitivity = state.get("data_sensitivity", "internal")
        approval_chain = state.get("approval_chain", [])

        ctx = self.get_context(
            task_id=state.get("task_id", ""),
            trace_id=trace_id,
        )

        policy_engine = get_policy_engine(state.get("policy_rules_path"))
        pctx = PolicyContext(
            agent_id=getattr(ctx, "agent_id", self.name),
            department=state.get("department", self.department),
            role=state.get("role", "agent"),
            tier=state.get("tier", self.tier),
            action="llm_call",
            resource=f"model:{self.name}",
            risk_level=risk_level,
            data_sensitivity=data_sensitivity,
            has_ticket_id=bool(state.get("ticket_id")),
            approval_chain=approval_chain,
            time_of_day=state.get("time_of_day", ""),
            metadata={"task_id": state.get("task_id", ""), "trace_id": trace_id},
        )

        decision = policy_engine.evaluate(pctx)

        telemetry.emit(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            event_type="policy_evaluated",
            decision=decision.action.value,
            reason=decision.reason,
            risk_level=risk_level,
            data_sensitivity=data_sensitivity,
            requester_id=state.get("requester_id"),
            resource=f"model:{self.name}",
            current_step=current_step,
            approval_chain=approval_chain,
        )

        if decision.action == PolicyAction.DENY:
            telemetry.emit(
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                event_type="step_failed",
                status="failed",
                decision="deny",
                reason=decision.reason,
                error_code="policy_denied",
                error_class="PolicyDenied",
                error_message_short=decision.reason[:200] if decision.reason else "",
                risk_level=risk_level,
                data_sensitivity=data_sensitivity,
                current_step=current_step,
            )
            return decision, {
                **state,
                "trace_id": trace_id,
                "span_id": span_id,
                "status": "failed",
                "current_agent": self.name,
                "error": decision.reason,
            }

        if decision.action == PolicyAction.REQUIRE_APPROVAL:
            required_roles: list[str] = []
            if decision.obligations and decision.obligations.notify_roles:
                required_roles = list(decision.obligations.notify_roles)

            telemetry.emit(
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                event_type="approval_requested",
                status="pending",
                decision="require_approval",
                reason=decision.reason,
                risk_level=risk_level,
                data_sensitivity=data_sensitivity,
                current_step=current_step,
                approval_required_roles=required_roles,
                approval_chain=approval_chain,
            )
            return decision, {
                **state,
                "trace_id": trace_id,
                "span_id": span_id,
                "status": "needs_approval",
                "current_agent": self.name,
                "approval_required": True,
                "required_approvals": required_roles,
                "approval_reason": decision.reason,
            }

        # ALLOW — caller proceeds
        return decision, None

    @staticmethod
    def _safe_json_loads(text: str) -> dict:
        """Graceful JSON parse that never crashes.

        Returns parsed dict on success, or {"raw_response": text} on failure.
        Handles non-dict JSON values by wrapping them.
        """
        try:
            obj = json.loads(text)
            return obj if isinstance(obj, dict) else {"value": obj}
        except Exception:
            return {"raw_response": text}

    @staticmethod
    def _parse_and_validate(
        raw_text: str, schema: Type[BaseModel]
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Parse JSON + validate with Pydantic schema.

        Uses graceful degradation:
        - Pydantic v2 (model_validate) tried first, then v1 fallback.
        - Returns (parsed_dict, None) on success.
        - Returns (None, error_message) on failure.
        """
        try:
            raw = json.loads(raw_text)
            # Pydantic v2
            if hasattr(schema, "model_validate"):
                parsed = schema.model_validate(raw).model_dump()
            else:
                # Pydantic v1 fallback
                parsed = schema(**raw).dict()
            return parsed, None
        except (json.JSONDecodeError, ValidationError) as e:
            return None, str(e)[:200]

    def _build_output(
        self,
        *,
        status: str,
        summary: str,
        task_id: str = "",
        artifact_id: str = "",
        artifact_type: str = "",
        telemetry: dict[str, Any] | None = None,
        errors: list[str] | None = None,
    ) -> dict[str, Any]:
        """Build a standardized output envelope (AgentOutputSchema-compatible).

        Works with Pydantic v1 and v2. Falls back to a stable dict if
        schema validation fails.
        """
        from app.agents.contracts import AgentOutputSchema, ArtifactRef

        artifacts = []
        if artifact_id:
            artifacts.append(ArtifactRef(
                artifact_id=artifact_id,
                artifact_type=artifact_type or "document",
            ))

        payload = {
            "task_id": task_id,
            "status": status,
            "summary": summary,
            "artifacts": artifacts,
            "token_usage": (telemetry or {}).get("tokens_used", 0),
            "execution_time_ms": (telemetry or {}).get("duration_ms", 0),
            "errors": errors or [],
        }
        try:
            if hasattr(AgentOutputSchema, "model_validate"):
                model = AgentOutputSchema.model_validate(payload)
                return model.model_dump()
            model = AgentOutputSchema(**payload)
            return model.dict()
        except Exception as e:
            logger.warning("output_schema_failed", agent=self.name, error=str(e))
            return {
                "status": status,
                "summary": summary,
                "artifacts": {"primary_artifact_id": artifact_id},
                "errors": errors or [],
            }

    def _emit_lifecycle(
        self,
        event_type: str,
        ctx: AgentContext,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Emit a structured lifecycle event via Telemetry.

        Uses the real Telemetry.emit_lifecycle() method.
        Never crashes — failures are silently logged.
        """
        try:
            tele = self._create_telemetry()
            tele.emit_lifecycle(event_type, ctx, payload)
        except Exception:
            pass  # Telemetry failures are non-fatal

    @staticmethod
    def _validate_output(
        raw: dict[str, Any],
        schema: Type[BaseModel],
    ) -> dict[str, Any]:
        """Validate a raw LLM dict against a Pydantic output schema.

        Returns validated dict on success, or the original raw dict
        on failure (graceful degradation). This makes agent schema
        imports useful rather than dead weight.
        """
        try:
            if hasattr(schema, "model_validate"):
                return schema.model_validate(raw).model_dump()
            return schema(**raw).dict()  # type: ignore[arg-type]
        except Exception:
            return raw

    async def _store_artifact(
        self,
        *,
        trace_id: str,
        task_id: str,
        span_id: str = "",
        name: str,
        content: dict[str, Any],
        artifact_type: str = "document",
        sensitivity: str = "internal",
    ) -> dict[str, Any]:
        """Store artifact via ArtifactStore with rich dashboard metadata.

        Returns a dashboard-friendly artifact dict with artifact_id, type,
        created_at_ms, trace/span correlation, and agent attribution.
        """
        artifact_id = f"{self.name}_{task_id}_{span_id or uuid.uuid4().hex[:8]}"
        artifact_meta = {
            "artifact_id": artifact_id,
            "type": f"{self.department}.{self.name}.{name.replace('.json', '')}",
            "created_at_ms": now_ms(),
            "trace_id": trace_id,
            "span_id": span_id,
            "agent": self.name,
            "sensitivity": sensitivity,
            "payload": content,
        }
        try:
            store = get_artifact_store()
            await store.put_json(
                trace_id=trace_id,
                task_id=task_id,
                name=name,
                content=artifact_meta,
                sensitivity=sensitivity,
            )
        except Exception:
            pass  # Storage failure is non-fatal; artifact_meta is still returned
        return artifact_meta

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.name} ({self.department}/{self.tier})>"
