"""BudgetPlanningAgent — Budget proposals and variance analysis."""

import json
import structlog
from app.agents.base_agent import BaseAgent
from app.agents.state import AgentState

logger = structlog.get_logger()


class BudgetPlanningAgent(BaseAgent):
    """Creates budget proposals, performs variance analysis, tracks spending."""

    def get_system_prompt(self) -> str:
        return (
            "You are a Budget Planning Agent in the Finance Department.\n\n"
            "Responsibilities:\n"
            "1. Create departmental budget proposals\n"
            "2. Perform budget vs actual variance analysis\n"
            "3. Identify cost-saving opportunities\n"
            "4. Project future spending based on trends\n"
            "5. Flag budget overruns requiring management action\n\n"
            "Output JSON: {\"budget_proposal\": {\"department\": \"\", \"period\": \"\", "
            "\"line_items\": [], \"total\": 0}, \"variance_analysis\": {\"items\": [], "
            "\"total_variance\": 0, \"status\": \"on_track|over_budget|under_budget\"}}"
        )

    async def process(self, state: AgentState) -> AgentState:
        ctx = self.get_context(task_id=state.get("task_id", ""), trace_id=state.get("trace_id", ""))
        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": state.get("task_description", "")},
        ]
        response = await self.call_llm(messages, temperature=0.3, ctx=ctx)
        try:
            result = json.loads(response.content)
        except json.JSONDecodeError:
            result = {"raw_response": response.content}
        artifacts = dict(state.get("artifacts", {}))
        artifacts["budget_plan"] = result
        return {**state, "artifacts": artifacts, "status": "budget_planning_complete",
                "current_agent": self.name,
                "token_usage": state.get("token_usage", 0) + response.total_tokens}
