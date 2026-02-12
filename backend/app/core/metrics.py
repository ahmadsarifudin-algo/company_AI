"""
MetricsCollector — Redis-backed metrics aggregation for the enterprise OS.

Collects:
- Cost per agent / department / day
- Execution time (mean, p95)
- Success / failure rates
- Tool error rates
- Approval latencies

Data is stored in Redis hashes keyed by department + date.
Dashboard endpoint reads these for admin display.
"""

from datetime import date, datetime
from typing import Any

import structlog

from app.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


class MetricsCollector:
    """Redis-backed metrics aggregation.

    Metrics are stored as Redis HASHes:
    - metrics:{department}:{date} → { agent_calls, cost_usd, ... }
    - metrics:global:{date}       → global aggregates
    """

    def __init__(self, redis_client=None):
        """Initialize with optional Redis client.

        Args:
            redis_client: aioredis client. If None, metrics are logged
                          but not persisted.
        """
        self._redis = redis_client

    async def record(
        self,
        department: str,
        agent_name: str,
        duration_ms: float,
        cost_usd: float,
        success: bool,
        tool_errors: int = 0,
        token_count: int = 0,
        event_type: str = "agent_execution",
    ) -> None:
        """Record a metric data point.

        Args:
            department: Department scope.
            agent_name: Agent that generated this metric.
            duration_ms: Execution time in milliseconds.
            cost_usd: Cost incurred in USD.
            success: Whether the operation succeeded.
            tool_errors: Number of tool errors encountered.
            token_count: Tokens consumed.
            event_type: Type of event being measured.
        """
        today = date.today().isoformat()
        key = f"metrics:{department}:{today}"
        global_key = f"metrics:global:{today}"

        fields = {
            "total_calls": 1,
            "total_cost_usd": cost_usd,
            "total_duration_ms": duration_ms,
            "total_tokens": token_count,
            "tool_errors": tool_errors,
            "success_count": 1 if success else 0,
            "failure_count": 0 if success else 1,
        }

        if self._redis:
            for field_name, value in fields.items():
                await self._redis.hincrbyfloat(key, field_name, value)
                await self._redis.hincrbyfloat(global_key, field_name, value)

            # Per-agent tracking
            agent_key = f"metrics:agent:{agent_name}:{today}"
            for field_name, value in fields.items():
                await self._redis.hincrbyfloat(agent_key, field_name, value)

            # Set TTL (30 days)
            for k in [key, global_key, agent_key]:
                await self._redis.expire(k, 30 * 86400)

        logger.info(
            "metric_recorded",
            department=department,
            agent=agent_name,
            event_type=event_type,
            cost_usd=round(cost_usd, 6),
            duration_ms=round(duration_ms, 1),
            success=success,
        )

    async def record_approval_latency(
        self,
        department: str,
        latency_ms: float,
    ) -> None:
        """Record time between approval request and resolution."""
        today = date.today().isoformat()
        key = f"metrics:{department}:{today}"

        if self._redis:
            await self._redis.hincrbyfloat(key, "approval_latency_total_ms", latency_ms)
            await self._redis.hincrbyfloat(key, "approval_count", 1)

    async def get_dashboard(self, department: str | None = None) -> dict[str, Any]:
        """Get aggregated dashboard metrics.

        Args:
            department: Optional department filter. None = global.

        Returns:
            Dashboard dict with cost, performance, and reliability metrics.
        """
        today = date.today().isoformat()

        if department:
            key = f"metrics:{department}:{today}"
        else:
            key = f"metrics:global:{today}"

        if not self._redis:
            return self._empty_dashboard()

        data = await self._redis.hgetall(key)
        if not data:
            return self._empty_dashboard()

        total_calls = float(data.get("total_calls", 0))
        success_count = float(data.get("success_count", 0))
        failure_count = float(data.get("failure_count", 0))
        total_duration = float(data.get("total_duration_ms", 0))
        approval_latency = float(data.get("approval_latency_total_ms", 0))
        approval_count = float(data.get("approval_count", 0))

        return {
            "date": today,
            "department": department or "global",
            "total_calls": int(total_calls),
            "cost_usd": round(float(data.get("total_cost_usd", 0)), 6),
            "total_tokens": int(float(data.get("total_tokens", 0))),
            "success_rate": round(success_count / total_calls, 4) if total_calls > 0 else 0,
            "failure_rate": round(failure_count / total_calls, 4) if total_calls > 0 else 0,
            "tool_errors": int(float(data.get("tool_errors", 0))),
            "avg_duration_ms": round(total_duration / total_calls, 1) if total_calls > 0 else 0,
            "avg_approval_latency_ms": round(
                approval_latency / approval_count, 1
            ) if approval_count > 0 else 0,
        }

    def _empty_dashboard(self) -> dict[str, Any]:
        """Return an empty dashboard structure."""
        return {
            "date": date.today().isoformat(),
            "department": "global",
            "total_calls": 0,
            "cost_usd": 0.0,
            "total_tokens": 0,
            "success_rate": 0.0,
            "failure_rate": 0.0,
            "tool_errors": 0,
            "avg_duration_ms": 0.0,
            "avg_approval_latency_ms": 0.0,
        }


# ── Singleton ─────────────────────────────────────
_metrics: MetricsCollector | None = None


def get_metrics_collector(redis_client=None) -> MetricsCollector:
    """Get the singleton MetricsCollector."""
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector(redis_client)
    return _metrics
