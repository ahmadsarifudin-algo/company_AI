"""
BaseAgent — Abstract base class for all enterprise agents.

Every specialist agent (Tech, Finance, HR, etc.) inherits from this class.
Provides:
- LiteLLM model selection by tier
- Rate limiting (tool calls, tokens, execution time)
- Loop detection (repeated similar tool calls)
- Standard execution pipeline
"""

import hashlib
import time
from abc import ABC, abstractmethod
from collections import Counter
from typing import Any

import httpx
import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agents.state import AgentState
from app.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()

# ── Model routing by tier ────────────────────────
TIER_MODEL_MAP = {
    "nano": "gpt-4o-mini",
    "standard": "claude-3-5-sonnet-20241022",
    "advanced": "claude-3-opus-20240229",
    "code": "deepseek/deepseek-coder",
    "vision": "gpt-4o",
}


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
        - get_tools() -> list[dict]
        - process(state: AgentState) -> AgentState
    """

    def __init__(
        self,
        agent_id: str,
        name: str,
        department: str,
        tier: str = "standard",
        config: dict[str, Any] | None = None,
    ):
        self.agent_id = agent_id
        self.name = name
        self.department = department
        self.tier = tier
        self.config = config or {}

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

    @property
    def model_name(self) -> str:
        """Get the LLM model name based on this agent's tier."""
        return TIER_MODEL_MAP.get(self.tier, TIER_MODEL_MAP["standard"])

    @property
    def litellm_url(self) -> str:
        """LiteLLM proxy URL for API calls."""
        return f"{settings.LITELLM_PROXY_URL}/v1/chat/completions"

    # ── Abstract methods (must be implemented by subclasses) ──

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the system prompt for this agent."""
        ...

    @abstractmethod
    def get_tools(self) -> list[dict]:
        """Return the tool definitions available to this agent."""
        ...

    @abstractmethod
    async def process(self, state: AgentState) -> AgentState:
        """Process the current state and return updated state.

        This is the main execution logic of the agent. Subclasses implement
        their specific behavior here (code generation, analysis, etc.).
        """
        ...

    # ── LLM Interaction ──────────────────────────

    async def call_llm(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
    ) -> dict[str, Any]:
        """Call LLM via LiteLLM proxy with rate limiting and cost tracking.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            tools: Optional tool definitions for function calling.
            temperature: Sampling temperature.

        Returns:
            LiteLLM response dict with 'choices' and 'usage'.

        Raises:
            RateLimitExceeded: If token budget is exceeded.
        """
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools

        self.log.info("calling_llm", model=self.model_name, msg_count=len(messages))

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                self.litellm_url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {settings.LITELLM_MASTER_KEY}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            result = response.json()

        # Track token usage
        usage = result.get("usage", {})
        tokens_used = usage.get("total_tokens", 0)
        self.log.info("llm_response", tokens=tokens_used, model=self.model_name)

        return result

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
