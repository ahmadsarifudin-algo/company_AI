"""PricingAgent — Dynamic pricing and margin analysis."""

import json, structlog
from app.agents.base_agent import BaseAgent
from app.agents.state import AgentState
logger = structlog.get_logger()

class PricingAgent(BaseAgent):
    """Manages dynamic pricing, discount approvals, and margin analysis."""

    def get_system_prompt(self) -> str:
        return (
            "You are a Pricing Agent in the Sales Department.\n\n"
            "Responsibilities:\n"
            "1. Calculate optimal pricing based on cost, market, and competition\n"
            "2. Evaluate and approve discount requests\n"
            "3. Analyze margins and profitability\n"
            "4. Create pricing tiers and bundles\n"
            "5. Flag pricing that falls below minimum margins\n\n"
            "Output JSON: {\"pricing\": {\"base_price\": 0, \"recommended_price\": 0, "
            "\"discount_approved\": false, \"margin_pct\": 0, "
            "\"justification\": \"\"}, \"approval_required\": false}"
        )

    async def process(self, state: AgentState) -> AgentState:
        ctx = self.get_context(task_id=state.get("task_id", ""), trace_id=state.get("trace_id", ""))
        messages = [{"role": "system", "content": self.get_system_prompt()},
                    {"role": "user", "content": state.get("task_description", "")}]
        response = await self.call_llm(messages, temperature=0.2, ctx=ctx)
        try: result = json.loads(response.content)
        except json.JSONDecodeError: result = {"raw_response": response.content}
        artifacts = dict(state.get("artifacts", {}))
        artifacts["pricing_result"] = result
        return {**state, "artifacts": artifacts, "status": "pricing_complete",
                "current_agent": self.name,
                "token_usage": state.get("token_usage", 0) + response.total_tokens}
