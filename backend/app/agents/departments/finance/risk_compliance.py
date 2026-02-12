"""RiskComplianceAgent — Regulatory monitoring and risk assessment."""

import json
import structlog
from app.agents.base_agent import BaseAgent
from app.agents.state import AgentState

logger = structlog.get_logger()


class RiskComplianceAgent(BaseAgent):
    """Monitors regulatory requirements, assesses risks, ensures compliance."""

    def get_system_prompt(self) -> str:
        return (
            "You are a Risk & Compliance Agent in the Finance Department.\n\n"
            "Responsibilities:\n"
            "1. Monitor regulatory requirements (OJK, BKPM, tax authority)\n"
            "2. Assess financial and operational risks\n"
            "3. Ensure compliance with financial regulations\n"
            "4. Generate risk heat maps and compliance scorecards\n"
            "5. Track regulatory changes and their impact\n\n"
            "Output JSON: {\"risk_assessment\": {\"risks\": [{\"category\": \"\", "
            "\"description\": \"\", \"likelihood\": \"high|medium|low\", "
            "\"impact\": \"high|medium|low\", \"mitigation\": \"\"}]}, "
            "\"compliance_status\": {\"regulations\": [{\"name\": \"\", "
            "\"status\": \"compliant|non_compliant|in_progress\", \"due_date\": \"\"}]}}"
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
        artifacts["risk_compliance"] = result
        return {**state, "artifacts": artifacts, "status": "risk_compliance_complete",
                "current_agent": self.name,
                "token_usage": state.get("token_usage", 0) + response.total_tokens}
