"""
Test Suite — PolicyContextBuilder (policy_context.py).

Tests:
- Complete context construction for tool calls and LLM calls
- Composite risk level calculation
- Terminal command classification
- PII argument sensitivity detection
"""

import pytest

from app.core.policy_context import (
    PolicyContextBuilder,
    _max_risk,
    _max_sensitivity,
    classify_args,
    classify_terminal_command,
    sanitize_args,
)
from app.core.tool_registry import RiskLevel, ToolMeta


# ── Helpers ──────────────────────────────────────

def _make_ctx(**overrides):
    """Create a minimal AgentContext-like object for testing."""
    from dataclasses import dataclass, field as dc_field

    @dataclass
    class FakeCtx:
        agent_id: str = "agent-1"
        agent_name: str = "FinanceBot"
        department: str = "finance"
        tier: str = "standard"
        role: str = "agent"
        trace_id: str = "trace-abc"
        span_id: str = "span-123"
        task_id: str = "task-001"
        requester_id: str = "user-1"
        ticket_id: str = ""
        approval_chain: list = dc_field(default_factory=list)
        data_sensitivity: str = "internal"
        risk_level: str = "low"

    return FakeCtx(**overrides)


async def _dummy_handler(**kwargs):
    return {"ok": True}


def _make_tool_meta(**overrides):
    """Create a ToolMeta for testing."""
    defaults = {
        "name": "test_tool",
        "handler": _dummy_handler,
        "risk_level": RiskLevel.LOW,
        "data_sensitivity_default": "internal",
        "side_effect_level": "none",
        "arg_sensitivity_hints": [],
    }
    defaults.update(overrides)
    return ToolMeta(**defaults)


# ── Composite Risk ───────────────────────────────

class TestCompositeRisk:
    def test_max_risk_low_vs_high(self):
        assert _max_risk("low", "high") == "high"

    def test_max_risk_critical_vs_medium(self):
        assert _max_risk("critical", "medium") == "critical"

    def test_max_risk_same(self):
        assert _max_risk("medium", "medium") == "medium"

    def test_max_sensitivity_internal_vs_pii(self):
        assert _max_sensitivity("internal", "pii") == "pii"


# ── Terminal Command Classification ──────────────

class TestTerminalCommandClassification:
    def test_read_only_git_status(self):
        assert classify_terminal_command("git status") == "read_only"

    def test_read_only_ls(self):
        assert classify_terminal_command("ls -la") == "read_only"

    def test_write_repo_git_push(self):
        assert classify_terminal_command("git push origin main") == "write_repo"

    def test_install_pip(self):
        assert classify_terminal_command("pip install requests") == "install"

    def test_network_curl(self):
        assert classify_terminal_command("curl https://example.com") == "network"

    def test_destructive_rm(self):
        assert classify_terminal_command("rm -rf /tmp/data") == "destructive"

    def test_destructive_sudo(self):
        assert classify_terminal_command("sudo apt update") == "destructive"

    def test_unknown_command(self):
        assert classify_terminal_command("python main.py") == "unknown"

    def test_empty_command(self):
        assert classify_terminal_command("") == "unknown"


# ── Arg Sensitivity ──────────────────────────────

class TestArgSensitivity:
    def test_detects_pii_from_hints(self):
        result = classify_args(
            {"email_personal": "test@x.com", "name": "John"},
            hints=["email_personal"]
        )
        assert result == "pii"

    def test_detects_pii_from_builtin_patterns(self):
        result = classify_args({"salary": 50000, "dept": "finance"})
        assert result == "pii"

    def test_no_pii_returns_internal(self):
        result = classify_args({"query": "select", "limit": 10})
        assert result == "internal"

    def test_empty_args_returns_internal(self):
        assert classify_args({}) == "internal"


# ── PolicyContextBuilder ────────────────────────

class TestPolicyContextBuilder:
    def test_for_tool_call_builds_complete_context(self):
        ctx = _make_ctx(ticket_id="TIX-001", risk_level="medium")
        tool = _make_tool_meta(name="send_email", risk_level=RiskLevel.HIGH)
        args = {"to": "user@example.com", "body": "Hello"}

        policy_ctx = PolicyContextBuilder.for_tool_call(ctx, tool, args)

        assert policy_ctx.agent_id == "agent-1"
        assert policy_ctx.department == "finance"
        assert policy_ctx.action == "tool_call"
        assert policy_ctx.resource == "tool:send_email"
        assert policy_ctx.risk_level == "high"  # max(medium, high)
        assert policy_ctx.has_ticket_id is True
        assert policy_ctx.metadata["trace_id"] == "trace-abc"
        assert policy_ctx.metadata["side_effect_level"] == "none"

    def test_composite_risk_uses_max(self):
        ctx = _make_ctx(risk_level="low")
        tool = _make_tool_meta(risk_level=RiskLevel.CRITICAL)
        args = {}

        policy_ctx = PolicyContextBuilder.for_tool_call(ctx, tool, args)
        assert policy_ctx.risk_level == "critical"

    def test_terminal_tool_classifies_command(self):
        ctx = _make_ctx()
        tool = _make_tool_meta(name="terminal_exec")
        args = {"command": "git push origin main"}

        policy_ctx = PolicyContextBuilder.for_tool_call(ctx, tool, args)
        assert policy_ctx.metadata.get("command_category") == "write_repo"

    def test_for_llm_call_context(self):
        ctx = _make_ctx(risk_level="high", data_sensitivity="confidential")

        policy_ctx = PolicyContextBuilder.for_llm_call(ctx, "gpt-4o")

        assert policy_ctx.action == "llm_call"
        assert policy_ctx.resource == "model:gpt-4o"
        assert policy_ctx.risk_level == "high"
        assert policy_ctx.data_sensitivity == "confidential"


# ── Sanitize Args ────────────────────────────────

class TestSanitizeArgs:
    def test_masks_specified_fields(self):
        args = {"email": "test@x.com", "name": "John", "phone": "123"}
        result = sanitize_args(args, ["email", "phone"])

        assert result["email"] == "***MASKED***"
        assert result["phone"] == "***MASKED***"
        assert result["name"] == "John"

    def test_does_not_mutate_original(self):
        args = {"email": "test@x.com"}
        sanitize_args(args, ["email"])
        assert args["email"] == "test@x.com"

    def test_no_mask_fields_returns_copy(self):
        args = {"key": "value"}
        result = sanitize_args(args, [])
        assert result == args
        assert result is not args
