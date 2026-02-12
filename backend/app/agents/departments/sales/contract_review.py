"""ContractReviewAgent — Contract terms review and risk assessment."""

import json, structlog
from app.agents.base_agent import BaseAgent
from app.agents.state import AgentState
logger = structlog.get_logger()

class ContractReviewAgent(BaseAgent):
    """Reviews contract terms, identifies risk clauses, manages renewals."""

    def get_system_prompt(self) -> str:
        return (
            "You are a Contract Review Agent in the Sales Department.\n\n"
            "Responsibilities:\n"
            "1. Review contract terms and conditions\n"
            "2. Identify risk clauses (liability, indemnification, SLA)\n"
            "3. Compare against standard contract templates\n"
            "4. Track contract renewals and expirations\n"
            "5. Recommend negotiation points\n\n"
            "Output JSON: {\"review\": {\"contract_type\": \"\", "
            "\"risk_clauses\": [{\"clause\": \"\", \"risk\": \"high|medium|low\", "
            "\"recommendation\": \"\"}], \"deviations_from_standard\": [], "
            "\"overall_risk\": \"acceptable|review_required|reject\"}, "
            "\"renewal_tracking\": {}}"
        )

    async def process(self, state: AgentState) -> AgentState:
        ctx = self.get_context(task_id=state.get("task_id", ""), trace_id=state.get("trace_id", ""))
        messages = [{"role": "system", "content": self.get_system_prompt()},
                    {"role": "user", "content": state.get("task_description", "")}]
        response = await self.call_llm(messages, temperature=0.2, ctx=ctx)
        try: result = json.loads(response.content)
        except json.JSONDecodeError: result = {"raw_response": response.content}
        artifacts = dict(state.get("artifacts", {}))
        artifacts["contract_review"] = result
        return {**state, "artifacts": artifacts, "status": "contract_review_complete",
                "current_agent": self.name,
                "token_usage": state.get("token_usage", 0) + response.total_tokens}
