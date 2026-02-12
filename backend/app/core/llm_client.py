"""
LLMClient — Single Chokepoint for all LLM calls.

Every LLM interaction in the system MUST go through this client.
It enforces: budget checking, audit logging, tracing, and cost tracking.

No agent or service may import httpx/requests to call LLM directly.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import httpx
import structlog

from app.core.config import get_settings
from app.core.policy_context import PolicyContextBuilder
from app.core.policy_engine import get_policy_engine

logger = structlog.get_logger()
settings = get_settings()


# ── Model routing by tier ────────────────────────
TIER_MODEL_MAP: dict[str, str] = {
    "nano": "gpt-4o-mini",
    "standard": "claude-3-5-sonnet-20241022",
    "advanced": "claude-3-opus-20240229",
    "code": "deepseek/deepseek-coder",
    "vision": "gpt-4o",
}


class LLMCallDenied(Exception):
    """Raised when an LLM call is denied by policy."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"LLM call denied by policy: {reason}")


@dataclass
class LLMResponse:
    """Structured response from an LLM call."""

    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    prompt_hash: str = ""
    raw: dict = field(default_factory=dict)
    status: str = "success"  # "success" | "needs_approval"
    approval_id: str | None = None


@dataclass
class AgentContext:
    """Context that flows through all chokepoint gateways.

    Created once per request/workflow and passed to LLMClient,
    ToolBroker, and DataAccessLayer for policy/audit/budget decisions.
    """

    agent_id: str
    agent_name: str
    department: str
    tier: str = "standard"
    role: str = "agent"
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    span_id: str = field(default_factory=lambda: str(uuid4()))
    parent_span: str | None = None
    task_id: str = ""
    requester_id: str = ""
    # ── Policy-ready fields ──
    ticket_id: str = ""
    approval_chain: list[str] = field(default_factory=list)
    data_sensitivity: str = "internal"
    risk_level: str = "low"

    def new_span(self) -> "AgentContext":
        """Create a child span within the same trace."""
        return AgentContext(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            department=self.department,
            tier=self.tier,
            role=self.role,
            trace_id=self.trace_id,
            span_id=str(uuid4()),
            parent_span=self.span_id,
            task_id=self.task_id,
            requester_id=self.requester_id,
            ticket_id=self.ticket_id,
            approval_chain=list(self.approval_chain),
            data_sensitivity=self.data_sensitivity,
            risk_level=self.risk_level,
        )


