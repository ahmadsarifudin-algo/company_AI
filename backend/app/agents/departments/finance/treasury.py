"""TreasuryAgent — Cash position monitoring and liquidity management."""

import json
import structlog
from app.agents.base_agent import BaseAgent
from app.agents.state import AgentState

logger = structlog.get_logger()


class TreasuryAgent(BaseAgent):
    """Monitors cash positions, manages liquidity, tracks FX exposure."""

    def get_system_prompt(self) -> str:
        return (
            "You are a Treasury Agent in the Finance Department.\n\n"
            "Responsibilities:\n"
            "1. Monitor daily cash positions across accounts\n"
            "2. Manage liquidity and short-term investments\n"
            "3. Track foreign exchange exposure\n"
            "4. Optimize working capital\n"
            "5. Generate treasury reports and cash forecasts\n\n"
            "Output JSON: {\"cash_position\": {\"accounts\": [{\"name\": \"\", "
            "\"balance\": 0, \"currency\": \"IDR\"}], \"total\": 0}, "
            "\"fx_exposure\": [{\"currency\": \"\", \"amount\": 0, \"hedge_status\": \"\"}], "
            "\"liquidity_ratio\": 0, \"recommendations\": []}"
        )

    async def process(self, state: AgentState) -> AgentState:
        ctx = self.get_context(task_id=state.get("task_id", ""), trace_id=state.get("trace_id", ""))
        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": state.get("task_description", "")},
        ]
        response = await self.call_llm(messages, temperature=0.2, ctx=ctx)
        try:
            result = json.loads(response.content)
        except json.JSONDecodeError:
            result = {"raw_response": response.content}
        artifacts = dict(state.get("artifacts", {}))
        artifacts["treasury_report"] = result
        return {**state, "artifacts": artifacts, "status": "treasury_complete",
                "current_agent": self.name,
                "token_usage": state.get("token_usage", 0) + response.total_tokens}
