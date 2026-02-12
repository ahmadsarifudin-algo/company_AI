"""
BudgetEnforcer — Atomic budget reservation and enforcement.

Uses a two-phase approach:
1. reserve(): Atomically check + reserve estimated cost (Redis Lua script)
2. finalize(): Adjust reservation to actual cost
3. release(): Release on failure (auto-release via TTL)

Two layers of budget enforcement:
- Per-department per-day: total spend limit for the department
- Per-agent per-day: individual agent spend limit

Soft limit → require_approval (warning)
Hard limit → deny (block execution)
"""

from dataclasses import dataclass
from uuid import uuid4

import structlog

from app.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


class BudgetExceeded(Exception):
    """Raised when budget is exceeded (hard limit)."""

    def __init__(self, entity: str, current: float, limit: float, requested: float):
        self.entity = entity
        self.current = current
        self.limit = limit
        self.requested = requested
        super().__init__(
            f"Budget exceeded for {entity}: "
            f"current=${current:.4f} + requested=${requested:.4f} > limit=${limit:.4f}"
        )


class BudgetSoftLimit(Exception):
    """Raised when soft limit is hit — requires approval to continue."""

    def __init__(self, entity: str, current: float, soft_limit: float):
        self.entity = entity
        self.current = current
        self.soft_limit = soft_limit
        super().__init__(
            f"Budget soft limit for {entity}: "
            f"current=${current:.4f} exceeds soft limit=${soft_limit:.4f}"
        )


@dataclass
class Reservation:
    """A budget reservation."""

    reservation_id: str
    entity_key: str  # "dept:finance:2026-02-12" or "agent:finance_bot:2026-02-12"
    estimated_cost: float
    actual_cost: float | None = None
    finalized: bool = False
    released: bool = False


@dataclass
class BudgetSummary:
    """Current budget usage summary."""

    entity: str
    current_spend: float
    soft_limit: float
    hard_limit: float
    remaining: float
    utilization_pct: float
    reservations_active: int = 0


# ── Redis Lua Scripts ─────────────────────────────
# Atomic check + reserve: ensures no race conditions under concurrency

RESERVE_LUA = """
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
local hard_limit = tonumber(ARGV[1])
local amount = tonumber(ARGV[2])
if current + amount > hard_limit then
    return -1
end
redis.call('INCRBYFLOAT', KEYS[1], amount)
return 1
"""

FINALIZE_LUA = """
local estimated = tonumber(ARGV[1])
local actual = tonumber(ARGV[2])
local diff = actual - estimated
redis.call('INCRBYFLOAT', KEYS[1], diff)
return 1
"""

RELEASE_LUA = """
local amount = tonumber(ARGV[1])
redis.call('INCRBYFLOAT', KEYS[1], -amount)
return 1
"""


