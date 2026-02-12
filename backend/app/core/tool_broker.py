"""
ToolBroker — Single Chokepoint for all tool executions.

Every tool call in the system MUST go through ToolBroker.execute().
It enforces: tool allowlist, ABAC policy, obligations, network egress,
file sandbox, and audit logging.

No agent may directly invoke tool handlers or make external calls.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from app.core.approval_gate import ApprovalGate
from app.core.policy_context import PolicyContextBuilder, sanitize_args
from app.core.policy_engine import PolicyAction, get_policy_engine
from app.core.sandbox import NetworkPolicy, TaskSandbox
from app.core.tool_registry import RiskLevel, ToolAccessDenied, ToolMeta, ToolNotFound, ToolRegistry

logger = structlog.get_logger()


class ToolCallDenied(Exception):
    """Raised when a tool call is denied by the broker."""

    def __init__(self, tool_name: str, reason: str):
        self.tool_name = tool_name
        self.reason = reason
        super().__init__(f"Tool call denied: '{tool_name}' — {reason}")


@dataclass
class ToolResult:
    """Structured result from a tool execution."""

    tool_name: str
    success: bool
    output: Any = None
    error: str | None = None
    artifacts: list[str] = field(default_factory=list)
    execution_time_ms: float = 0.0
    risk_level: str = "low"
    # ── ABAC enrichment ──
    status: str = "success"  # "success" | "error" | "needs_approval"
    approval_id: str | None = None
    policy_decision: str = ""  # "allow" | "deny" | "require_approval"
    obligations: dict | None = None


class ToolBroker:
    """Sole gateway for all tool executions.

    Execution flow:
    1. Resolve tool from registry (unknown → deny)
    2. Check role/department access
    2.5. PolicyEngine evaluation (NON-BYPASSABLE)
    2.6. Obligations enforcement
    3. Check network egress (if tool has_egress)
    4. Check file path (if tool has_file_access)
    5. Log the attempt (with policy decision)
    6. Execute handler
    7. Log the result
    """

    async def execute(
        self,
        ctx: "AgentContext",
        tool_name: str,
        args: dict[str, Any],
    ) -> ToolResult:
        """Execute a tool through the single chokepoint.

        All controls are enforced here. No tool can be called
        without going through this method.

        Args:
            ctx: Agent context (from LLMClient.AgentContext).
            tool_name: Name of the tool to execute.
            args: Arguments to pass to the tool handler.

        Returns:
            ToolResult with output, artifacts, timing, and policy decision.

        Raises:
            ToolNotFound: If tool is not registered.
            ToolAccessDenied: If agent's role/dept can't use this tool.
            ToolCallDenied: If any policy check fails.
        """
        start_time = time.monotonic()
        args_hash = hashlib.sha256(
            json.dumps(args, sort_keys=True, default=str).encode()
        ).hexdigest()

        # ── Step 1: Resolve tool ──
        try:
            tool_meta: ToolMeta = ToolRegistry.resolve(tool_name)
        except ToolNotFound:
            logger.warning(
                "tool_call_denied",
                trace_id=ctx.trace_id,
                agent=ctx.agent_name,
                tool=tool_name,
                reason="not_registered",
            )
            raise

        # ── Step 2: Check role/department access ──
        if not tool_meta.is_allowed_for(ctx.role, ctx.department):
            logger.warning(
                "tool_call_denied",
                trace_id=ctx.trace_id,
                agent=ctx.agent_name,
                tool=tool_name,
                reason="access_denied",
                agent_role=ctx.role,
                department=ctx.department,
            )
            raise ToolAccessDenied(tool_name, ctx.role, ctx.department)

        # ── Step 2.5: PolicyEngine evaluation (NON-BYPASSABLE) ──
        policy_ctx = PolicyContextBuilder.for_tool_call(ctx, tool_meta, args)
        decision = get_policy_engine().evaluate(policy_ctx)

        # Emit policy_evaluated event (ALWAYS, before any tool execution)
        logger.info(
            "policy_evaluated",
            trace_id=ctx.trace_id,
            span_id=ctx.span_id,
            agent=ctx.agent_name,
            tool=tool_name,
            decision=decision.action.value,
            rule=decision.rule_name,
            risk_level=policy_ctx.risk_level,
            data_sensitivity=policy_ctx.data_sensitivity,
        )

        if decision.denied:
            # Emit policy_denied + tool_blocked
            logger.warning(
                "tool_blocked",
                trace_id=ctx.trace_id,
                agent=ctx.agent_name,
                tool=tool_name,
                reason=decision.reason,
                rule=decision.rule_name,
            )
            raise ToolCallDenied(tool_name, decision.reason)

        if decision.needs_approval:
            # Non-blocking approval: create record, return pending, do NOT call handler
            approval_result = ApprovalGate.check(
                trace_id=ctx.trace_id,
                task_id=ctx.task_id,
                agent_name=ctx.agent_name,
                department=ctx.department,
                action="tool_call",
                resource=f"tool:{tool_name}",
                risk_level=policy_ctx.risk_level,
                policy_reason=decision.reason,
                required_approvers=decision.obligations.notify_roles if decision.obligations else None,
            )

            logger.info(
                "approval_requested",
                trace_id=ctx.trace_id,
                agent=ctx.agent_name,
                tool=tool_name,
                approval_id=approval_result.approval_id,
                reason=decision.reason,
            )

            elapsed_ms = (time.monotonic() - start_time) * 1000
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=None,
                execution_time_ms=elapsed_ms,
                risk_level=tool_meta.risk_level.value,
                status="needs_approval",
                approval_id=approval_result.approval_id,
                policy_decision="require_approval",
                obligations=self._obligations_to_dict(decision.obligations),
            )

        # ── Step 2.6: Obligations enforcement ──
        obligations_dict = self._obligations_to_dict(decision.obligations)
        log_args_sanitized = args
        if decision.obligations and decision.obligations.mask_fields:
            log_args_sanitized = sanitize_args(args, decision.obligations.mask_fields)

        # ── Step 3: Network egress check ──
        if tool_meta.has_egress:
            url = args.get("url", "")
            if url:
                NetworkPolicy.check_egress(tool_name, url, tool_meta.egress_domains)

        # ── Step 4: File path check ──
        if tool_meta.has_file_access:
            path = args.get("path", "")
            if path and ctx.task_id:
                TaskSandbox.validate_path(ctx.task_id, path)

        # ── Step 5: Log attempt (with sanitized args) ──
        logger.info(
            "tool_call_start",
            trace_id=ctx.trace_id,
            span_id=ctx.span_id,
            agent=ctx.agent_name,
            tool=tool_name,
            risk=policy_ctx.risk_level,
            policy_decision="allow",
            args_hash=args_hash[:16],
        )

        # ── Step 6: Execute handler ──
        try:
            output = await tool_meta.handler(**args)
        except Exception as exc:
            elapsed_ms = (time.monotonic() - start_time) * 1000
            logger.error(
                "tool_call_error",
                trace_id=ctx.trace_id,
                agent=ctx.agent_name,
                tool=tool_name,
                error=str(exc),
                elapsed_ms=int(elapsed_ms),
            )
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=str(exc),
                execution_time_ms=elapsed_ms,
                risk_level=tool_meta.risk_level.value,
                status="error",
                policy_decision="allow",
                obligations=obligations_dict,
            )

        elapsed_ms = (time.monotonic() - start_time) * 1000

        # ── Step 7: Collect artifacts ──
        artifacts: list[str] = []
        if ctx.task_id:
            artifacts = TaskSandbox.list_artifacts(ctx.task_id)

        # ── Step 8: Log result ──
        logger.info(
            "tool_call_complete",
            trace_id=ctx.trace_id,
            span_id=ctx.span_id,
            agent=ctx.agent_name,
            tool=tool_name,
            success=True,
            elapsed_ms=int(elapsed_ms),
            artifact_count=len(artifacts),
            policy_decision="allow",
        )

        return ToolResult(
            tool_name=tool_name,
            success=True,
            output=output,
            artifacts=artifacts,
            execution_time_ms=elapsed_ms,
            risk_level=tool_meta.risk_level.value,
            status="success",
            policy_decision="allow",
            obligations=obligations_dict,
        )

    def get_available_tools(self, role: str, department: str) -> list[dict]:
        """Get tool definitions for an agent (OpenAI function format).

        Args:
            role: Agent role.
            department: Agent department.

        Returns:
            List of tool definitions in OpenAI function calling format.
        """
        tools = ToolRegistry.get_tools_for(role, department)
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters if t.parameters else {
                        "type": "object",
                        "properties": {},
                    },
                },
            }
            for t in tools
        ]

    @staticmethod
    def _obligations_to_dict(obligations) -> dict | None:
        """Convert Obligations dataclass to dict for ToolResult."""
        if not obligations:
            return None
        return {
            "mask_fields": obligations.mask_fields,
            "log_level": obligations.log_level,
            "require_encryption": obligations.require_encryption,
            "max_retention_days": obligations.max_retention_days,
            "notify_roles": obligations.notify_roles,
        }


# ── Singleton ─────────────────────────────────────
_tool_broker: ToolBroker | None = None


def get_tool_broker() -> ToolBroker:
    """Get the singleton ToolBroker instance."""
    global _tool_broker
    if _tool_broker is None:
        _tool_broker = ToolBroker()
    return _tool_broker
