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

import hashlib
import time
from abc import ABC, abstractmethod
from collections import Counter
from typing import Any

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agents.state import AgentState
from app.core.config import get_settings
from app.core.llm_client import AgentContext, LLMClient, LLMResponse

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

        # Internal tracking
        self._tool_call_hashes: Counter = Counter()
        self._start_time: float | None = None

        self.log = logger.bind(agent=self.name, department=self.department)

    def get_context(self, task_id: str = "", trace_id: str = "") -> AgentContext:
        """Create an AgentContext for this agent.

        Used by call_llm() and call_tool() for tracing and policy.
        """
        return AgentContext(
            agent_id=self.agent_id,
            agent_name=self.name,
            department=self.department,
            tier=self.tier,
            role="agent",
            task_id=task_id,
            trace_id=trace_id or "",
        )

    # ── Abstract methods (must be implemented by subclasses) ──

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the system prompt for this agent."""
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

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.name} ({self.department}/{self.tier})>"
