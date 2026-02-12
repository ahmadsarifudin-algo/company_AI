"""
TaskSandbox — Per-task file system isolation.
NetworkPolicy — Domain-level egress control for tools.

These enforce that:
- Tools can only read/write files within their task workspace
- Tools can only make HTTP calls to pre-approved domains
"""

import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import structlog

logger = structlog.get_logger()


class EgressDenied(Exception):
    """Raised when a tool tries to access a blocked domain."""

    def __init__(self, tool_name: str, url: str, allowed_domains: list[str]):
        self.tool_name = tool_name
        self.url = url
        self.allowed_domains = allowed_domains
        super().__init__(
            f"Egress denied: tool '{tool_name}' tried to access '{url}'. "
            f"Allowed domains: {allowed_domains}"
        )


class PathEscapeAttempt(Exception):
    """Raised when a tool tries to access files outside its workspace."""

    def __init__(self, task_id: str, attempted_path: str, workspace: str):
        self.task_id = task_id
        self.attempted_path = attempted_path
        self.workspace = workspace
        super().__init__(
            f"Path escape attempt: task '{task_id}' tried to access "
            f"'{attempted_path}' outside workspace '{workspace}'"
        )


class TaskSandbox:
    """Per-task isolated file system workspace.

    Each task gets a dedicated directory under /tmp/company_ai_tasks/{task_id}/.
    Tools can only read/write within this workspace. The workspace is
    automatically cleaned up after task completion.
    """

    BASE_DIR = Path(tempfile.gettempdir()) / "company_ai_tasks"

    @classmethod
    def create_workspace(cls, task_id: str) -> Path:
        """Create an isolated workspace for a task.

        Args:
            task_id: Unique task identifier.

        Returns:
            Path to the created workspace directory.
        """
        workspace = cls.BASE_DIR / task_id
        workspace.mkdir(parents=True, exist_ok=True)

        logger.info("sandbox_workspace_created", task_id=task_id, path=str(workspace))
        return workspace

    @classmethod
    def get_workspace(cls, task_id: str) -> Path:
        """Get the workspace path for a task (creates if not exists)."""
        workspace = cls.BASE_DIR / task_id
        if not workspace.exists():
            return cls.create_workspace(task_id)
        return workspace

    @classmethod
    def validate_path(cls, task_id: str, path: str | Path) -> Path:
        """Validate that a path is within the task's workspace.

        Args:
            task_id: Task identifier.
            path: Path to validate.

        Returns:
            Resolved absolute path within the workspace.

        Raises:
            PathEscapeAttempt: If path resolves outside workspace.
        """
        workspace = cls.get_workspace(task_id)
        resolved = (workspace / Path(path)).resolve()

        if not str(resolved).startswith(str(workspace.resolve())):
            raise PathEscapeAttempt(task_id, str(path), str(workspace))

        return resolved

    @classmethod
    def cleanup(cls, task_id: str) -> None:
        """Remove workspace and all its contents.

        Args:
            task_id: Task identifier.
        """
        workspace = cls.BASE_DIR / task_id
        if workspace.exists():
            shutil.rmtree(workspace, ignore_errors=True)
            logger.info("sandbox_workspace_cleaned", task_id=task_id)

    @classmethod
    def list_artifacts(cls, task_id: str) -> list[str]:
        """List all files in a task's workspace.

        Returns:
            List of relative file paths.
        """
        workspace = cls.get_workspace(task_id)
        if not workspace.exists():
            return []
        return [
            str(p.relative_to(workspace))
            for p in workspace.rglob("*")
            if p.is_file()
        ]


class NetworkPolicy:
    """Domain-level egress control.

    Default policy: BLOCK ALL outbound connections.
    Each tool must declare its allowed egress domains in ToolMeta.
    NetworkPolicy checks against this allowlist before any HTTP call.
    """

    @staticmethod
    def check_egress(tool_name: str, url: str, allowed_domains: list[str]) -> None:
        """Check if a URL is in the tool's allowed egress domains.

        Args:
            tool_name: Name of the tool making the request.
            url: Target URL.
            allowed_domains: List of allowed domain names.

        Raises:
            EgressDenied: If the domain is not in the allowlist.
        """
        if not allowed_domains:
            raise EgressDenied(tool_name, url, [])

        parsed = urlparse(url)
        hostname = parsed.hostname or ""

        # Check exact match or subdomain match
        allowed = False
        for domain in allowed_domains:
            if hostname == domain or hostname.endswith(f".{domain}"):
                allowed = True
                break

        if not allowed:
            logger.warning(
                "egress_denied",
                tool=tool_name,
                url=url,
                hostname=hostname,
                allowed=allowed_domains,
            )
            raise EgressDenied(tool_name, url, allowed_domains)

        logger.debug(
            "egress_allowed",
            tool=tool_name,
            hostname=hostname,
        )
