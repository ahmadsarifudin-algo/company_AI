"""
PolicyContextBuilder — Consistent PolicyContext construction for all chokepoints.

Single builder ensuring ToolBroker, LLMClient, and DAL all build
PolicyContext the same way. Includes classifier utilities for
argument sensitivity and terminal command classification.
"""

import re
from typing import Any

from app.core.policy_engine import PolicyContext
from app.core.tool_registry import ToolMeta


# ── Risk level ordering ──────────────────────────
RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
SENSITIVITY_ORDER = {"public": 0, "internal": 1, "confidential": 2, "pii": 3}
SENSITIVITY_REVERSE = {0: "public", 1: "internal", 2: "confidential", 3: "pii"}


def _max_risk(a: str, b: str) -> str:
    """Return the higher risk level between two values."""
    a_val = RISK_ORDER.get(a, 0)
    b_val = RISK_ORDER.get(b, 0)
    return a if a_val >= b_val else b


def _max_sensitivity(a: str, b: str) -> str:
    """Return the higher sensitivity level between two values."""
    a_val = SENSITIVITY_ORDER.get(a, 1)
    b_val = SENSITIVITY_ORDER.get(b, 1)
    return a if a_val >= b_val else b


# ── Arg classifier ───────────────────────────────

# Built-in PII patterns (field names that are likely PII)
_BUILTIN_PII_PATTERNS = {
    "nik", "ktp", "npwp", "rekening", "account_number", "bank_account",
    "phone", "phone_number", "mobile", "email_personal", "alamat",
    "address", "home_address", "salary", "gaji", "take_home_pay",
    "ssn", "social_security", "passport", "birth_date", "tanggal_lahir",
}


def classify_args(args: dict[str, Any], hints: list[str] | None = None) -> str:
    """Classify argument sensitivity based on field names.

    Checks arg keys against:
    1. ToolMeta.arg_sensitivity_hints (explicit per-tool hints)
    2. Built-in PII field patterns

    Args:
        args: Tool call arguments.
        hints: Per-tool PII field name hints from ToolMeta.

    Returns:
        Sensitivity level: "public" | "internal" | "confidential" | "pii"
    """
    if not args:
        return "internal"

    hint_set = set(hints or [])
    check_set = hint_set | _BUILTIN_PII_PATTERNS

    for key in args:
        normalized = key.lower().strip()
        if normalized in check_set:
            return "pii"

    return "internal"


# ── Terminal command classifier ──────────────────

_CMD_CATEGORIES: list[tuple[str, list[str]]] = [
    ("destructive", ["rm ", "rm\t", "rmdir", "chmod", "chown", "sudo ", "kill ", "mkfs", "dd "]),
    ("install", ["pip install", "pip3 install", "npm install", "yarn add", "apt install", "apt-get install"]),
    ("network", ["curl ", "wget ", "ssh ", "scp ", "rsync ", "nc ", "nmap"]),
    ("write_repo", ["git add", "git commit", "git push", "git merge", "git rebase", "git apply", "git reset"]),
    ("read_only", ["git status", "git diff", "git log", "git branch", "cat ", "ls ", "ls\t",
                    "head ", "tail ", "echo ", "pwd", "whoami", "env", "printenv", "wc ", "grep "]),
]


def classify_terminal_command(cmd: str) -> str:
    """Classify a terminal command into a risk category.

    Args:
        cmd: The command string (e.g., "git push origin main").

    Returns:
        Category: "read_only" | "write_repo" | "install" | "network" | "destructive" | "unknown"
    """
    if not cmd:
        return "unknown"

    cmd_lower = cmd.strip().lower()

    # Check in priority order (destructive first)
    for category, patterns in _CMD_CATEGORIES:
        for pattern in patterns:
            if cmd_lower.startswith(pattern) or f" {pattern}" in cmd_lower:
                return category

    return "unknown"


# ── PolicyContext builders ───────────────────────


class PolicyContextBuilder:
    """Builds PolicyContext consistently for all chokepoints.

    Usage:
        ctx = PolicyContextBuilder.for_tool_call(agent_ctx, tool_meta, args)
        ctx = PolicyContextBuilder.for_llm_call(agent_ctx, model_name)
    """

    @staticmethod
    def for_tool_call(
        ctx: "AgentContext",
        tool_meta: ToolMeta,
        args: dict[str, Any],
    ) -> PolicyContext:
        """Build PolicyContext for a tool call.

        Computes composite risk and sensitivity from both the task
        context and the tool metadata.

        Args:
            ctx: Agent context from the caller.
            tool_meta: Metadata of the tool being called.
            args: Arguments passed to the tool.

        Returns:
            Fully populated PolicyContext.
        """
        # Composite risk = max(task risk, tool risk)
        composite_risk = _max_risk(ctx.risk_level, tool_meta.risk_level.value)

        # Composite sensitivity = max(tool default, arg classification)
        arg_sensitivity = classify_args(args, tool_meta.arg_sensitivity_hints)
        composite_sensitivity = _max_sensitivity(
            tool_meta.data_sensitivity_default, arg_sensitivity
        )

        # Build metadata
        metadata: dict[str, Any] = {
            "task_id": ctx.task_id,
            "trace_id": ctx.trace_id,
            "span_id": ctx.span_id,
            "side_effect_level": tool_meta.side_effect_level,
        }

        # Terminal command classification
        if "terminal" in tool_meta.name.lower():
            cmd = args.get("command", args.get("cmd", ""))
            if cmd:
                metadata["command_category"] = classify_terminal_command(cmd)

        return PolicyContext(
            agent_id=ctx.agent_id,
            department=ctx.department,
            role=ctx.role,
            tier=ctx.tier,
            action="tool_call",
            resource=f"tool:{tool_meta.name}",
            risk_level=composite_risk,
            data_sensitivity=composite_sensitivity,
            has_ticket_id=bool(ctx.ticket_id),
            approval_chain=list(ctx.approval_chain),
            metadata=metadata,
        )

    @staticmethod
    def for_llm_call(
        ctx: "AgentContext",
        model_name: str,
    ) -> PolicyContext:
        """Build PolicyContext for an LLM call.

        Args:
            ctx: Agent context from the caller.
            model_name: Name of the LLM model being called.

        Returns:
            Fully populated PolicyContext.
        """
        return PolicyContext(
            agent_id=ctx.agent_id,
            department=ctx.department,
            role=ctx.role,
            tier=ctx.tier,
            action="llm_call",
            resource=f"model:{model_name}",
            risk_level=ctx.risk_level,
            data_sensitivity=ctx.data_sensitivity,
            has_ticket_id=bool(ctx.ticket_id),
            approval_chain=list(ctx.approval_chain),
            metadata={
                "task_id": ctx.task_id,
                "trace_id": ctx.trace_id,
                "span_id": ctx.span_id,
            },
        )


# ── Obligations helper ───────────────────────────


def sanitize_args(args: dict[str, Any], mask_fields: list[str]) -> dict[str, Any]:
    """Sanitize arguments by masking sensitive fields.

    Creates a copy of args with matching field values replaced by "***MASKED***".
    Does NOT mutate the original dict.

    Args:
        args: Original arguments dict.
        mask_fields: List of field names to mask.

    Returns:
        Sanitized copy of args.
    """
    if not mask_fields:
        return dict(args)

    mask_set = {f.lower() for f in mask_fields}
    sanitized = {}
    for key, value in args.items():
        if key.lower() in mask_set:
            sanitized[key] = "***MASKED***"
        else:
            sanitized[key] = value
    return sanitized
