"""
Test Suite — LLMClient + PolicyEngine integration.

Tests that PolicyEngine is NON-BYPASSABLE in LLMClient.call():
- Denied LLM calls raise LLMCallDenied (no HTTP call)
- Require_approval returns LLMResponse with needs_approval status (no HTTP call)
- Allowed calls proceed normally
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.llm_client import AgentContext, LLMCallDenied, LLMClient, LLMResponse
from app.core.policy_engine import PolicyAction, PolicyDecision


# ── Fixtures ─────────────────────────────────────

@pytest.fixture
def agent_ctx():
    return AgentContext(
        agent_id="agent-sales-1",
        agent_name="SalesBot",
        department="sales",
        tier="standard",
        role="agent",
        task_id="task-003",
    )


@pytest.fixture
def client():
    return LLMClient()


# ── Test: Denied LLM Call ────────────────────────

class TestDeniedLLMCall:
    @pytest.mark.asyncio
    async def test_denied_raises_exception(self, client, agent_ctx):
        """When PolicyEngine returns DENY, LLMCallDenied must be raised."""
        deny_decision = PolicyDecision(
            action=PolicyAction.DENY,
            reason="Rule 'block_llm_after_hours' denied access",
            rule_name="block_llm_after_hours",
        )

        with patch("app.core.llm_client.get_policy_engine") as mock_engine, \
             patch("httpx.AsyncClient") as mock_http:

            mock_engine.return_value.evaluate.return_value = deny_decision

            with pytest.raises(LLMCallDenied) as exc_info:
                await client.call(
                    agent_ctx,
                    messages=[{"role": "user", "content": "Hello"}],
                )

            assert "block_llm_after_hours" in str(exc_info.value)
            # HTTP client should NOT have been used
            mock_http.assert_not_called()


# ── Test: Require Approval ───────────────────────

class TestRequireApprovalLLMCall:
    @pytest.mark.asyncio
    async def test_require_approval_returns_pending(self, client, agent_ctx):
        """When PolicyEngine returns REQUIRE_APPROVAL, return LLMResponse with needs_approval."""
        approval_decision = PolicyDecision(
            action=PolicyAction.REQUIRE_APPROVAL,
            reason="Rule 'llm_approval_needed': approval required",
            rule_name="llm_approval_needed",
        )

        with patch("app.core.llm_client.get_policy_engine") as mock_engine, \
             patch("httpx.AsyncClient") as mock_http:

            mock_engine.return_value.evaluate.return_value = approval_decision

            result = await client.call(
                agent_ctx,
                messages=[{"role": "user", "content": "Generate report"}],
            )

            assert result.status == "needs_approval"
            assert result.content == ""
            # HTTP client should NOT have been used
            mock_http.assert_not_called()


# ── Test: Allowed LLM Call ───────────────────────

class TestAllowedLLMCall:
    @pytest.mark.asyncio
    async def test_allowed_call_proceeds(self, client, agent_ctx):
        """When PolicyEngine returns ALLOW, the LLM call should proceed normally."""
        allow_decision = PolicyDecision(
            action=PolicyAction.ALLOW,
            reason="Default allow",
            rule_name="default_allow",
        )

        mock_response_data = {
            "choices": [{"message": {"content": "Hello, world!"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }

        with patch("app.core.llm_client.get_policy_engine") as mock_engine, \
             patch("httpx.AsyncClient") as mock_http_cls:

            mock_engine.return_value.evaluate.return_value = allow_decision

            # Mock the HTTP response
            mock_response = MagicMock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status = MagicMock()

            mock_client_instance = AsyncMock()
            mock_client_instance.post.return_value = mock_response
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_http_cls.return_value = mock_client_instance

            result = await client.call(
                agent_ctx,
                messages=[{"role": "user", "content": "Hello"}],
            )

            assert result.content == "Hello, world!"
            assert result.prompt_tokens == 10
            assert result.prompt_hash != ""
