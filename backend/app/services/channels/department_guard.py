"""
DepartmentGuard — Enforce department isolation for chat channels.

Policy:
- Known user via chat → ONLY agents from user's own department
- Unknown user via chat → route to Marketing Digital
- Dashboard/API → no enforcement (pass through)
"""

from __future__ import annotations

import structlog

from app.services.orchestration.intent_router import RoutingResult

logger = structlog.get_logger()

# Channels that require department enforcement
CHAT_CHANNELS = {"telegram", "whatsapp"}

# Department for unknown users
DEFAULT_DEPARTMENT_UNKNOWN = "marketing"
DEFAULT_AGENT_UNKNOWN = "MarketingDigitalAgent"

# Department → Supervisor agent name mapping
DEPT_SUPERVISOR_MAP = {
    "tech": "TechSupervisor",
    "finance": "FinanceSupervisor",
    "hr": "HRSupervisor",
    "sales": "SalesSupervisor",
    "marketing": "MarketingDigitalAgent",
}


class DepartmentGuard:
    """Enforce department-locked routing for chat channels.

    Sits between Identity Linker and IntentRouter.
    Overrides routing that crosses department boundaries.
    """

    @classmethod
    def enforce(
        cls,
        channel: str,
        user_department: str | None,
        intent_result: RoutingResult,
    ) -> RoutingResult:
        """Apply department routing policy.

        Args:
            channel: Message channel (telegram, whatsapp, email, dashboard).
            user_department: User's department if known, None if unknown user.
            intent_result: Original routing result from IntentRouter.

        Returns:
            Possibly modified RoutingResult with department enforcement.
        """
        # Dashboard/API/email: no enforcement
        if channel not in CHAT_CHANNELS:
            return intent_result

        # Unknown user → Marketing Digital
        if user_department is None:
            logger.info(
                "department_guard_unknown_user",
                channel=channel,
                routed_to=DEFAULT_DEPARTMENT_UNKNOWN,
            )
            return RoutingResult(
                department=DEFAULT_DEPARTMENT_UNKNOWN,
                agent=DEFAULT_AGENT_UNKNOWN,
                intent=intent_result.intent,
                tools_needed=[],
                priority=intent_result.priority,
                confidence=0.9,
                routing_method="department_guard_unknown",
            )

        # Known user: check if routing stays within department
        if intent_result.department != user_department:
            supervisor = DEPT_SUPERVISOR_MAP.get(
                user_department,
                f"{user_department.capitalize()}Supervisor",
            )
            logger.info(
                "department_guard_cross_dept_blocked",
                channel=channel,
                user_department=user_department,
                attempted_department=intent_result.department,
                redirected_to=supervisor,
            )
            return RoutingResult(
                department=user_department,
                agent=supervisor,
                intent=intent_result.intent,
                tools_needed=[],
                priority=intent_result.priority,
                confidence=0.7,
                routing_method="department_guard_locked",
            )

        # Same department: pass through
        logger.debug(
            "department_guard_ok",
            channel=channel,
            department=user_department,
            agent=intent_result.agent,
        )
        return intent_result
