"""ForecastingAgent — Cashflow projection and revenue modeling."""

import json
import structlog
from app.agents.base_agent import BaseAgent
from app.agents.state import AgentState

logger = structlog.get_logger()


class ForecastingAgent(BaseAgent):
    """Projects cashflow, models revenue scenarios, and predicts financial trends."""

    def get_system_prompt(self) -> str:
        return (
            "You are a Forecasting Agent in the Finance Department.\n\n"
            "Responsibilities:\n"
            "1. Project cashflow for 3/6/12 month horizons\n"
            "2. Model revenue scenarios (best/base/worst case)\n"
            "3. Analyze financial trends and seasonality\n"
            "4. Predict working capital needs\n"
            "5. Generate financial forecast reports\n\n"
            "Output JSON: {\"cashflow_projection\": {\"period\": \"\", \"monthly\": [], "
            "\"net_position\": 0}, \"revenue_forecast\": {\"scenarios\": "
            "[{\"name\": \"base\", \"revenue\": 0, \"probability\": 0.5}]}, "
            "\"recommendations\": []}"
        )

    async def process(self, state: AgentState) -> AgentState:
        ctx = self.get_context(task_id=state.get("task_id", ""), trace_id=state.get("trace_id", ""))
        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": state.get("task_description", "")},
        ]
        response = await self.call_llm(messages, temperature=0.4, ctx=ctx)
        try:
            result = json.loads(response.content)
        except json.JSONDecodeError:
            result = {"raw_response": response.content}
        artifacts = dict(state.get("artifacts", {}))
        artifacts["financial_forecast"] = result
        return {**state, "artifacts": artifacts, "status": "forecasting_complete",
                "current_agent": self.name,
                "token_usage": state.get("token_usage", 0) + response.total_tokens}
