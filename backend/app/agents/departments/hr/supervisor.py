"""HRSupervisor — Routes HR tasks to specialist agents."""

import json
import structlog
from app.agents.base_agent import BaseAgent
from app.agents.state import AgentState

logger = structlog.get_logger()

HR_SPECIALISTS = {
    "Recruitment": "CV screening, candidate ranking, interview scheduling",
    "Onboarding": "New hire checklist, contract drafts, orientation",
    "Payroll": "Payroll validation, anomaly detection, salary benchmarking",
    "Performance": "KPI aggregation, performance reviews, talent mapping",
    "Compliance": "Labor law compliance, work permit tracking, policy audit",
    "Training": "Skill gap analysis, learning path design, certification tracking",
    "Benefits": "Benefits eligibility, enrollment management, cost analysis",
}


class HRSupervisor(BaseAgent):
    """HR Department Supervisor — routes tasks to HR specialists."""

    def get_system_prompt(self) -> str:
        agent_list = "\n".join(f"  - {k}: {v}" for k, v in HR_SPECIALISTS.items())
        return (
            "You are the HR Department Supervisor.\n\n"
            "Route HR requests to appropriate specialists. Ensure PII handling "
            "compliance for all employee data.\n\n"
            f"Available specialists:\n{agent_list}\n\n"
            "Output valid JSON plan with tasks and assignments."
        )

    async def process(self, state: AgentState) -> AgentState:
        ctx = self.get_context(task_id=state.get("task_id", ""), trace_id=state.get("trace_id", ""))
        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": state.get("task_description", "")},
        ]
        response = await self.call_llm(messages, temperature=0.3, ctx=ctx)
        try:
            plan = json.loads(response.content)
        except json.JSONDecodeError:
            plan = {"raw_response": response.content, "tasks": []}
        artifacts = dict(state.get("artifacts", {}))
        artifacts["hr_plan"] = plan
        return {**state, "artifacts": artifacts, "status": "planned",
                "current_agent": self.name,
                "token_usage": state.get("token_usage", 0) + response.total_tokens}
