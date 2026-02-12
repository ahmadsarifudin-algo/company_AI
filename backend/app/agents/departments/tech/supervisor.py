"""
TechSupervisor — Department-level orchestrator for Tech Development.

Responsibilities:
- Decompose high-level requests into Plan JSON tasks
- Assign tasks to appropriate specialist agents
- Manage dependencies between tasks
- Monitor progress and handle retries
- Aggregate results into final deliverables

Does NOT execute tools directly — delegates everything to specialists.
"""

import json
from typing import Any

import structlog

from app.agents.base_agent import BaseAgent
from app.agents.state import AgentState
from app.core.llm_client import AgentContext

logger = structlog.get_logger()

PLAN_SCHEMA = """\
Output a valid JSON plan with this structure:
{
  "goal": "Feature objective",
  "project_id": "string",
  "constraints": {
    "deadline": "ISO date or null",
    "environment": "dev|staging|prod",
    "budget_limit_usd": number
  },
  "tasks": [
    {
      "id": "T1",
      "owner_agent": "AgentName",
      "depends_on": [],
      "input": "description or artifact reference",
      "tools_allowed": [],
      "output_artifact": "artifact name",
      "definition_of_done": "measurable criteria"
    }
  ],
  "risk": ["identified risks"],
  "approval_required": ["steps needing human approval"]
}
"""

AVAILABLE_AGENTS = {
    "ProductAnalyst": "PRD generation, acceptance criteria, KPI definition",
    "Architect": "HLD/LLD design, API contracts, threat model",
    "BackendEngineer": "Server-side code generation, unit tests, PRs",
    "FrontendEngineer": "UI implementation, component tests, PRs",
    "QA": "Test plan generation, acceptance validation, release blocking",
    "DevOps": "CI/CD configuration, deployment preparation, rollback plans",
    "SRE": "Monitoring rules, incident response, postmortem drafting",
    "Security": "CVE scanning, dependency audit, secret detection",
    "DataEngineer": "ETL pipeline design, data quality validation",
    "TechnicalWriter": "API documentation, changelogs, ADRs",
}


class TechSupervisor(BaseAgent):
    """Tech Department Supervisor — orchestrates specialist agents.

    Takes a high-level request and produces a structured Plan JSON
    that assigns tasks to the appropriate specialist agents.
    """

    def get_system_prompt(self) -> str:
        agent_list = "\n".join(
            f"  - {name}: {desc}" for name, desc in AVAILABLE_AGENTS.items()
        )
        return (
            "You are the Tech Department Supervisor for an enterprise AI system.\n\n"
            "Your role:\n"
            "1. Break down requests into concrete, actionable tasks\n"
            "2. Assign each task to the most appropriate specialist agent\n"
            "3. Define clear dependencies between tasks\n"
            "4. Identify risks and approval requirements\n"
            "5. Set measurable definition-of-done for each task\n\n"
            "You do NOT execute any tools yourself. You only produce plans.\n\n"
            f"Available specialist agents:\n{agent_list}\n\n"
            f"Output format:\n{PLAN_SCHEMA}\n"
            "Respond ONLY with valid JSON. No markdown, no explanation."
        )

    async def process(self, state: AgentState) -> AgentState:
        """Decompose request into Plan JSON and return updated state."""
        ctx = self.get_context(
            task_id=state.get("task_id", ""),
            trace_id=state.get("trace_id", ""),
        )

        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": state.get("task_description", "")},
        ]

        self.log.info(
            "supervisor_planning",
            trace_id=ctx.trace_id,
            task=state.get("task_description", "")[:100],
        )

        response = await self.call_llm(messages, temperature=0.3, ctx=ctx)

        # Parse Plan JSON
        try:
            plan = json.loads(response.content)
            task_count = len(plan.get("tasks", []))
        except json.JSONDecodeError:
            plan = {"raw_response": response.content, "tasks": []}
            task_count = 0

        self.log.info(
            "supervisor_plan_complete",
            trace_id=ctx.trace_id,
            task_count=task_count,
            cost_usd=response.cost_usd,
        )

        # Update state with plan
        messages_out = list(state.get("messages", []))
        messages_out.append(
            {"role": "assistant", "content": json.dumps(plan, indent=2)}
        )

        artifacts = dict(state.get("artifacts", {}))
        artifacts["plan_json"] = plan

        return {
            **state,
            "messages": messages_out,
            "artifacts": artifacts,
            "status": "planned",
            "current_agent": self.name,
            "token_usage": state.get("token_usage", 0) + response.total_tokens,
        }
