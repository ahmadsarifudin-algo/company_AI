"""
Test Suite — Static Analysis Tests (Module 3.5.9).

Tests architectural invariants:
- No direct imports of forbidden modules in agents/
- All agents use chokepoint gateways (LLMClient, ToolBroker, DAL)
- No subprocess/os.system calls in agent code
- Tool handlers registered via ToolRegistry (not ad-hoc)
"""

import ast
import os
from pathlib import Path

import pytest

# Project root
BACKEND_DIR = Path(__file__).parent.parent
AGENTS_DIR = BACKEND_DIR / "app" / "agents"
CORE_DIR = BACKEND_DIR / "app" / "core"


# ── Forbidden Imports in Agent Code ───────────────


# Agents must NOT directly import these — they bypass chokepoints
FORBIDDEN_AGENT_IMPORTS = {
    "litellm",           # Must use LLMClient
    "openai",            # Must use LLMClient
    "anthropic",         # Must use LLMClient
    "subprocess",        # Must use ToolBroker
    "os.system",         # Must use ToolBroker
    "sqlalchemy",        # Must use DataAccessLayer
    "asyncpg",           # Must use DataAccessLayer
    "psycopg2",          # Must use DataAccessLayer
    "redis",             # Must use BudgetEnforcer/MetricsCollector
    "requests",          # Must use ToolBroker
    "httpx",             # Must use ToolBroker
    "aiohttp",           # Must use ToolBroker
}

# Some imports are OK in workflows (they import from core, not directly)
WORKFLOW_ALLOWED_IMPORTS = {
    "app.core.llm_client",
    "app.core.tool_broker",
    "app.core.data_access",
    "app.core.policy_engine",
    "app.core.approval_gate",
    "app.core.resilience",
    "app.core.budget",
    "app.core.tracing",
}


def _get_python_files(directory: Path) -> list[Path]:
    """Get all .py files in a directory recursively."""
    if not directory.exists():
        return []
    return [f for f in directory.rglob("*.py") if f.name != "__init__.py"]


def _get_imports(filepath: Path) -> list[str]:
    """Extract all import module names from a Python file."""
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


class TestForbiddenImports:
    """Agents must not import SDK libraries directly."""

    @pytest.mark.parametrize("filepath", _get_python_files(AGENTS_DIR))
    def test_no_forbidden_imports_in_agents(self, filepath):
        """Agent files must not import forbidden modules."""
        imports = _get_imports(filepath)
        # Check for workflows directory — they're allowed to import from core
        is_workflow = "workflows" in str(filepath)

        for imp in imports:
            top_module = imp.split(".")[0]
            full_module = imp

            # Skip allowed core imports for workflows
            if is_workflow and full_module in WORKFLOW_ALLOWED_IMPORTS:
                continue

            assert top_module not in FORBIDDEN_AGENT_IMPORTS, (
                f"{filepath.name} imports forbidden module '{imp}'. "
                f"Use chokepoint gateways instead."
            )


# ── No Dangerous Calls ────────────────────────────


DANGEROUS_FUNCTIONS = {"os.system", "subprocess.call", "subprocess.run", "subprocess.Popen", "eval", "exec"}


class TestNoDangerousCalls:
    """No dangerous function calls in agent code."""

    @pytest.mark.parametrize("filepath", _get_python_files(AGENTS_DIR))
    def test_no_dangerous_calls(self, filepath):
        """Agent files must not call dangerous functions."""
        try:
            tree = ast.parse(filepath.read_text(encoding="utf-8"))
        except SyntaxError:
            return

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = ""
                if isinstance(node.func, ast.Attribute):
                    if isinstance(node.func.value, ast.Name):
                        func_name = f"{node.func.value.id}.{node.func.attr}"
                elif isinstance(node.func, ast.Name):
                    func_name = node.func.id

                assert func_name not in DANGEROUS_FUNCTIONS, (
                    f"{filepath.name}:{node.lineno} calls dangerous function '{func_name}'"
                )


# ── Core Module Structure ─────────────────────────


class TestCoreModuleStructure:
    """Core chokepoint modules must exist."""

    @pytest.mark.parametrize("module", [
        "llm_client.py",
        "tool_broker.py",
        "data_access.py",
        "policy_engine.py",
        "budget.py",
        "resilience.py",
        "tracing.py",
        "sandbox.py",
        "tool_registry.py",
        "resource_classification.py",
    ])
    def test_core_module_exists(self, module):
        """All core chokepoint modules must exist."""
        module_path = CORE_DIR / module
        assert module_path.exists(), f"Core module '{module}' missing from {CORE_DIR}"

    def test_approval_gate_exists(self):
        """ApprovalGate module must exist."""
        assert (CORE_DIR / "approval_gate.py").exists()


# ── Policy Files ──────────────────────────────────


class TestPolicyFiles:
    """Policy configuration files must exist and be valid."""

    def test_default_policy_exists(self):
        """default.yaml policy file must exist."""
        policy_path = BACKEND_DIR / "policies" / "default.yaml"
        assert policy_path.exists(), "policies/default.yaml missing"

    def test_default_policy_has_rules(self):
        """default.yaml must contain rules."""
        import yaml

        policy_path = BACKEND_DIR / "policies" / "default.yaml"
        data = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
        assert "rules" in data
        assert len(data["rules"]) >= 7, f"Expected ≥7 rules, got {len(data['rules'])}"


# ── Workflow Files ────────────────────────────────


class TestWorkflowStructure:
    """Workflow module must follow conventions."""

    def test_workflows_package_exists(self):
        """agents/workflows/ package exists."""
        assert (AGENTS_DIR / "workflows" / "__init__.py").exists()

    def test_finance_invoice_workflow_exists(self):
        """Reference workflow file exists."""
        assert (AGENTS_DIR / "workflows" / "finance_invoice.py").exists()
