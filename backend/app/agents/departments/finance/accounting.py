"""AccountingAgent — Ledger reconciliation, journal entries, month-end close."""

import json
import structlog
from app.agents.base_agent import BaseAgent
from app.agents.state import AgentState

logger = structlog.get_logger()


class AccountingAgent(BaseAgent):
    """Reconciles ledgers, generates journal entries, performs month-end close."""

    def get_system_prompt(self) -> str:
        return (
            "You are an Accounting Agent in the Finance Department.\n\n"
            "Responsibilities:\n"
            "1. Reconcile general ledger accounts\n"
            "2. Generate journal entries for adjustments\n"
            "3. Perform month-end close procedures\n"
            "4. Identify discrepancies and propose corrections\n"
            "5. Generate financial statements (BS, P&L, CF)\n\n"
            "Output JSON: {\"reconciliation\": {\"accounts\": [], \"discrepancies\": [], "
            "\"journal_entries\": [], \"status\": \"balanced|unbalanced\"}, "
            "\"financial_statements\": {}}"
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
        artifacts["accounting_result"] = result
        return {**state, "artifacts": artifacts, "status": "accounting_complete",
                "current_agent": self.name,
                "token_usage": state.get("token_usage", 0) + response.total_tokens}
