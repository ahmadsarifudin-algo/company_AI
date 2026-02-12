"""
Test Suite — ToolBroker + PolicyEngine integration.

Tests that PolicyEngine is NON-BYPASSABLE in ToolBroker.execute():
- Denied tool calls never invoke handler
- Require_approval tool calls never invoke handler, return needs_approval
- Allowed tool calls proceed normally
- Time-based and PII-based policy rules
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.core.llm_client import AgentContext
from app.core.policy_engine import Obligations, PolicyAction, PolicyDecision
from app.core.tool_broker import ToolBroker, ToolCallDenied, ToolResult
from app.core.tool_registry import RiskLevel, ToolMeta, ToolRegistry


# ── Fixtures ─────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_registry():
    """Clear tool registry before each test."""
    ToolRegistry._tools.clear()
    yield
    ToolRegistry._tools.clear()


@pytest.fixture
def agent_ctx():
    """Standard agent context for testing."""
    return AgentContext(
        agent_id="agent-finance-1",
        agent_name="FinanceBot",
        department="finance",
        tier="standard",
        role="agent",
        task_id="task-001",
        ticket_id="",
        risk_level="low",
    )


@pytest.fixture
def broker():
    return ToolBroker()


def _register_tool(name="test_tool", risk=RiskLevel.LOW, **kwargs):
    """Register a dummy tool and return its handler mock."""
    handler = AsyncMock(return_value={"result": "ok"})
    meta = ToolMeta(
        name=name,
        handler=handler,
        risk_level=risk,
        allowed_roles={"agent"},
        allowed_departments={"*"},
        **kwargs,
    )
    ToolRegistry.register(meta)
    return handler


# ── Test: Denied by Policy ───────────────────────

class TestToolCallDeniedByPolicy:
    @pytest.mark.asyncio
    async def test_denied_tool_handler_not_called(self, broker, agent_ctx):
        """When PolicyEngine returns DENY, the handler must NOT be called."""
        handler = _register_tool("send_email")

        deny_decision = PolicyDecision(
            action=PolicyAction.DENY,
            reason="Rule 'block_after_hours' denied access",
            rule_name="block_after_hours",
        )

        with patch("app.core.tool_broker.get_policy_engine") as mock_engine:
            mock_engine.return_value.evaluate.return_value = deny_decision

            with pytest.raises(ToolCallDenied) as exc_info:
                await broker.execute(agent_ctx, "send_email", {"to": "user@x.com"})

            assert "send_email" in str(exc_info.value)
            handler.assert_not_called()


# ── Test: Requires Approval ──────────────────────

class TestToolCallRequiresApproval:
    @pytest.mark.asyncio
    async def test_approval_returns_needs_approval_status(self, broker, agent_ctx):
        """When PolicyEngine returns REQUIRE_APPROVAL, handler NOT called, result has approval_id."""
        handler = _register_tool("access_payroll")

        approval_decision = PolicyDecision(
            action=PolicyAction.REQUIRE_APPROVAL,
            reason="Rule 'payroll_access_hr_only': approval required",
            rule_name="payroll_access_hr_only",
            obligations=Obligations(notify_roles=["hr_manager"]),
        )

        with patch("app.core.tool_broker.get_policy_engine") as mock_engine:
            mock_engine.return_value.evaluate.return_value = approval_decision

            result = await broker.execute(agent_ctx, "access_payroll", {"employee_id": "E001"})

            assert result.status == "needs_approval"
            assert result.approval_id is not None
            assert result.policy_decision == "require_approval"
            handler.assert_not_called()


# ── Test: Allowed by Policy ──────────────────────

class TestToolCallAllowedByPolicy:
    @pytest.mark.asyncio
    async def test_allowed_tool_executes_handler(self, broker, agent_ctx):
        """When PolicyEngine returns ALLOW, handler is called and result is success."""
        handler = _register_tool("search_data")

        allow_decision = PolicyDecision(
            action=PolicyAction.ALLOW,
            reason="No policy rule denied or required approval",
            rule_name="default_allow",
        )

        with patch("app.core.tool_broker.get_policy_engine") as mock_engine:
            mock_engine.return_value.evaluate.return_value = allow_decision

            result = await broker.execute(agent_ctx, "search_data", {"query": "revenue"})

            assert result.success is True
            assert result.status == "success"
            assert result.policy_decision == "allow"
            handler.assert_called_once_with(query="revenue")


# ── Test: Critical After Hours ───────────────────

class TestCriticalAfterHours:
    @pytest.mark.asyncio
    async def test_critical_tool_blocked_after_hours(self, broker, agent_ctx):
        """Critical risk tool should be denied after hours by policy."""
        handler = _register_tool("deploy_prod", risk=RiskLevel.CRITICAL)

        deny_decision = PolicyDecision(
            action=PolicyAction.DENY,
            reason="Rule 'block_critical_after_hours' denied access",
            rule_name="block_critical_after_hours",
        )

        with patch("app.core.tool_broker.get_policy_engine") as mock_engine:
            mock_engine.return_value.evaluate.return_value = deny_decision

            with pytest.raises(ToolCallDenied):
                await broker.execute(agent_ctx, "deploy_prod", {"env": "production"})

            handler.assert_not_called()


# ── Test: PII Requires Ticket ────────────────────

class TestPiiRequiresTicket:
    @pytest.mark.asyncio
    async def test_pii_tool_without_ticket_requires_approval(self, broker, agent_ctx):
        """PII access without ticket should trigger require_approval."""
        handler = _register_tool(
            "read_employee_data",
            data_sensitivity_default="pii",
            arg_sensitivity_hints=["salary", "nik"],
        )
        agent_ctx.ticket_id = ""  # No ticket

        approval_decision = PolicyDecision(
            action=PolicyAction.REQUIRE_APPROVAL,
            reason="Rule 'pii_requires_ticket_and_approval': approval required",
            rule_name="pii_requires_ticket_and_approval",
        )

        with patch("app.core.tool_broker.get_policy_engine") as mock_engine:
            mock_engine.return_value.evaluate.return_value = approval_decision

            result = await broker.execute(
                agent_ctx, "read_employee_data", {"salary": 50000}
            )

            assert result.status == "needs_approval"
            handler.assert_not_called()
