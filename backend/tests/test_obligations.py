"""
Test Suite — Obligations enforcement.

Tests that mask_fields obligations are enforced in both
log args and audit payloads, and that obligations metadata
is present in ToolResult.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.llm_client import AgentContext
from app.core.policy_context import sanitize_args
from app.core.policy_engine import Obligations, PolicyAction, PolicyDecision
from app.core.tool_broker import ToolBroker, ToolResult
from app.core.tool_registry import RiskLevel, ToolMeta, ToolRegistry


# ── Fixtures ─────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_registry():
    ToolRegistry._tools.clear()
    yield
    ToolRegistry._tools.clear()


@pytest.fixture
def agent_ctx():
    return AgentContext(
        agent_id="agent-hr-1",
        agent_name="HRBot",
        department="hr",
        tier="standard",
        role="agent",
        task_id="task-002",
    )


@pytest.fixture
def broker():
    return ToolBroker()


# ── Test: Mask Fields Sanitizes Log Args ─────────

class TestMaskFieldsSanitizesLogArgs:
    def test_sanitize_args_masks_pii_fields(self):
        """Direct test of sanitize_args helper."""
        args = {
            "email": "private@x.com",
            "phone": "08123456789",
            "name": "John Doe",
            "query": "SELECT * FROM users",
        }
        result = sanitize_args(args, ["email", "phone"])

        assert result["email"] == "***MASKED***"
        assert result["phone"] == "***MASKED***"
        assert result["name"] == "John Doe"
        assert result["query"] == "SELECT * FROM users"

    def test_sanitize_args_case_insensitive(self):
        """Mask field matching should be case-insensitive."""
        args = {"Email": "test@x.com", "PHONE": "123"}
        result = sanitize_args(args, ["email", "phone"])

        assert result["Email"] == "***MASKED***"
        assert result["PHONE"] == "***MASKED***"


# ── Test: Obligations Metadata in ToolResult ─────

class TestObligationsInToolResult:
    @pytest.mark.asyncio
    async def test_allowed_with_obligations_includes_metadata(self, broker, agent_ctx):
        """When policy allows with obligations, ToolResult should contain obligations dict."""
        handler = AsyncMock(return_value={"data": "sensitive"})
        tool = ToolMeta(
            name="read_pii_data",
            handler=handler,
            risk_level=RiskLevel.HIGH,
            allowed_roles={"agent"},
            allowed_departments={"*"},
        )
        ToolRegistry.register(tool)

        allow_with_obligations = PolicyDecision(
            action=PolicyAction.ALLOW,
            reason="Allowed with masking obligations",
            rule_name="pii_with_masking",
            obligations=Obligations(
                mask_fields=["nik", "salary"],
                log_level="warning",
                require_encryption=True,
                notify_roles=["hr_manager"],
            ),
        )

        with patch("app.core.tool_broker.get_policy_engine") as mock_engine:
            mock_engine.return_value.evaluate.return_value = allow_with_obligations

            result = await broker.execute(agent_ctx, "read_pii_data", {"employee_id": "E001"})

            assert result.success is True
            assert result.obligations is not None
            assert result.obligations["mask_fields"] == ["nik", "salary"]
            assert result.obligations["log_level"] == "warning"
            assert result.obligations["require_encryption"] is True
            assert result.obligations["notify_roles"] == ["hr_manager"]
