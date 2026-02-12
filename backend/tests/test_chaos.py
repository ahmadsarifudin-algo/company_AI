"""
Test Suite — Chaos & Resilience Tests (Module 3.5.9).

Tests:
- RetryPolicy with transient/permanent errors
- DeadLetterQueue (push, replay, get_pending)
- CircuitBreaker (close → open → half-open recovery)
- BudgetEnforcer (reserve, finalize, release, exceed)
- IdempotencyGuard (execute_once, duplicate prevention)
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.approval_gate import IdempotencyGuard
from app.core.budget import (
    BudgetEnforcer,
    BudgetExceeded,
    BudgetSoftLimit,
    Reservation,
)
from app.core.resilience import (
    BreakerState,
    CircuitBreaker,
    DeadLetterQueue,
    ErrorCategory,
    RetryPolicy,
    classify_error,
)


# ── Fixtures ──────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_state():
    """Reset shared state between tests."""
    DeadLetterQueue.clear()
    IdempotencyGuard.clear()
    yield
    DeadLetterQueue.clear()
    IdempotencyGuard.clear()


# ── Error Classification ──────────────────────────


class TestErrorClassification:
    """Classify exceptions into retry taxonomy."""

    def test_connection_error_is_transient(self):
        assert classify_error(ConnectionError("timeout")) == ErrorCategory.TRANSIENT

    def test_timeout_error_is_transient(self):
        assert classify_error(TimeoutError("deadline")) == ErrorCategory.TRANSIENT

    def test_value_error_is_validation(self):
        assert classify_error(ValueError("bad input")) == ErrorCategory.VALIDATION

    def test_budget_exceeded_is_budget(self):
        err = BudgetExceeded("finance", 10.0, 5.0, 3.0)
        assert classify_error(err) == ErrorCategory.BUDGET_DENIED

    def test_unknown_error_is_unknown(self):
        assert classify_error(RuntimeError("wat")) == ErrorCategory.UNKNOWN


# ── RetryPolicy ───────────────────────────────────


class TestRetryPolicy:
    """Retry with taxonomy-based backoff."""

    @pytest.mark.asyncio
    async def test_returns_on_success(self):
        """Successful call → returns immediately."""
        func = AsyncMock(return_value="ok")
        result = await RetryPolicy.execute(func=func, trace_id="t1")
        assert result == "ok"
        assert func.await_count == 1

    @pytest.mark.asyncio
    async def test_retries_transient_errors(self):
        """Transient → retries up to max_retries, then raises."""
        call_count = 0

        async def flaky():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("down")

        with pytest.raises(ConnectionError):
            await RetryPolicy.execute(func=flaky, trace_id="t2")

        # 1 original + 3 retries for transient
        assert call_count == 4

    @pytest.mark.asyncio
    async def test_no_retry_on_validation_error(self):
        """Validation error → no retry, immediate raise."""
        call_count = 0

        async def bad_input():
            nonlocal call_count
            call_count += 1
            raise ValueError("invalid")

        with pytest.raises(ValueError):
            await RetryPolicy.execute(func=bad_input, trace_id="t3")

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_no_retry_on_budget_error(self):
        """Budget exceeded → no retry."""
        async def over_budget():
            raise BudgetExceeded("dept", 10.0, 5.0, 3.0)

        with pytest.raises(BudgetExceeded):
            await RetryPolicy.execute(func=over_budget, trace_id="t4")

    @pytest.mark.asyncio
    async def test_dlq_callback_on_exhaustion(self):
        """On retry exhaustion → on_dlq callback fired."""
        dlq_called = False

        def on_dlq(trace_id, step_id, error):
            nonlocal dlq_called
            dlq_called = True

        async def always_fail():
            raise ConnectionError("permanent")

        with pytest.raises(ConnectionError):
            await RetryPolicy.execute(
                func=always_fail,
                trace_id="t5",
                step_id="s5",
                on_dlq=on_dlq,
            )

        assert dlq_called


# ── DeadLetterQueue ───────────────────────────────


class TestDeadLetterQueue:
    """DLQ push, get, and replay."""

    def test_push_creates_entry(self):
        """Push a failed operation → entry stored."""
        entry = DeadLetterQueue.push(
            trace_id="tr1",
            step_id="step1",
            error=ConnectionError("timeout"),
            payload={"key": "value"},
        )
        assert entry.trace_id == "tr1"
        assert entry.error_category == "transient"
        assert entry.replayed is False

    def test_get_pending_returns_unreplayed(self):
        """get_pending() returns only unreplayed entries."""
        DeadLetterQueue.push("tr2", "s1", RuntimeError("err1"))
        DeadLetterQueue.push("tr3", "s2", RuntimeError("err2"))
        pending = DeadLetterQueue.get_pending()
        assert len(pending) == 2

    def test_get_by_trace_filters(self):
        """get_by_trace() returns entries for specific trace."""
        DeadLetterQueue.push("tr4", "s1", RuntimeError("err"))
        DeadLetterQueue.push("tr5", "s1", RuntimeError("err"))
        assert len(DeadLetterQueue.get_by_trace("tr4")) == 1

    @pytest.mark.asyncio
    async def test_replay_executes_handler(self):
        """Replay a DLQ entry → handler is called."""
        entry = DeadLetterQueue.push("tr6", "s1", RuntimeError("err"))

        handler = AsyncMock(return_value="replayed!")
        result = await DeadLetterQueue.replay(entry.dlq_id, handler)

        assert result == "replayed!"
        updated = [e for e in DeadLetterQueue.get_pending()]
        # After replay, it should not be in pending
        replayed_entries = DeadLetterQueue.get_by_trace("tr6")
        assert replayed_entries[0].replayed is True


# ── CircuitBreaker ────────────────────────────────


class TestCircuitBreaker:
    """Circuit breaker state transitions."""

    def test_initial_state_closed(self):
        """New breaker → CLOSED."""
        cb = CircuitBreaker(name="test-cb", failure_threshold=3)
        assert cb.state == BreakerState.CLOSED

    def test_opens_after_threshold(self):
        """N consecutive failures → OPEN."""
        cb = CircuitBreaker(name="fail-cb", failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == BreakerState.OPEN

    def test_closed_allows_calls(self):
        """CLOSED state → allow_request() returns True."""
        cb = CircuitBreaker(name="ok-cb", failure_threshold=5)
        assert cb.allow_request() is True

    def test_open_blocks_calls(self):
        """OPEN state → allow_request() returns False."""
        cb = CircuitBreaker(name="block-cb", failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == BreakerState.OPEN
        assert cb.allow_request() is False

    def test_success_resets_failure_count(self):
        """Success after failures → resets counter."""
        cb = CircuitBreaker(name="reset-cb", failure_threshold=5)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.state == BreakerState.CLOSED


# ── BudgetEnforcer ────────────────────────────────


class TestBudgetEnforcer:
    """Atomic budget reservation and enforcement."""

    @pytest.fixture
    def enforcer(self):
        """BudgetEnforcer with mock Redis."""
        mock_redis = MagicMock()
        mock_redis.get = MagicMock(return_value=b"0.0")
        mock_redis.eval = MagicMock(return_value=1)
        return BudgetEnforcer(redis_client=mock_redis)

    @pytest.mark.asyncio
    async def test_reserve_creates_reservation(self, enforcer):
        """reserve() returns a Reservation object."""
        reservation = await enforcer.reserve("finance", "bot-1", 0.05)
        assert isinstance(reservation, Reservation)
        assert reservation.estimated_cost == 0.05
        assert reservation.finalized is False

    @pytest.mark.asyncio
    async def test_finalize_adjusts_cost(self, enforcer):
        """finalize() marks reservation as finalized."""
        reservation = await enforcer.reserve("finance", "bot-1", 0.05)
        await enforcer.finalize(reservation, 0.03)
        assert reservation.finalized is True
        assert reservation.actual_cost == 0.03

    @pytest.mark.asyncio
    async def test_release_unreserves_on_failure(self, enforcer):
        """release() returns budget on cancellation."""
        reservation = await enforcer.reserve("finance", "bot-1", 0.05)
        await enforcer.release(reservation)
        assert reservation.released is True

    @pytest.mark.asyncio
    async def test_check_budget_raises_when_exceeded(self):
        """Hard limit exceeded → BudgetExceeded raised."""
        mock_redis = MagicMock()
        mock_redis.get = MagicMock(return_value=b"100.0")
        enforcer = BudgetEnforcer(redis_client=mock_redis)
        enforcer.set_limits("finance", soft_limit=5.0, hard_limit=10.0)

        with pytest.raises(BudgetExceeded):
            await enforcer.check_budget("finance", "bot-1")


# ── IdempotencyGuard ──────────────────────────────


class TestIdempotencyGuard:
    """Idempotency ensures at-most-once execution."""

    @pytest.mark.asyncio
    async def test_first_execution_runs(self):
        """First call → handler executes."""
        handler = AsyncMock(return_value="result")
        result = await IdempotencyGuard.execute_once("key-1", handler)
        assert result == "result"
        handler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_duplicate_returns_cached(self):
        """Second call with same key → cached result returned."""
        call_count = 0

        async def handler():
            nonlocal call_count
            call_count += 1
            return f"result-{call_count}"

        r1 = await IdempotencyGuard.execute_once("key-2", handler)
        r2 = await IdempotencyGuard.execute_once("key-2", handler)

        assert r1 == "result-1"
        assert r2 == "result-1"  # Same result, no re-execution
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_different_keys_execute_separately(self):
        """Different keys → each executes independently."""
        h1 = AsyncMock(return_value="a")
        h2 = AsyncMock(return_value="b")

        r1 = await IdempotencyGuard.execute_once("key-a", h1)
        r2 = await IdempotencyGuard.execute_once("key-b", h2)

        assert r1 == "a"
        assert r2 == "b"

    def test_has_executed(self):
        """has_executed() checks presence."""
        assert IdempotencyGuard.has_executed("key-check") is False
