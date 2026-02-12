"""
ToolRegistry — Static tool registration and allowlist.

All tools MUST be registered at application startup via ToolRegistry.register().
Agents are FORBIDDEN from declaring their own tools.
ToolBroker uses this registry to resolve and validate every tool call.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine

import structlog

logger = structlog.get_logger()


class RiskLevel(str, Enum):
    """Risk classification for tools and actions."""

    LOW = "low"  # auto-approve
    MEDIUM = "medium"  # notify human
    HIGH = "high"  # require 1 approval
    CRITICAL = "critical"  # require 2 approvals


class ToolNotFound(Exception):
    """Raised when a tool is not registered."""

    def __init__(self, tool_name: str):
        self.tool_name = tool_name
        super().__init__(f"Tool not found in registry: '{tool_name}'. All tools must be pre-registered.")


class ToolAccessDenied(Exception):
    """Raised when agent role/dept is not allowed to use a tool."""

    def __init__(self, tool_name: str, agent_role: str, department: str):
        self.tool_name = tool_name
        self.agent_role = agent_role
        self.department = department
        super().__init__(
            f"Access denied: role='{agent_role}' dept='{department}' "
            f"cannot use tool '{tool_name}'"
        )


# Type alias for async tool handler functions
ToolHandler = Callable[..., Coroutine[Any, Any, Any]]


@dataclass
class ToolMeta:
    """Metadata for a registered tool."""

    name: str
    handler: ToolHandler
    description: str = ""
    allowed_roles: set[str] = field(default_factory=lambda: {"agent"})
    allowed_departments: set[str] = field(default_factory=lambda: {"*"})  # "*" = all
    risk_level: RiskLevel = RiskLevel.LOW
    has_egress: bool = False
    egress_domains: list[str] = field(default_factory=list)
    has_file_access: bool = False
    idempotent: bool = False
    cost_estimate_usd: float = 0.0
    # ── ABAC enrichment ──
    data_sensitivity_default: str = "internal"  # public | internal | confidential | pii
    side_effect_level: str = "none"  # none | low | high
    arg_sensitivity_hints: list[str] = field(default_factory=list)  # PII field names
    parameters: dict = field(default_factory=dict)  # OpenAI function calling parameter schema

    def is_allowed_for(self, role: str, department: str) -> bool:
        """Check if a role+department combination is allowed."""
        role_ok = role in self.allowed_roles or "*" in self.allowed_roles
        dept_ok = department in self.allowed_departments or "*" in self.allowed_departments
        return role_ok and dept_ok


class ToolRegistry:
    """Central registry for all tools in the system.

    Tools are registered statically at startup. No dynamic tool declaration
    by agents is allowed. The ToolBroker queries this registry to:
    1. Resolve tool handlers
    2. Check role/department access
    3. Get risk level for policy evaluation
    4. Get egress domains for network policy
    """

    _tools: dict[str, ToolMeta] = {}
    _frozen: bool = False

    @classmethod
    def register(cls, meta: ToolMeta) -> None:
        """Register a tool. Must be called during application startup.

        Args:
            meta: Tool metadata including handler, permissions, risk level.

        Raises:
            RuntimeError: If registry is frozen (app already started).
            ValueError: If tool with same name already registered.
        """
        if cls._frozen:
            raise RuntimeError(
                f"Cannot register tool '{meta.name}' — registry is frozen. "
                "All tools must be registered before application startup."
            )
        if meta.name in cls._tools:
            raise ValueError(f"Tool '{meta.name}' is already registered.")

        cls._tools[meta.name] = meta
        logger.info(
            "tool_registered",
            name=meta.name,
            risk=meta.risk_level.value,
            egress=meta.has_egress,
            roles=list(meta.allowed_roles),
        )

    @classmethod
    def freeze(cls) -> None:
        """Freeze the registry. No more tools can be registered after this."""
        cls._frozen = True
        logger.info("tool_registry_frozen", tool_count=len(cls._tools))

    @classmethod
    def resolve(cls, name: str) -> ToolMeta:
        """Resolve a tool by name.

        Args:
            name: Tool name.

        Returns:
            ToolMeta for the tool.

        Raises:
            ToolNotFound: If tool is not registered.
        """
        if name not in cls._tools:
            raise ToolNotFound(name)
        return cls._tools[name]

    @classmethod
    def get_tools_for(cls, role: str, department: str) -> list[ToolMeta]:
        """Get all tools available to a given role and department.

        Args:
            role: Agent role (e.g. "agent", "supervisor", "admin").
            department: Department name.

        Returns:
            List of ToolMeta for allowed tools.
        """
        return [
            tool for tool in cls._tools.values()
            if tool.is_allowed_for(role, department)
        ]

    @classmethod
    def get_tool_names_for(cls, role: str, department: str) -> list[str]:
        """Get tool names available to a role+department."""
        return [t.name for t in cls.get_tools_for(role, department)]

    @classmethod
    def list_all(cls) -> list[ToolMeta]:
        """List all registered tools."""
        return list(cls._tools.values())

    @classmethod
    def clear(cls) -> None:
        """Clear all registered tools. Only for testing."""
        cls._tools.clear()
        cls._frozen = False

    @classmethod
    def is_registered(cls, name: str) -> bool:
        """Check if a tool is registered."""
        return name in cls._tools

    @classmethod
    def register_shared_tool(
        cls,
        name: str,
        handler: ToolHandler,
        description: str = "",
        risk_level: RiskLevel = RiskLevel.LOW,
        departments: list[str] | None = None,
        roles: list[str] | None = None,
        has_egress: bool = False,
        egress_domains: list[str] | None = None,
        has_file_access: bool = False,
        parameters: dict | None = None,
        **kwargs,
    ) -> None:
        """Register a shared tool (convenience wrapper for register).

        Accepts keyword args matching the shared_tools.py format and
        constructs a ToolMeta automatically.

        Args:
            name: Tool name.
            handler: Async handler function.
            description: Tool description.
            risk_level: Risk classification.
            departments: Allowed departments ("*" = all).
            roles: Allowed roles ("*" = all).
            has_egress: Whether tool makes external API calls.
            egress_domains: Allowed external domains.
            has_file_access: Whether tool reads/writes files.
            parameters: OpenAI function calling parameter schema.
        """
        if cls.is_registered(name):
            return  # Already registered

        meta = ToolMeta(
            name=name,
            handler=handler,
            description=description,
            risk_level=risk_level,
            allowed_roles=set(roles or ["*"]),
            allowed_departments=set(departments or ["*"]),
            has_egress=has_egress,
            egress_domains=egress_domains or [],
            has_file_access=has_file_access,
            parameters=parameters or {},
        )
        cls.register(meta)


# ── Workflow Tool Handlers (Reference Implementation) ─


async def _save_invoice_handler(
    invoice_data: dict,
    department: str = "",
    trace_id: str = "",
) -> dict:
    """Save an invoice record. In production this writes to DB via DAL."""
    logger.info(
        "tool_save_invoice",
        trace_id=trace_id,
        department=department,
        invoice_id=invoice_data.get("invoice_id", "unknown"),
    )
    return {"saved": True, "invoice_id": invoice_data.get("invoice_id", "unknown")}


async def _generate_invoice_pdf_handler(
    invoice_data: dict,
    output_path: str = "",
    trace_id: str = "",
) -> dict:
    """Generate a PDF artifact for an invoice. Stub for reference."""
    logger.info(
        "tool_generate_pdf",
        trace_id=trace_id,
        output_path=output_path,
    )
    return {"generated": True, "path": output_path or f"/artifacts/{trace_id}/invoice.pdf"}


def register_workflow_tools() -> None:
    """Register all workflow tools in the ToolRegistry.

    Called during application startup, before ToolRegistry.freeze().
    """
    if ToolRegistry.is_registered("save_invoice"):
        return  # Already registered (e.g. in tests)

    ToolRegistry.register(ToolMeta(
        name="save_invoice",
        handler=_save_invoice_handler,
        description="Persist a finalized invoice to the database",
        allowed_roles={"agent", "finance_agent", "supervisor"},
        allowed_departments={"finance", "accounting", "*"},
        risk_level=RiskLevel.MEDIUM,
        has_egress=False,
        has_file_access=False,
        idempotent=True,
        cost_estimate_usd=0.0,
    ))

    ToolRegistry.register(ToolMeta(
        name="generate_invoice_pdf",
        handler=_generate_invoice_pdf_handler,
        description="Generate a PDF artifact for an invoice",
        allowed_roles={"agent", "finance_agent", "supervisor"},
        allowed_departments={"finance", "accounting", "*"},
        risk_level=RiskLevel.LOW,
        has_egress=False,
        has_file_access=True,
        idempotent=True,
        cost_estimate_usd=0.0,
    ))

    logger.info("workflow_tools_registered", tools=["save_invoice", "generate_invoice_pdf"])

