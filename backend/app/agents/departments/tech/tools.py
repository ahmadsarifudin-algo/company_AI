"""
Tech Department Tools — Registration of department-specific tools.

Tools registered here are available to Tech agents via ToolBroker.
All tool executions go through the chokepoint architecture.
"""

from app.core.tool_registry import ToolRegistry, ToolMeta, RiskLevel


def _git_clone_handler(args: dict) -> dict:
    """Clone a git repository into the sandbox workspace."""
    return {"status": "success", "repo": args.get("repo_url"), "path": args.get("target_path", ".")}


def _git_commit_handler(args: dict) -> dict:
    """Create a git commit with the specified message."""
    return {"status": "success", "message": args.get("message", ""), "files": args.get("files", [])}


def _git_create_pr_handler(args: dict) -> dict:
    """Create a pull request on the remote repository."""
    return {
        "status": "success",
        "pr_number": 0,
        "title": args.get("title", ""),
        "branch": args.get("branch", ""),
    }


def _run_tests_handler(args: dict) -> dict:
    """Execute test suite and return results."""
    return {
        "status": "success",
        "framework": args.get("framework", "pytest"),
        "command": args.get("command", "pytest"),
        "passed": 0,
        "failed": 0,
        "total": 0,
    }


def _lint_code_handler(args: dict) -> dict:
    """Run code linting and return findings."""
    return {
        "status": "success",
        "linter": args.get("linter", "ruff"),
        "issues": [],
        "total_issues": 0,
    }


def _build_docker_handler(args: dict) -> dict:
    """Build a Docker image from Dockerfile."""
    return {
        "status": "success",
        "image": args.get("image_name", ""),
        "tag": args.get("tag", "latest"),
    }


def _scan_dependencies_handler(args: dict) -> dict:
    """Scan project dependencies for vulnerabilities."""
    return {
        "status": "success",
        "scanner": "safety",
        "vulnerabilities": [],
        "total": 0,
    }


def _read_document_handler(args: dict) -> dict:
    """Read a document from the artifact store."""
    return {
        "status": "success",
        "path": args.get("path", ""),
        "content": "",
    }


def _write_artifact_handler(args: dict) -> dict:
    """Write an artifact to the artifact store."""
    return {
        "status": "success",
        "path": args.get("path", ""),
        "size_bytes": len(args.get("content", "")),
    }


def _query_logs_handler(args: dict) -> dict:
    """Query application logs for analysis."""
    return {
        "status": "success",
        "query": args.get("query", ""),
        "results": [],
        "total": 0,
    }


def register_tech_tools() -> None:
    """Register all Tech Department tools in the global ToolRegistry."""
    registry = ToolRegistry()

    tech_tools = [
        ToolMeta(
            name="git_clone",
            description="Clone a git repository into sandbox workspace",
            handler=_git_clone_handler,
            risk_level=RiskLevel.LOW,
            allowed_roles=["backend_engineer", "frontend_engineer", "devops", "data_engineer"],
            allowed_departments=["development"],
            egress_domains=["github.com", "gitlab.com"],
        ),
        ToolMeta(
            name="git_commit",
            description="Create a git commit with staged changes",
            handler=_git_commit_handler,
            risk_level=RiskLevel.MEDIUM,
            allowed_roles=["backend_engineer", "frontend_engineer", "devops", "data_engineer"],
            allowed_departments=["development"],
            egress_domains=[],
        ),
        ToolMeta(
            name="git_create_pr",
            description="Create a pull request on the remote repository",
            handler=_git_create_pr_handler,
            risk_level=RiskLevel.MEDIUM,
            allowed_roles=["backend_engineer", "frontend_engineer", "devops"],
            allowed_departments=["development"],
            egress_domains=["api.github.com"],
        ),
        ToolMeta(
            name="run_tests",
            description="Execute test suite (pytest / jest / vitest)",
            handler=_run_tests_handler,
            risk_level=RiskLevel.LOW,
            allowed_roles=["backend_engineer", "frontend_engineer", "qa"],
            allowed_departments=["development"],
            egress_domains=[],
        ),
        ToolMeta(
            name="lint_code",
            description="Run code linting (ruff / eslint)",
            handler=_lint_code_handler,
            risk_level=RiskLevel.LOW,
            allowed_roles=["backend_engineer", "frontend_engineer", "qa"],
            allowed_departments=["development"],
            egress_domains=[],
        ),
        ToolMeta(
            name="build_docker",
            description="Build Docker image from Dockerfile",
            handler=_build_docker_handler,
            risk_level=RiskLevel.HIGH,
            allowed_roles=["devops", "sre"],
            allowed_departments=["development"],
            egress_domains=["registry.hub.docker.com"],
        ),
        ToolMeta(
            name="scan_dependencies",
            description="Scan project dependencies for CVEs",
            handler=_scan_dependencies_handler,
            risk_level=RiskLevel.LOW,
            allowed_roles=["security", "backend_engineer", "devops"],
            allowed_departments=["development"],
            egress_domains=["pypi.org", "registry.npmjs.org"],
        ),
        ToolMeta(
            name="read_document",
            description="Read a document from the artifact store",
            handler=_read_document_handler,
            risk_level=RiskLevel.LOW,
            allowed_roles=["product_analyst", "architect", "qa", "technical_writer",
                           "backend_engineer", "frontend_engineer", "sre", "security",
                           "data_engineer", "devops"],
            allowed_departments=["development"],
            egress_domains=[],
        ),
        ToolMeta(
            name="write_artifact",
            description="Write an artifact (PRD, HLD, test plan, etc.) to store",
            handler=_write_artifact_handler,
            risk_level=RiskLevel.MEDIUM,
            allowed_roles=["product_analyst", "architect", "qa", "technical_writer",
                           "backend_engineer", "frontend_engineer", "sre", "devops",
                           "data_engineer"],
            allowed_departments=["development"],
            egress_domains=[],
        ),
        ToolMeta(
            name="query_logs",
            description="Query application and system logs",
            handler=_query_logs_handler,
            risk_level=RiskLevel.LOW,
            allowed_roles=["sre", "backend_engineer", "qa", "devops", "security"],
            allowed_departments=["development"],
            egress_domains=[],
        ),
    ]

    for tool in tech_tools:
        registry.register(tool)
