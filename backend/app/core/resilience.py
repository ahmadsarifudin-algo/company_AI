"""
Resilience — Retry policies, Dead Letter Queue (DLQ), and Circuit Breaker.

RetryPolicy:
    Classifies errors into taxonomy: transient (retry), policy-denied (no retry),
    validation-error (no retry), budget-denied (no retry).

DeadLetterQueue:
    Failed operations after max retries are stored for manual inspection and
    replay. Keyed by trace_id + step_id.

CircuitBreaker:
    Opens after N consecutive failures to a provider. When open, requests
    fall back to a lower-tier model or fail fast. Half-open after cooldown
    to test recovery.
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine
from uuid import uuid4

import structlog

logger = structlog.get_logger()


class ErrorCategory(str, Enum):
    """Error taxonomy — determines retry behavior."""

    TRANSIENT = "transient"        # timeout, 502, connection reset
    POLICY_DENIED = "policy_denied"  # ABAC denied, no retry
    VALIDATION = "validation"      # bad input, no retry
    BUDGET_DENIED = "budget_denied"  # budget exceeded, no retry
    RATE_LIMITED = "rate_limited"   # 429, retry with backoff
    UNKNOWN = "unknown"


@dataclass
class RetryConfig:
    """Configuration for retry behavior per error category."""

    max_retries: int
    backoff_type: str = "none"       # "none" | "exponential" | "linear"
    backoff_base_ms: int = 1000
    backoff_max_ms: int = 30000


# ── Retry Taxonomy ────────────────────────────────
RETRY_TAXONOMY: dict[ErrorCategory, RetryConfig] = {
    ErrorCategory.TRANSIENT: RetryConfig(
        max_retries=3,
        backoff_type="exponential",
        backoff_base_ms=1000,
        backoff_max_ms=30000,
    ),
    ErrorCategory.RATE_LIMITED: RetryConfig(
        max_retries=5,
        backoff_type="exponential",
        backoff_base_ms=2000,
        backoff_max_ms=60000,
    ),
    ErrorCategory.POLICY_DENIED: RetryConfig(max_retries=0),
    ErrorCategory.VALIDATION: RetryConfig(max_retries=0),
    ErrorCategory.BUDGET_DENIED: RetryConfig(max_retries=0),
    ErrorCategory.UNKNOWN: RetryConfig(max_retries=1, backoff_type="linear", backoff_base_ms=2000),
}


def classify_error(error: Exception) -> ErrorCategory:
    """Classify an exception into the retry taxonomy.

    Args:
        error: The exception to classify.

    Returns:
        ErrorCategory determining retry behavior.
    """
    error_type = type(error).__name__
    error_msg = str(error).lower()

    # Policy / access denied
    if error_type in ("PolicyDenied", "ToolAccessDenied", "ToolCallDenied", "EgressDenied"):
        return ErrorCategory.POLICY_DENIED

    # Budget
    if error_type in ("BudgetExceeded", "BudgetSoftLimit"):
        return ErrorCategory.BUDGET_DENIED

    # Validation
    if error_type in ("ValidationError", "ValueError", "TypeError", "PathEscapeAttempt"):
        return ErrorCategory.VALIDATION

    # Rate limiting
    if "429" in error_msg or "rate limit" in error_msg or "too many requests" in error_msg:
        return ErrorCategory.RATE_LIMITED

    # Transient network / server errors
    if any(indicator in error_msg for indicator in [
        "timeout", "timed out", "502", "503", "504",
        "connection", "reset", "eof", "broken pipe",
    ]):
        return ErrorCategory.TRANSIENT

    if error_type in ("TimeoutError", "ConnectionError", "OSError"):
        return ErrorCategory.TRANSIENT

    return ErrorCategory.UNKNOWN


class RetryPolicy:
    """Execute an async operation with retry based on error taxonomy.

    Usage:
        result = await RetryPolicy.execute(
            func=lambda: llm_client.call(...),
            trace_id="abc",
            step_id="step_1",
        )
    """

    @staticmethod
    async def execute(
        func: Callable[..., Coroutine[Any, Any, Any]],
        trace_id: str = "",
        step_id: str = "",
        on_dlq: Callable | None = None,
    ) -> Any:
        """Execute with automatic retry based on error classification.

        Args:
            func: Async operation to execute.
            trace_id: For logging and DLQ.
            step_id: For logging and DLQ.
            on_dlq: Callback when operation exhausts retries (sends to DLQ).

        Returns:
            Result of the operation.

        Raises:
            The last exception if all retries exhausted.
        """
        last_error: Exception | None = None

        # First attempt
        try:
            return await func()
        except Exception as e:
            last_error = e

        category = classify_error(last_error)
        config = RETRY_TAXONOMY.get(category, RETRY_TAXONOMY[ErrorCategory.UNKNOWN])

        if config.max_retries == 0:
            logger.warning(
                "retry_not_allowed",
                category=category.value,
                error=str(last_error)[:200],
                trace_id=trace_id,
            )
            raise last_error

        # Retry loop
        for attempt in range(1, config.max_retries + 1):
            # Compute backoff
            if config.backoff_type == "exponential":
                delay_ms = min(config.backoff_base_ms * (2 ** (attempt - 1)), config.backoff_max_ms)
            elif config.backoff_type == "linear":
                delay_ms = min(config.backoff_base_ms * attempt, config.backoff_max_ms)
            else:
                delay_ms = 0

            logger.info(
                "retrying",
                attempt=attempt,
                max_retries=config.max_retries,
                category=category.value,
                delay_ms=delay_ms,
                trace_id=trace_id,
            )

            if delay_ms > 0:
                await asyncio.sleep(delay_ms / 1000.0)

            try:
                return await func()
            except Exception as e:
                last_error = e
                new_category = classify_error(e)
                if new_category != category:
                    # Error type changed — re-evaluate retry
                    config = RETRY_TAXONOMY.get(new_category, config)
                    if config.max_retries == 0:
                        break

        # All retries exhausted → DLQ
        logger.error(
            "retries_exhausted",
            category=category.value,
            error=str(last_error)[:200],
            trace_id=trace_id,
            step_id=step_id,
        )

        if on_dlq:
            import inspect
            if inspect.iscoroutinefunction(on_dlq):
                await on_dlq(trace_id, step_id, last_error)
            else:
                on_dlq(trace_id, step_id, last_error)

        raise last_error


# ── Dead Letter Queue ─────────────────────────────

@dataclass
class DLQEntry:
    """An entry in the Dead Letter Queue."""

    dlq_id: str
    trace_id: str
    step_id: str
    error_type: str
    error_message: str
    error_category: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    replayed: bool = False
    replay_result: Any = None


class DeadLetterQueue:
    """Storage for failed operations after retry exhaustion.

    In-memory implementation; production would use Redis list or DB table.
    """

    _entries: dict[str, DLQEntry] = {}

    @classmethod
    async def push(
        cls,
        trace_id: str,
        step_id: str,
        error: Exception,
        payload: dict[str, Any] | None = None,
    ) -> DLQEntry:
        """Push a failed operation to the DLQ.

        Args:
            trace_id: Workflow trace ID.
            step_id: Step that failed.
            error: The exception that caused the failure.
            payload: Original operation payload for replay.

        Returns:
            The DLQ entry.
        """
        dlq_id = f"dlq_{uuid4().hex[:12]}"
        category = classify_error(error)

        entry = DLQEntry(
            dlq_id=dlq_id,
            trace_id=trace_id,
            step_id=step_id,
            error_type=type(error).__name__,
            error_message=str(error)[:500],
            error_category=category.value,
            payload=payload or {},
        )

        cls._entries[dlq_id] = entry

        logger.warning(
            "dlq_push",
            dlq_id=dlq_id,
            trace_id=trace_id,
            step_id=step_id,
            error_type=type(error).__name__,
        )

        return entry

    @classmethod
    async def replay(
        cls,
        dlq_id: str,
        handler: Callable[..., Coroutine[Any, Any, Any]],
    ) -> Any:
        """Replay a DLQ entry with its original handler.

        Uses the same idempotency_key as the original call to prevent
        duplicate side effects.

        Args:
            dlq_id: DLQ entry to replay.
            handler: Original async handler to re-execute.

        Returns:
            Result of the handler.
        """
        entry = cls._entries.get(dlq_id)
        if not entry:
            raise ValueError(f"DLQ entry {dlq_id} not found")

        logger.info("dlq_replay", dlq_id=dlq_id, trace_id=entry.trace_id)

        result = await handler()
        entry.replayed = True
        entry.replay_result = result

        return result

    @classmethod
    def get_pending(cls) -> list[DLQEntry]:
        """Get all un-replayed DLQ entries."""
        return [e for e in cls._entries.values() if not e.replayed]

    @classmethod
    def get_by_trace(cls, trace_id: str) -> list[DLQEntry]:
        """Get DLQ entries for a specific trace."""
        return [e for e in cls._entries.values() if e.trace_id == trace_id]

    @classmethod
    def clear(cls) -> None:
        """Clear all DLQ entries. For testing only."""
        cls._entries.clear()


# ── Circuit Breaker ───────────────────────────────

class BreakerState(str, Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Blocking requests (provider down)
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreaker:
    """Circuit breaker for external providers (LiteLLM, APIs).

    Opens after `failure_threshold` consecutive failures.
    When open, requests fail fast or use fallback.
    After `recovery_timeout`, transitions to half-open to test.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout_s: float = 60.0,
        fallback: Callable | None = None,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_s = recovery_timeout_s
        self.fallback = fallback

        self.state = BreakerState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0
        self._success_count_in_half_open = 0

    async def call(
        self,
        func: Callable[..., Coroutine[Any, Any, Any]],
    ) -> Any:
        """Execute with circuit breaker protection.

        Args:
            func: Async operation to execute.

        Returns:
            Result of func or fallback.

        Raises:
            Exception from func if no fallback and breaker is open.
        """
        # Check if breaker should transition from OPEN → HALF_OPEN
        if self.state == BreakerState.OPEN:
            elapsed = time.time() - self._last_failure_time
            if elapsed >= self.recovery_timeout_s:
                self.state = BreakerState.HALF_OPEN
                self._success_count_in_half_open = 0
                logger.info("circuit_breaker_half_open", name=self.name)
            else:
                # Still open — use fallback or fail fast
                logger.warning("circuit_breaker_open", name=self.name)
                if self.fallback:
                    return await self.fallback()
                raise RuntimeError(
                    f"Circuit breaker '{self.name}' is OPEN "
                    f"(recovery in {self.recovery_timeout_s - elapsed:.0f}s)"
                )

        try:
            result = await func()
            self._on_success()
            return result
        except Exception as e:
            category = classify_error(e)
            if category in (ErrorCategory.TRANSIENT, ErrorCategory.RATE_LIMITED):
                self._on_failure()
            raise

    def _on_success(self) -> None:
        """Record a successful call."""
        if self.state == BreakerState.HALF_OPEN:
            self._success_count_in_half_open += 1
            # Need 3 consecutive successes to close
            if self._success_count_in_half_open >= 3:
                self.state = BreakerState.CLOSED
                self._failure_count = 0
                logger.info("circuit_breaker_closed", name=self.name)
        else:
            self._failure_count = 0

    def _on_failure(self) -> None:
        """Record a failed call."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._failure_count >= self.failure_threshold:
            self.state = BreakerState.OPEN
            logger.error(
                "circuit_breaker_opened",
                name=self.name,
                failures=self._failure_count,
                recovery_s=self.recovery_timeout_s,
            )

    def record_failure(self) -> None:
        """Record a failed call (public API for testing and direct use)."""
        self._on_failure()

    def record_success(self) -> None:
        """Record a successful call (public API for testing and direct use)."""
        self._on_success()

    def allow_request(self) -> bool:
        """Check whether the breaker currently allows requests."""
        if self.state == BreakerState.CLOSED:
            return True
        if self.state == BreakerState.HALF_OPEN:
            return True  # allow probe request
        # OPEN — check if recovery timeout elapsed
        import time as _time
        elapsed = _time.time() - self._last_failure_time
        if elapsed >= self.recovery_timeout_s:
            self.state = BreakerState.HALF_OPEN
            self._success_count_in_half_open = 0
            return True
        return False

    def reset(self) -> None:
        """Manually reset the breaker to CLOSED state."""
        self.state = BreakerState.CLOSED
        self._failure_count = 0
        self._success_count_in_half_open = 0


# ── Pre-configured breakers ──────────────────────
_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout_s: float = 60.0,
    fallback: Callable | None = None,
) -> CircuitBreaker:
    """Get or create a named circuit breaker."""
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout_s=recovery_timeout_s,
            fallback=fallback,
        )
    return _breakers[name]