def _compute_prompt_hash(messages: list[dict[str, str]]) -> str:
    """Compute SHA-256 hash of the prompt for audit trail."""
    canonical = json.dumps(messages, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Rough cost estimation per model.

    Rates are approximate USD per 1M tokens (input/output).
    """
    COST_MAP = {
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4o": (2.50, 10.00),
        "claude-3-5-sonnet-20241022": (3.00, 15.00),
        "claude-3-opus-20240229": (15.00, 75.00),
        "deepseek/deepseek-coder": (0.14, 0.28),
    }
    input_rate, output_rate = COST_MAP.get(model, (3.00, 15.00))
    cost = (prompt_tokens * input_rate + completion_tokens * output_rate) / 1_000_000
    return round(cost, 6)


class LLMClient:
    """Sole gateway for all LLM interactions.

    Features:
    - Centralized model routing by agent tier
    - Prompt hashing for audit trail
    - Cost estimation and tracking
    - Structured logging with trace context
    - Future hooks: budget reservation, circuit breaker
    """

    def __init__(self) -> None:
        self._base_url = settings.LITELLM_PROXY_URL
        self._master_key = settings.LITELLM_MASTER_KEY

    def _get_model(self, tier: str) -> str:
        """Resolve model name from tier."""
        return TIER_MODEL_MAP.get(tier, TIER_MODEL_MAP["standard"])

    async def call(
        self,
        ctx: AgentContext,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Call LLM via LiteLLM proxy through the single chokepoint.

        All controls (budget, audit, tracing) are enforced here.

        Args:
            ctx: Agent context with trace_id, department, tier.
            messages: Chat messages in OpenAI format.
            tools: Optional tool definitions for function calling.
            temperature: Sampling temperature.
            max_tokens: Max completion tokens.

        Returns:
            Structured LLMResponse with content, tokens, cost, and hash.
        """
        model = self._get_model(ctx.tier)
        prompt_hash = _compute_prompt_hash(messages)
        url = f"{self._base_url}/v1/chat/completions"

        # ── Policy evaluation (NON-BYPASSABLE) ──
        policy_ctx = PolicyContextBuilder.for_llm_call(ctx, model)
        decision = get_policy_engine().evaluate(policy_ctx)

        logger.info(
            "policy_evaluated",
            trace_id=ctx.trace_id,
            span_id=ctx.span_id,
            agent=ctx.agent_name,
            action="llm_call",
            resource=f"model:{model}",
            decision=decision.action.value,
            rule=decision.rule_name,
        )

        if decision.denied:
            raise LLMCallDenied(decision.reason)

        if decision.needs_approval:
            return LLMResponse(
                content="",
                model=model,
                prompt_hash=prompt_hash,
                status="needs_approval",
            )

        # Build payload
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
        if max_tokens:
            payload["max_tokens"] = max_tokens

        logger.info(
            "llm_call_start",
            trace_id=ctx.trace_id,
            span_id=ctx.span_id,
            agent=ctx.agent_name,
            department=ctx.department,
            model=model,
            msg_count=len(messages),
            prompt_hash=prompt_hash[:16],
        )

        start_time = time.monotonic()

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self._master_key}",
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()
                result = response.json()

        except httpx.TimeoutException:
            logger.error(
                "llm_call_timeout",
                trace_id=ctx.trace_id,
                agent=ctx.agent_name,
                model=model,
            )
            raise
        except httpx.HTTPStatusError as exc:
            logger.error(
                "llm_call_error",
                trace_id=ctx.trace_id,
                agent=ctx.agent_name,
                model=model,
                status=exc.response.status_code,
                body=exc.response.text[:500],
            )
            raise

        elapsed_ms = (time.monotonic() - start_time) * 1000

        # Extract usage
        usage = result.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)
        cost_usd = _estimate_cost(model, prompt_tokens, completion_tokens)

        # Extract content
        choices = result.get("choices", [])
        content = ""
        if choices:
            message = choices[0].get("message", {})
            content = message.get("content", "") or ""

        logger.info(
            "llm_call_complete",
            trace_id=ctx.trace_id,
            span_id=ctx.span_id,
            agent=ctx.agent_name,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            elapsed_ms=int(elapsed_ms),
        )

        return LLMResponse(
            content=content,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            prompt_hash=prompt_hash,
            raw=result,
        )

    async def embed(
        self,
        ctx: AgentContext,
        texts: list[str],
        model: str | None = None,
    ) -> list[list[float]]:
        """Embed texts via LiteLLM proxy embedding endpoint.

        Args:
            ctx: Agent context for tracing.
            texts: List of texts to embed.
            model: Override embedding model (default from settings).

        Returns:
            List of embedding vectors.
        """
        embed_model = model or settings.EMBEDDING_MODEL
        url = f"{self._base_url}/v1/embeddings"

        logger.info(
            "embed_start",
            trace_id=ctx.trace_id,
            agent=ctx.agent_name,
            model=embed_model,
            text_count=len(texts),
        )

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                url,
                json={"model": embed_model, "input": texts},
                headers={
                    "Authorization": f"Bearer {self._master_key}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            result = response.json()

        embeddings = [item["embedding"] for item in result["data"]]

        logger.info(
            "embed_complete",
            trace_id=ctx.trace_id,
            agent=ctx.agent_name,
            model=embed_model,
            vectors=len(embeddings),
        )

        return embeddings


# ── Singleton ─────────────────────────────────────
_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Get the singleton LLMClient instance."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
