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
