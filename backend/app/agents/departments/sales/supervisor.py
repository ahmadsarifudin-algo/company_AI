"""SalesSupervisor — Routes sales/marketing tasks to specialists."""

import json, structlog
from app.agents.base_agent import BaseAgent
from app.agents.state import AgentState
logger = structlog.get_logger()

SALES_SPECIALISTS = {
    "LeadScoring": "Lead qualification, scoring, prioritization",
    "DealIntelligence": "Competitive analysis, win/loss analysis, market insights",
    "SalesForecasting": "Pipeline forecasting, revenue projection, quota tracking",
    "Pricing": "Dynamic pricing, discount approval, margin analysis",
    "ContractReview": "Contract terms review, risk clauses, renewal management",
}

class SalesSupervisor(BaseAgent):
    """Sales Department Supervisor — routes tasks to sales specialists."""

    def get_system_prompt(self) -> str:
        agent_list = "\n".join(f"  - {k}: {v}" for k, v in SALES_SPECIALISTS.items())
        return (
            "You are the Sales & Marketing Department Supervisor.\n\n"
            "Route sales requests to appropriate specialists. "
            "Prioritize pipeline velocity and deal closure.\n\n"
            f"Available specialists:\n{agent_list}\n\n"
            "Output valid JSON plan with tasks and assignments."
        )

    async def process(self, state: AgentState) -> AgentState:
        ctx = self.get_context(task_id=state.get("task_id", ""), trace_id=state.get("trace_id", ""))
        messages = [{"role": "system", "content": self.get_system_prompt()},
                    {"role": "user", "content": state.get("task_description", "")}]
        response = await self.call_llm(messages, temperature=0.3, ctx=ctx)
        try: plan = json.loads(response.content)
        except json.JSONDecodeError: plan = {"raw_response": response.content, "tasks": []}
        artifacts = dict(state.get("artifacts", {}))
        artifacts["sales_plan"] = plan
        return {**state, "artifacts": artifacts, "status": "planned",
                "current_agent": self.name,
                "token_usage": state.get("token_usage", 0) + response.total_tokens}
