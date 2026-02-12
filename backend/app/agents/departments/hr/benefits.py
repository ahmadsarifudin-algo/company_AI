"""BenefitsAgent — Benefits eligibility lookup and enrollment management."""

import json, structlog
from app.agents.base_agent import BaseAgent
from app.agents.state import AgentState
logger = structlog.get_logger()

class BenefitsAgent(BaseAgent):
    """Manages employee benefits: eligibility, enrollment, cost analysis."""

    def get_system_prompt(self) -> str:
        return (
            "You are a Benefits Administration Agent in the HR Department.\n\n"
            "Responsibilities:\n"
            "1. Look up employee benefits eligibility\n"
            "2. Process enrollment and changes (BPJS, insurance)\n"
            "3. Calculate benefits costs and employer contributions\n"
            "4. Compare benefits packages and benchmarks\n"
            "5. Generate benefits utilization reports\n\n"
            "Output JSON: {\"eligibility\": [{\"benefit\": \"\", \"eligible\": true, "
            "\"tier\": \"\", \"employer_cost\": 0}], "
            "\"enrollment_status\": {\"bpjs_kesehatan\": \"\", \"bpjs_tk\": \"\", "
            "\"private_insurance\": \"\"}, \"cost_summary\": {}}"
        )

    async def process(self, state: AgentState) -> AgentState:
        ctx = self.get_context(task_id=state.get("task_id", ""), trace_id=state.get("trace_id", ""))
        messages = [{"role": "system", "content": self.get_system_prompt()},
                    {"role": "user", "content": state.get("task_description", "")}]
        response = await self.call_llm(messages, temperature=0.2, ctx=ctx)
        try: result = json.loads(response.content)
        except json.JSONDecodeError: result = {"raw_response": response.content}
        artifacts = dict(state.get("artifacts", {}))
        artifacts["benefits_result"] = result
        return {**state, "artifacts": artifacts, "status": "benefits_complete",
                "current_agent": self.name,
                "token_usage": state.get("token_usage", 0) + response.total_tokens}