class BudgetEnforcer:
    """Atomic budget reservation and enforcement.

    Usage:
        enforcer = BudgetEnforcer(redis_client)
        reservation = await enforcer.reserve("finance", "finance_bot", 0.05)
        try:
            result = await llm_call(...)
            await enforcer.finalize(reservation, actual_cost=0.032)
        except Exception:
            await enforcer.release(reservation)
    """

    # Default limits (USD per day)
    DEFAULT_DEPT_HARD_LIMIT = 100.0
    DEFAULT_DEPT_SOFT_LIMIT = 80.0
    DEFAULT_AGENT_HARD_LIMIT = 25.0
    DEFAULT_AGENT_SOFT_LIMIT = 20.0

    def __init__(self, redis_client=None):
        self._redis = redis_client
        self._reservations: dict[str, Reservation] = {}

        # Configurable limits per entity (can be loaded from DB/config)
        self._limits: dict[str, tuple[float, float]] = {}  # entity → (soft, hard)

    def set_limits(self, entity: str, soft_limit: float, hard_limit: float) -> None:
        """Set custom budget limits for an entity."""
        self._limits[entity] = (soft_limit, hard_limit)

    def _get_limits(self, entity_type: str) -> tuple[float, float]:
        """Get (soft, hard) limits for an entity type."""
        if entity_type in self._limits:
            return self._limits[entity_type]
        if entity_type.startswith("dept:"):
            return (self.DEFAULT_DEPT_SOFT_LIMIT, self.DEFAULT_DEPT_HARD_LIMIT)
        return (self.DEFAULT_AGENT_SOFT_LIMIT, self.DEFAULT_AGENT_HARD_LIMIT)

    async def reserve(
        self,
        department: str,
        agent_id: str,
        estimated_cost: float,
    ) -> Reservation:
        """Atomically reserve budget for an operation.

        Checks both department and agent limits. Uses Redis Lua for atomicity.

        Args:
            department: Department to charge.
            agent_id: Agent to charge.
            estimated_cost: Estimated cost in USD.

        Returns:
            Reservation object with reservation_id.

        Raises:
            BudgetExceeded: If hard limit would be exceeded.
            BudgetSoftLimit: If soft limit is exceeded (needs approval).
        """
        from datetime import date
        today = date.today().isoformat()

        dept_key = f"budget:dept:{department}:{today}"
        agent_key = f"budget:agent:{agent_id}:{today}"

        # Check department budget
        dept_soft, dept_hard = self._get_limits(f"dept:{department}")
        await self._check_and_reserve(dept_key, dept_hard, dept_soft, estimated_cost, department)

        # Check agent budget
        agent_soft, agent_hard = self._get_limits(f"agent:{agent_id}")
        try:
            await self._check_and_reserve(agent_key, agent_hard, agent_soft, estimated_cost, agent_id)
        except (BudgetExceeded, BudgetSoftLimit):
            # Rollback department reservation
            await self._rollback(dept_key, estimated_cost)
            raise

        reservation_id = f"res_{uuid4().hex[:12]}"
        reservation = Reservation(
            reservation_id=reservation_id,
            entity_key=f"{dept_key}|{agent_key}",
            estimated_cost=estimated_cost,
        )
        self._reservations[reservation_id] = reservation

        logger.info(
            "budget_reserved",
            reservation_id=reservation_id,
            department=department,
            agent=agent_id,
            estimated_cost=round(estimated_cost, 6),
        )

        return reservation

    async def finalize(self, reservation: Reservation, actual_cost: float) -> None:
        """Adjust reservation to actual cost.

        Args:
            reservation: The reservation to finalize.
            actual_cost: The actual cost incurred.
        """
        if reservation.finalized:
            return

        diff = actual_cost - reservation.estimated_cost
        keys = reservation.entity_key.split("|")

        if self._redis and diff != 0:
            for key in keys:
                await self._redis.incrbyfloat(key, diff)
        elif diff != 0:
            # In-memory fallback
            for key in keys:
                self._memory_budget[key] = self._memory_budget.get(key, 0.0) + diff

        reservation.actual_cost = actual_cost
        reservation.finalized = True

        logger.info(
            "budget_finalized",
            reservation_id=reservation.reservation_id,
            estimated=round(reservation.estimated_cost, 6),
            actual=round(actual_cost, 6),
            diff=round(diff, 6),
        )

    async def release(self, reservation: Reservation) -> None:
        """Release a reservation (on failure / cancellation).

        Args:
            reservation: The reservation to release.
        """
        if reservation.finalized or reservation.released:
            return

        keys = reservation.entity_key.split("|")

        if self._redis:
            for key in keys:
                await self._redis.incrbyfloat(key, -reservation.estimated_cost)
        else:
            for key in keys:
                self._memory_budget[key] = self._memory_budget.get(key, 0.0) - reservation.estimated_cost

        reservation.released = True

        logger.info(
            "budget_released",
            reservation_id=reservation.reservation_id,
            amount=round(reservation.estimated_cost, 6),
        )

    async def get_usage(self, department: str) -> BudgetSummary:
        """Get current budget usage for a department.

        Args:
            department: Department to query.

        Returns:
            BudgetSummary with current spend, limits, and utilization.
        """
        from datetime import date
        today = date.today().isoformat()
        key = f"budget:dept:{department}:{today}"

        soft, hard = self._get_limits(f"dept:{department}")

        if self._redis:
            current = float(await self._redis.get(key) or "0")
        else:
            current = self._memory_budget.get(key, 0.0)

        return BudgetSummary(
            entity=department,
            current_spend=round(current, 6),
            soft_limit=soft,
            hard_limit=hard,
            remaining=round(hard - current, 6),
            utilization_pct=round((current / hard) * 100, 2) if hard > 0 else 0,
        )

    async def check_budget(self, department: str, agent_id: str) -> None:
        """Quick check if budget is available (no reservation).

        Raises BudgetExceeded if hard limit is hit,
        BudgetSoftLimit if soft limit is hit.
        """
        from datetime import date
        today = date.today().isoformat()

        dept_key = f"budget:dept:{department}:{today}"
        dept_soft, dept_hard = self._get_limits(f"dept:{department}")

        if self._redis:
            current = float(await self._redis.get(dept_key) or "0")
        else:
            current = self._memory_budget.get(dept_key, 0.0)

        if current >= dept_hard:
            raise BudgetExceeded(department, current, dept_hard, 0)
        if current >= dept_soft:
            raise BudgetSoftLimit(department, current, dept_soft)

    # ── Internal helpers ──────────────────────────

    # In-memory fallback when Redis is unavailable
    _memory_budget: dict[str, float] = {}

    async def _check_and_reserve(
        self, key: str, hard_limit: float, soft_limit: float,
        amount: float, entity: str,
    ) -> None:
        """Check limits and atomically reserve budget."""
        if self._redis:
            result = await self._redis.eval(RESERVE_LUA, 1, key, str(hard_limit), str(amount))
            if result == -1:
                current = float(await self._redis.get(key) or "0")
                raise BudgetExceeded(entity, current, hard_limit, amount)

            current = float(await self._redis.get(key) or "0")
            if current >= soft_limit:
                raise BudgetSoftLimit(entity, current, soft_limit)
        else:
            # In-memory fallback
            current = self._memory_budget.get(key, 0.0)
            if current + amount > hard_limit:
                raise BudgetExceeded(entity, current, hard_limit, amount)
            self._memory_budget[key] = current + amount
            if current + amount >= soft_limit:
                raise BudgetSoftLimit(entity, current + amount, soft_limit)

    async def _rollback(self, key: str, amount: float) -> None:
        """Rollback a reservation."""
        if self._redis:
            await self._redis.incrbyfloat(key, -amount)
        else:
            self._memory_budget[key] = self._memory_budget.get(key, 0.0) - amount


# ── Singleton ─────────────────────────────────────
_budget: BudgetEnforcer | None = None


def get_budget_enforcer(redis_client=None) -> BudgetEnforcer:
    """Get the singleton BudgetEnforcer."""
    global _budget
    if _budget is None:
        _budget = BudgetEnforcer(redis_client)
    return _budget
