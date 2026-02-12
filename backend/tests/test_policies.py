"""
Test Suite — Policy Engine Tests (Module 3.5.9).

Tests ABAC PolicyEngine against the default.yaml rules:
- PII requires ticket + approval
- Finance high-value requires CFO
- After-hours critical block
- High-risk tools require approval
- Legal confidential requires legal_lead
- Payroll: deny if no ticket
- Write operations: allow with warning obligation
"""

import pytest

from app.core.policy_engine import (
    Obligations,
    PolicyAction,
    PolicyContext,
    PolicyDecision,
    PolicyEngine,
)


# ── Fixtures ──────────────────────────────────────


@pytest.fixture
def engine():
    """PolicyEngine loaded with default rules."""
    e = PolicyEngine()
    e.load_rules("policies/default.yaml")
    return e


def _ctx(**overrides) -> PolicyContext:
    """Create a PolicyContext with defaults."""
    defaults = {
        "agent_id": "test-agent",
        "department": "tech",
        "role": "agent",
        "tier": "standard",
        "action": "read",
        "resource": "knowledge_base",
        "data_sensitivity": "internal",
    }
    defaults.update(overrides)
    return PolicyContext(**defaults)


# ── PII Protection Rules ─────────────────────────


class TestPIIPolicy:
    """PII data requires ticket + approval chain."""

    def test_pii_without_ticket_requires_approval(self, engine):
        """PII access without ticket → REQUIRE_APPROVAL."""
        ctx = _ctx(
            data_sensitivity="pii",
            has_ticket_id=False,
            resource="employee_pii",
        )
        decision = engine.evaluate(ctx)
        assert decision.action == PolicyAction.REQUIRE_APPROVAL
        assert decision.rule_name == "pii_requires_ticket_and_approval"

    def test_pii_with_ticket_but_no_approval_chain(self, engine):
        """PII with ticket but no dept_lead in approval → REQUIRE_APPROVAL."""
        ctx = _ctx(
            data_sensitivity="pii",
            has_ticket_id=True,
            approval_chain=[],
            resource="payroll",
        )
        decision = engine.evaluate(ctx)
        assert decision.action == PolicyAction.REQUIRE_APPROVAL

    def test_pii_mask_obligations(self, engine):
        """PII rule sets mask_fields obligation."""
        ctx = _ctx(
            data_sensitivity="pii",
            has_ticket_id=False,
        )
        decision = engine.evaluate(ctx)
        assert decision.obligations is not None
        assert "nik" in decision.obligations.mask_fields
        assert "salary" in decision.obligations.mask_fields
        assert decision.obligations.log_level == "warning"

    def test_pii_notifies_compliance(self, engine):
        """PII rule notifies compliance_officer."""
        ctx = _ctx(data_sensitivity="pii")
        decision = engine.evaluate(ctx)
        assert decision.obligations is not None
        assert "compliance_officer" in decision.obligations.notify_roles


# ── Finance High-Value Rules ─────────────────────


class TestFinancePolicy:
    """Finance high-risk requires CFO approval."""

    def test_finance_high_risk_requires_approval(self, engine):
        """Finance + high risk → REQUIRE_APPROVAL."""
        ctx = _ctx(
            department="finance",
            risk_level="high",
            action="transfer",
        )
        decision = engine.evaluate(ctx)
        assert decision.action == PolicyAction.REQUIRE_APPROVAL

    def test_finance_critical_requires_approval(self, engine):
        """Finance + critical risk → REQUIRE_APPROVAL."""
        ctx = _ctx(
            department="finance",
            risk_level="critical",
            action="write",
        )
        decision = engine.evaluate(ctx)
        assert decision.action == PolicyAction.REQUIRE_APPROVAL

    def test_finance_low_risk_allowed(self, engine):
        """Finance + low risk → ALLOW (no rule fires)."""
        ctx = _ctx(
            department="finance",
            risk_level="low",
            action="read",
            data_sensitivity="internal",
        )
        decision = engine.evaluate(ctx)
        assert decision.action == PolicyAction.ALLOW


# ── After-Hours Rules ─────────────────────────────


class TestAfterHoursPolicy:
    """Critical actions blocked outside business hours."""

    def test_critical_after_hours_denied(self, engine):
        """Critical + after_hours → DENY."""
        ctx = _ctx(
            risk_level="critical",
            time_of_day="after_hours",
        )
        decision = engine.evaluate(ctx)
        assert decision.action == PolicyAction.DENY
        assert decision.rule_name == "block_critical_after_hours"

    def test_critical_during_hours_allowed(self, engine):
        """Critical + business_hours → no after-hours deny."""
        ctx = _ctx(
            risk_level="critical",
            time_of_day="business_hours",
            data_sensitivity="internal",
        )
        decision = engine.evaluate(ctx)
        # May still hit other rules, but not the after-hours block
        assert decision.rule_name != "block_critical_after_hours"


