"""PerformanceAgent — KPI aggregation and performance reviews."""

import json, structlog
from app.agents.base_agent import BaseAgent
from app.agents.state import AgentState
logger = structlog.get_logger()

class PerformanceAgent(BaseAgent):
    """Aggregates KPIs, generates performance reviews, maps talent."""

    def get_system_prompt(self) -> str:
        return (
            "You are a Performance Analytics Agent in the HR Department.\n\n"
            "Responsibilities:\n"
            "1. Aggregate KPIs across employees and teams\n"
            "2. Generate performance review summaries\n"
            "3. Identify high/low performers and talent risks\n"
            "4. Create 9-box talent grid mapping\n"
            "5. Recommend development plans\n\n"
            "Output JSON: {\"kpi_summary\": {\"team\": \"\", \"metrics\": []}, "
            "\"performance_reviews\": [], \"talent_grid\": {}, \"recommendations\": []}"
        )

    async def process(self, state: AgentState) -> AgentState:
        ctx = self.get_context(task_id=state.get("task_id", ""), trace_id=state.get("trace_id", ""))
        messages = [{"role": "system", "content": self.get_system_prompt()},
                    {"role": "user", "content": state.get("task_description", "")}]
        response = await self.call_llm(messages, temperature=0.3, ctx=ctx)
        try: result = json.loads(response.content)
        except json.JSONDecodeError: result = {"raw_response": response.content}
        artifacts = dict(state.get("artifacts", {}))
        artifacts["performance_result"] = result
        return {**state, "artifacts": artifacts, "status": "performance_complete",
                "current_agent": self.name,
                "token_usage": state.get("token_usage", 0) + response.total_tokens}
