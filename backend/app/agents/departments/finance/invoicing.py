"""InvoicingAgent — Invoice generation, AR/AP management, payment tracking."""

import json
import structlog
from app.agents.base_agent import BaseAgent
from app.agents.state import AgentState

logger = structlog.get_logger()


class InvoicingAgent(BaseAgent):
    """Generates invoices, manages accounts receivable/payable, tracks payments."""

    def get_system_prompt(self) -> str:
        return (
            "You are an Invoicing Agent in the Finance Department.\n\n"
            "Responsibilities:\n"
            "1. Generate invoices from purchase orders or contracts\n"
            "2. Manage accounts receivable (AR) — track customer payments\n"
            "3. Manage accounts payable (AP) — track vendor payments\n"
            "4. Send payment reminders and follow-ups\n"
            "5. Generate aging reports and payment summaries\n\n"
            "Output JSON: {\"invoice\": {\"invoice_number\": \"\", \"vendor\": \"\", "
            "\"amount\": 0, \"currency\": \"IDR\", \"due_date\": \"\", \"line_items\": [], "
            "\"status\": \"draft|sent|paid|overdue\"}, "
            "\"aging_report\": {\"current\": 0, \"30_days\": 0, \"60_days\": 0, \"90_plus\": 0}}"
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
        artifacts["invoicing_result"] = result
        return {**state, "artifacts": artifacts, "status": "invoicing_complete",
                "current_agent": self.name,
                "token_usage": state.get("token_usage", 0) + response.total_tokens}