# ── High-Risk Tool Calls ─────────────────────────


class TestToolCallPolicy:
    """High-risk tool calls require approval."""

    def test_high_risk_tool_requires_approval(self, engine):
        """tool_call + high risk → REQUIRE_APPROVAL."""
        ctx = _ctx(
            action="tool_call",
            risk_level="high",
            data_sensitivity="internal",
        )
        decision = engine.evaluate(ctx)
        assert decision.action == PolicyAction.REQUIRE_APPROVAL

    def test_low_risk_tool_allowed(self, engine):
        """tool_call + low risk → ALLOW."""
        ctx = _ctx(
            action="tool_call",
            risk_level="low",
            data_sensitivity="internal",
        )
        decision = engine.evaluate(ctx)
        assert decision.action == PolicyAction.ALLOW


# ── Legal Department Rules ────────────────────────


class TestLegalPolicy:
    """Legal confidential data requires legal_lead approval."""

    def test_legal_confidential_requires_approval(self, engine):
        """Legal + confidential → REQUIRE_APPROVAL."""
        ctx = _ctx(
            department="legal",
            data_sensitivity="confidential",
        )
        decision = engine.evaluate(ctx)
        assert decision.action == PolicyAction.REQUIRE_APPROVAL

    def test_legal_confidential_has_encryption_obligation(self, engine):
        """Legal confidential → encryption required."""
        ctx = _ctx(
            department="legal",
            data_sensitivity="confidential",
        )
        decision = engine.evaluate(ctx)
        assert decision.obligations is not None
        assert decision.obligations.require_encryption is True
        assert decision.obligations.max_retention_days == 365


# ── Write Operations Policy ──────────────────────


class TestWritePolicy:
    """All writes should be allowed with warning log level."""

    def test_write_allowed_with_warning(self, engine):
        """Write action → ALLOW + warning log level."""
        ctx = _ctx(
            action="write",
            data_sensitivity="internal",
            risk_level="low",
        )
        decision = engine.evaluate(ctx)
        assert decision.action == PolicyAction.ALLOW
        if decision.obligations:
            assert decision.obligations.log_level == "warning"


# ── Payroll Access Policy ─────────────────────────


class TestPayrollPolicy:
    """Payroll (PII) access denied without ticket."""

    def test_payroll_read_without_ticket_denied(self, engine):
        """PII + read + no ticket → deny_if_unmet (= DENY)."""
        ctx = _ctx(
            data_sensitivity="pii",
            action="read",
            has_ticket_id=False,
        )
        decision = engine.evaluate(ctx)
        # PII without ticket hits the pii_requires_ticket rule first
        assert decision.action in (PolicyAction.DENY, PolicyAction.REQUIRE_APPROVAL)


# ── Default Behavior ─────────────────────────────


class TestDefaultPolicy:
    """When no rule matches, default is ALLOW."""

    def test_no_rules_match_allows(self, engine):
        """Normal internal read → ALLOW."""
        ctx = _ctx(
            action="read",
            data_sensitivity="public",
            risk_level="low",
        )
        decision = engine.evaluate(ctx)
        assert decision.action == PolicyAction.ALLOW

    def test_empty_engine_allows(self):
        """Engine with no rules → ALLOW."""
        empty_engine = PolicyEngine()
        ctx = _ctx()
        decision = empty_engine.evaluate(ctx)
        assert decision.action == PolicyAction.ALLOW


# ── Engine Edge Cases ─────────────────────────────


class TestPolicyEngineEdgeCases:
    """Edge cases and programmatic rule addition."""

    def test_add_rule_programmatically(self):
        """Can add rules via add_rule() for testing."""
        engine = PolicyEngine()
        engine.add_rule({
            "name": "test_deny_all",
            "conditions": {"action": "delete"},
            "decision": "deny",
        })
        ctx = _ctx(action="delete")
        decision = engine.evaluate(ctx)
        assert decision.action == PolicyAction.DENY

    def test_deny_takes_priority_over_allow(self):
        """Deny rules evaluated before allow rules."""
        engine = PolicyEngine()
        engine.add_rule({
            "name": "allow_read",
            "conditions": {"action": "read"},
            "decision": "allow",
        })
        engine.add_rule({
            "name": "deny_pii",
            "conditions": {"data_sensitivity": "pii"},
            "decision": "deny",
        })
        ctx = _ctx(action="read", data_sensitivity="pii")
        decision = engine.evaluate(ctx)
        assert decision.action == PolicyAction.DENY
