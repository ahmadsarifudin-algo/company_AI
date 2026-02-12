"""DealIntelligenceAgent — Competitive analysis and market insights."""

import json, structlog
from app.agents.base_agent import BaseAgent
from app.agents.state import AgentState
logger = structlog.get_logger()

class DealIntelligenceAgent(BaseAgent):
    """Provides competitive analysis, win/loss analysis, and market insights."""

    def get_system_prompt(self) -> str:
        return (
            "You are a Deal Intelligence Agent in the Sales Department.\n\n"
            "Responsibilities:\n"
            "1. Analyze competitive landscape for specific deals\n"
            "2. Perform win/loss analysis on closed deals\n"
            "3. Provide market intelligence and trends\n"
            "4. Generate battle cards against competitors\n"
            "5. Recommend deal strategies and positioning\n\n"
            "Output JSON: {\"competitive_analysis\": {\"competitors\": [{\"name\": \"\", "
            "\"strengths\": [], \"weaknesses\": [], \"positioning\": \"\"}]}, "
            "\"battle_card\": {}, \"deal_strategy\": {\"recommended_approach\": \"\", "
            "\"key_differentiators\": [], \"risks\": []}}"
        )

    async def process(self, state: AgentState) -> AgentState:
        ctx = self.get_context(task_id=state.get("task_id", ""), trace_id=state.get("trace_id", ""))
        messages = [{"role": "system", "content": self.get_system_prompt()},
                    {"role": "user", "content": state.get("task_description", "")}]
        response = await self.call_llm(messages, temperature=0.4, ctx=ctx)
        try: result = json.loads(response.content)
        except json.JSONDecodeError: result = {"raw_response": response.content}
        artifacts = dict(state.get("artifacts", {}))
        artifacts["deal_intelligence"] = result
        return {**state, "artifacts": artifacts, "status": "deal_intel_complete",
                "current_agent": self.name,
                "token_usage": state.get("token_usage", 0) + response.total_tokens}
