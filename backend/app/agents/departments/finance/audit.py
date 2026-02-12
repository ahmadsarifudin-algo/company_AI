"""AuditAgent — Internal audit simulation and control testing."""

import json
import structlog
from app.agents.base_agent import BaseAgent
from app.agents.state import AgentState

logger = structlog.get_logger()


class AuditAgent(BaseAgent):
    """Simulates internal audits, tests controls, identifies compliance gaps."""

    def get_system_prompt(self) -> str:
        return (
            "You are an Audit Agent in the Finance Department.\n\n"
            "Responsibilities:\n"
            "1. Simulate internal audit procedures\n"
            "2. Test internal controls for effectiveness\n"
            "3. Identify compliance gaps and weaknesses\n"
            "4. Generate audit findings with severity ratings\n"
            "5. Recommend remediation actions\n\n"
            "Output JSON: {\"audit_report\": {\"scope\": \"\", \"period\": \"\", "
            "\"findings\": [{\"id\": \"\", \"severity\": \"critical|high|medium|low\", "
            "\"description\": \"\", \"control\": \"\", \"recommendation\": \"\"}], "
            "\"overall_rating\": \"satisfactory|needs_improvement|unsatisfactory\"}}"
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
        artifacts["audit_report"] = result
        return {**state, "artifacts": artifacts, "status": "audit_complete",
                "current_agent": self.name,
                "token_usage": state.get("token_usage", 0) + response.total_tokens}
