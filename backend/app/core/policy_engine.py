"""
PolicyEngine — Attribute-Based Access Control (ABAC) for the enterprise OS.

Evaluates access decisions based on:
- Agent identity (role, department, tier)
- Action being performed (tool_call, read, write, llm_call)
- Resource being accessed (tool:send_email, table:employee_pii)
- Context (risk level, data sensitivity, time of day, approval chain)

Rule evaluation order: explicit deny > require_approval > allow.
Default: allow (unless a rule fires).
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import structlog
import yaml

logger = structlog.get_logger()


class PolicyAction(str, Enum):
    """Possible outcomes of a policy evaluation."""

    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


@dataclass
class Obligations:
    """Post-decision obligations the gateway must enforce.

    Examples: mask PII fields, increase log level, add audit detail.
    """

    mask_fields: list[str] = field(default_factory=list)
    log_level: str = "info"
    require_encryption: bool = False
    max_retention_days: int | None = None
    notify_roles: list[str] = field(default_factory=list)


@dataclass
class PolicyContext:
    """Input context for policy evaluation.

    Built by the chokepoint gateways (LLMClient, ToolBroker, DAL)
    from AgentContext + resource metadata.
    """

    agent_id: str
    department: str
    role: str  # "agent" | "supervisor" | "admin"
    tier: str  # "nano" | "standard" | "advanced"
    action: str  # "tool_call" | "read" | "write" | "llm_call"
    resource: str  # "tool:send_email" | "table:employee_pii"
    risk_level: str = "low"  # server-derived risk
    data_sensitivity: str = "public"  # from ResourceClassification
    has_ticket_id: bool = False
    approval_chain: list[str] = field(default_factory=list)
    time_of_day: str = ""  # auto-computed
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.time_of_day:
            hour = datetime.now().hour
            self.time_of_day = "business_hours" if 8 <= hour < 18 else "after_hours"


@dataclass
class PolicyDecision:
    """Result of a policy evaluation."""

    action: PolicyAction
    reason: str
    rule_name: str = ""
    obligations: Obligations | None = None
    audit_ref: str = ""

    @property
    def denied(self) -> bool:
        return self.action == PolicyAction.DENY

    @property
    def needs_approval(self) -> bool:
        return self.action == PolicyAction.REQUIRE_APPROVAL

    @property
    def allowed(self) -> bool:
        return self.action == PolicyAction.ALLOW


def _matches_condition(ctx: PolicyContext, key: str, value: Any) -> bool:
    """Check if a single rule condition matches the context."""
    ctx_value = getattr(ctx, key, None)
    if ctx_value is None:
        return False

    # List match: condition value is a list, ctx value must be in it
    if isinstance(value, list):
        return ctx_value in value

    # Boolean match
    if isinstance(value, bool):
        return ctx_value == value

    # String match
    return str(ctx_value) == str(value)


def _check_requirements(ctx: PolicyContext, requirements: dict[str, Any]) -> bool:
    """Check if requirements are met (for require_approval / deny_if_unmet rules)."""
    for key, value in requirements.items():
        if key == "has_ticket_id":
            if ctx.has_ticket_id != value:
                return False
        elif key == "approval_chain_includes":
            if isinstance(value, list):
                for required_role in value:
                    if required_role not in ctx.approval_chain:
                        return False
            elif value not in ctx.approval_chain:
                return False
        elif key == "tool_registered":
            # This is handled by ToolBroker before PolicyEngine
            pass
        else:
            ctx_value = getattr(ctx, key, None)
            if ctx_value != value:
                return False
    return True


class PolicyEngine:
    """ABAC Policy Engine.

    Loads rules from a YAML config file and evaluates them against
    a PolicyContext. Rules are evaluated in order; first match wins
    (deny > require_approval > allow).

    Usage:
        engine = PolicyEngine("policies/default.yaml")
        decision = engine.evaluate(ctx)
        if decision.denied:
            raise PolicyDenied(decision.reason)
    """

    def __init__(self, rules_path: str | Path | None = None) -> None:
        self._rules: list[dict[str, Any]] = []

        if rules_path:
            self.load_rules(rules_path)

    def load_rules(self, path: str | Path) -> None:
        """Load policy rules from a YAML file.

        Args:
            path: Path to the YAML rules file.
        """
        path = Path(path)
        if not path.exists():
            logger.warning("policy_rules_not_found", path=str(path))
            return

        with open(path) as f:
            data = yaml.safe_load(f)

        self._rules = data.get("rules", [])
        logger.info("policy_rules_loaded", count=len(self._rules), path=str(path))

    def add_rule(self, rule: dict[str, Any]) -> None:
        """Add a rule programmatically (for testing)."""
        self._rules.append(rule)

    def evaluate(self, ctx: PolicyContext) -> PolicyDecision:
        """Evaluate all policy rules against the given context.

        Rule evaluation order: explicit deny > require_approval > allow.
        If no rule matches, default is ALLOW.

        Args:
            ctx: Full context for the access request.

        Returns:
            PolicyDecision with action, reason, and obligations.
        """
        deny_decisions: list[PolicyDecision] = []
        approval_decisions: list[PolicyDecision] = []

        for rule in self._rules:
            name = rule.get("name", "unnamed_rule")
            conditions = rule.get("conditions", {})
            requirements = rule.get("requirements", {})
            decision_type = rule.get("decision", "allow")
            obligations_raw = rule.get("obligations", {})

            # Check if all conditions match
            all_match = all(
                _matches_condition(ctx, k, v)
                for k, v in conditions.items()
            )

            if not all_match:
                continue  # this rule doesn't apply

            # Build obligations
            obligations = None
            if obligations_raw:
                obligations = Obligations(
                    mask_fields=obligations_raw.get("mask_fields", []),
                    log_level=obligations_raw.get("log_level", "info"),
                    require_encryption=obligations_raw.get("require_encryption", False),
                    max_retention_days=obligations_raw.get("max_retention_days"),
                    notify_roles=obligations_raw.get("notify_roles", []),
                )

            # Evaluate decision
            if decision_type == "deny":
                deny_decisions.append(PolicyDecision(
                    action=PolicyAction.DENY,
                    reason=f"Rule '{name}' denied access",
                    rule_name=name,
                    obligations=obligations,
                ))

            elif decision_type == "deny_if_unmet":
                if not _check_requirements(ctx, requirements):
                    deny_decisions.append(PolicyDecision(
                        action=PolicyAction.DENY,
                        reason=f"Rule '{name}': requirements not met",
                        rule_name=name,
                        obligations=obligations,
                    ))

            elif decision_type == "require_approval":
                if not _check_requirements(ctx, requirements):
                    approval_decisions.append(PolicyDecision(
                        action=PolicyAction.REQUIRE_APPROVAL,
                        reason=f"Rule '{name}': approval required",
                        rule_name=name,
                        obligations=obligations,
                    ))

        # Priority: deny > require_approval > allow
        if deny_decisions:
            decision = deny_decisions[0]
            logger.warning(
                "policy_denied",
                agent=ctx.agent_id,
                action=ctx.action,
                resource=ctx.resource,
                rule=decision.rule_name,
                reason=decision.reason,
            )
            return decision

        if approval_decisions:
            decision = approval_decisions[0]
            logger.info(
                "policy_approval_required",
                agent=ctx.agent_id,
                action=ctx.action,
                resource=ctx.resource,
                rule=decision.rule_name,
            )
            return decision

        # Default: allow
        return PolicyDecision(
            action=PolicyAction.ALLOW,
            reason="No policy rule denied or required approval",
            rule_name="default_allow",
        )


# ── Singleton ─────────────────────────────────────
_policy_engine: PolicyEngine | None = None


def get_policy_engine(rules_path: str | Path | None = None) -> PolicyEngine:
    """Get the singleton PolicyEngine instance."""
    global _policy_engine
    if _policy_engine is None:
        _policy_engine = PolicyEngine(rules_path)
    return _policy_engine
