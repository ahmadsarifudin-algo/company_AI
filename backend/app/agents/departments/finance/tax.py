"""TaxAgent — Tax calculation, filing preparation, and tax planning."""

import json
import structlog
from app.agents.base_agent import BaseAgent
from app.agents.state import AgentState

logger = structlog.get_logger()


class TaxAgent(BaseAgent):
    """Calculates taxes, prepares filings, provides tax planning advice."""

    def get_system_prompt(self) -> str:
        return (
            "You are a Tax Agent in the Finance Department.\n\n"
            "Responsibilities:\n"
            "1. Calculate corporate income tax (PPh Badan)\n"
            "2. Calculate and report VAT (PPN) obligations\n"
            "3. Prepare withholding tax reports (PPh 21/23/26)\n"
            "4. Generate tax filing documents\n"
            "5. Provide tax planning and optimization advice\n\n"
            "Output JSON: {\"tax_calculation\": {\"type\": \"PPh_Badan|PPN|PPh_21\", "
            "\"period\": \"\", \"taxable_income\": 0, \"tax_rate\": 0, \"tax_amount\": 0, "
            "\"deductions\": [], \"credits\": []}, "
            "\"filing\": {\"form\": \"\", \"due_date\": \"\", \"status\": \"draft|ready|filed\"}, "
            "\"planning_notes\": []}"
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
        artifacts["tax_result"] = result
        return {**state, "artifacts": artifacts, "status": "tax_complete",
                "current_agent": self.name,
                "token_usage": state.get("token_usage", 0) + response.total_tokens}
