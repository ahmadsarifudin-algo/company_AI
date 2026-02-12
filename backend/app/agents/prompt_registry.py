"""
Agent prompt registry — extracts _default_system_prompt() from all agent classes.

Provides a mapping of agent_name → default_system_prompt, auto-discovered from
the department agent modules. Used by the test endpoint and the sync-prompts
admin endpoint to ensure consistent prompt usage.
"""

import importlib
import inspect
import logging
from dataclasses import dataclass
from typing import Dict, List

logger = logging.getLogger(__name__)

# Module paths for all department agent files
_AGENT_MODULES = [
    # Finance
    "app.agents.departments.finance.accounting",
    "app.agents.departments.finance.audit",
    "app.agents.departments.finance.budget_planning",
    "app.agents.departments.finance.forecasting",
    "app.agents.departments.finance.invoicing",
    "app.agents.departments.finance.risk_compliance",
    "app.agents.departments.finance.supervisor",
    "app.agents.departments.finance.tax",
    "app.agents.departments.finance.treasury",
    # HR
    "app.agents.departments.hr.benefits",
    "app.agents.departments.hr.compliance",
    "app.agents.departments.hr.onboarding",
    "app.agents.departments.hr.payroll",
    "app.agents.departments.hr.performance",
    "app.agents.departments.hr.recruitment",
    "app.agents.departments.hr.supervisor",
    "app.agents.departments.hr.training",
    # Sales
    "app.agents.departments.sales.contract_review",
    "app.agents.departments.sales.deal_intelligence",
    "app.agents.departments.sales.lead_scoring",
    "app.agents.departments.sales.pricing",
    "app.agents.departments.sales.sales_forecasting",
    "app.agents.departments.sales.supervisor",
    # Tech
    "app.agents.departments.tech.architect",
    "app.agents.departments.tech.backend_engineer",
    "app.agents.departments.tech.data_engineer",
    "app.agents.departments.tech.devops",
    "app.agents.departments.tech.frontend_engineer",
    "app.agents.departments.tech.product_analyst",
    "app.agents.departments.tech.qa",
    "app.agents.departments.tech.security",
    "app.agents.departments.tech.sre",
    "app.agents.departments.tech.supervisor",
    "app.agents.departments.tech.technical_writer",
]


# Tier mapping by role
_ROLE_TIER_MAP = {
    "supervisor": "tier_3",
    "agent": "standard",
}


@dataclass
class AgentInfo:
    """Metadata about an agent class."""
    name: str
    department: str
    role: str
    tier: str
    system_prompt: str
    class_name: str
    module_path: str


def get_all_agent_info() -> List[AgentInfo]:
    """Auto-discover all agent classes and extract their metadata.

    Returns a list of AgentInfo with name, department, role, tier, and prompt.
    """
    agents: List[AgentInfo] = []

    for module_path in _AGENT_MODULES:
        try:
            mod = importlib.import_module(module_path)
        except Exception as e:
            logger.warning("Failed to import %s: %s", module_path, e)
            continue

        # Find classes with _default_system_prompt method
        for cls_name, cls in inspect.getmembers(mod, inspect.isclass):
            if not hasattr(cls, "_default_system_prompt"):
                continue
            # Skip base classes imported from other modules
            if cls.__module__ != mod.__name__:
                continue
            try:
                instance = cls.__new__(cls)
                prompt = cls._default_system_prompt(instance)
                name = getattr(cls, "name", cls_name)
                department = getattr(cls, "department", "unknown")
                role = getattr(cls, "role", "agent")
                tier = _ROLE_TIER_MAP.get(role, "standard")

                agents.append(AgentInfo(
                    name=name,
                    department=department,
                    role=role,
                    tier=tier,
                    system_prompt=prompt,
                    class_name=cls_name,
                    module_path=module_path,
                ))
                logger.debug("Extracted agent: %s (%s/%s)", name, department, role)
            except Exception as e:
                logger.warning("Failed to extract from %s: %s", cls_name, e)

    return agents


def get_all_default_prompts() -> Dict[str, str]:
    """Return dict mapping agent name → default system prompt."""
    return {a.name.lower(): a.system_prompt for a in get_all_agent_info()}


# Cache the prompts on first call
_cached_prompts: Dict[str, str] | None = None


def get_prompt_for_agent(agent_name: str) -> str | None:
    """Get the default system prompt for a given agent name.

    Matches case-insensitively. Returns None if no matching agent found.
    """
    global _cached_prompts
    if _cached_prompts is None:
        _cached_prompts = get_all_default_prompts()

    key = agent_name.lower().strip()
    # Try exact match first
    if key in _cached_prompts:
        return _cached_prompts[key]
    # Try partial match (e.g. "Accounting Agent" → "accounting_agent")
    key_nospace = key.replace(" ", "").replace("_", "").replace("-", "")
    for k, v in _cached_prompts.items():
        if k.replace(" ", "").replace("_", "").replace("-", "") == key_nospace:
            return v
    return None
