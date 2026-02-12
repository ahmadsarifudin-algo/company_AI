"""ComplianceAgent — Labor law compliance and policy audit."""

import json, structlog
from app.agents.base_agent import BaseAgent
from app.agents.state import AgentState
logger = structlog.get_logger()

class ComplianceAgent(BaseAgent):
    """Ensures labor law compliance and audits HR policies."""

    def get_system_prompt(self) -> str:
        return (
            "You are an HR Compliance Agent.\n\n"
            "Responsibilities:\n"
            "1. Monitor labor law compliance (UU Ketenagakerjaan)\n"
            "2. Track work permits and visa requirements\n"
            "3. Audit HR policies against regulations\n"
            "4. Manage mandatory reporting (Wajib Lapor)\n"
            "5. Handle employee grievance compliance\n\n"
            "Output JSON: {\"compliance_check\": {\"areas\": [{\"area\": \"\", "
            "\"status\": \"compliant|non_compliant\", \"regulation\": \"\", "
            "\"action_required\": \"\"}]}, \"risk_level\": \"low|medium|high\"}"
        )

    async def process(self, state: AgentState) -> AgentState:
        ctx = self.get_context(task_id=state.get("task_id", ""), trace_id=state.get("trace_id", ""))
        messages = [{"role": "system", "content": self.get_system_prompt()},
                    {"role": "user", "content": state.get("task_description", "")}]
        response = await self.call_llm(messages, temperature=0.2, ctx=ctx)
        try: result = json.loads(response.content)
        except json.JSONDecodeError: result = {"raw_response": response.content}
        artifacts = dict(state.get("artifacts", {}))
        artifacts["compliance_result"] = result
        return {**state, "artifacts": artifacts, "status": "compliance_complete",
                "current_agent": self.name,
                "token_usage": state.get("token_usage", 0) + response.total_tokens}
