"""SalesForecastingAgent — Pipeline forecasting and quota tracking."""

import json, structlog
from app.agents.base_agent import BaseAgent
from app.agents.state import AgentState
logger = structlog.get_logger()

class SalesForecastingAgent(BaseAgent):
    """Forecasts revenue, tracks quotas, and analyzes pipeline health."""

    def get_system_prompt(self) -> str:
        return (
            "You are a Sales Forecasting Agent in the Sales Department.\n\n"
            "Responsibilities:\n"
            "1. Forecast quarterly/annual revenue from pipeline\n"
            "2. Track individual and team quota attainment\n"
            "3. Analyze pipeline health (coverage, velocity, conversion)\n"
            "4. Identify pipeline risks and gaps\n"
            "5. Generate forecast reports with confidence levels\n\n"
            "Output JSON: {\"forecast\": {\"period\": \"\", \"committed\": 0, "
            "\"best_case\": 0, \"pipeline\": 0, \"confidence\": \"high|medium|low\"}, "
            "\"quota_tracking\": [{\"rep\": \"\", \"quota\": 0, \"attainment\": 0}], "
            "\"pipeline_health\": {\"coverage\": 0, \"velocity_days\": 0}}"
        )

    async def process(self, state: AgentState) -> AgentState:
        ctx = self.get_context(task_id=state.get("task_id", ""), trace_id=state.get("trace_id", ""))
        messages = [{"role": "system", "content": self.get_system_prompt()},
                    {"role": "user", "content": state.get("task_description", "")}]
        response = await self.call_llm(messages, temperature=0.3, ctx=ctx)
        try: result = json.loads(response.content)
        except json.JSONDecodeError: result = {"raw_response": response.content}
        artifacts = dict(state.get("artifacts", {}))
        artifacts["sales_forecast"] = result
        return {**state, "artifacts": artifacts, "status": "forecast_complete",
                "current_agent": self.name,
                "token_usage": state.get("token_usage", 0) + response.total_tokens}
