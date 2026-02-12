"""
FinanceSupervisor — Department-level orchestrator for Finance.

Routes financial tasks to the appropriate specialist agent.
"""

import json

import structlog

from app.agents.base_agent import BaseAgent
from app.agents.state import AgentState

logger = structlog.get_logger()

FINANCE_AGENTS = {
    "Accounting": "Ledger reconciliation, journal entries, month-end close",
    "BudgetPlanning": "Budget proposals, variance analysis, forecasting",
    "Forecasting": "Cashflow projection, revenue modeling, scenario analysis",
    "Audit": "Internal audit simulation, compliance checks, control testing",
    "RiskCompliance": "Regulatory monitoring (OJK/BKPM), risk assessment",
    "Treasury": "Cash position monitoring, liquidity management, FX exposure",
    "Invoicing": "Invoice generation, AR/AP management, payment tracking",
    "Tax": "Tax calculation, filing preparation, tax planning",
}


class FinanceSupervisor(BaseAgent):
    """Finance Department Supervisor — routes tasks to finance specialists."""

    def get_system_prompt(self) -> str:
        agent_list = "\n".join(
            f"  - {name}: {desc}" for name, desc in FINANCE_AGENTS.items()
        )
        return (
            "You are the Finance Department Supervisor.\n\n"
            "Your role:\n"
            "1. Analyze financial requests and decompose into tasks\n"
            "2. Assign each task to the appropriate finance specialist\n"
            "3. Ensure compliance with financial regulations\n"
            "4. Flag high-value transactions for approval\n"
            "5. Coordinate cross-functional financial activities\n\n"
            f"Available specialists:\n{agent_list}\n\n"
            "Output valid JSON plan with tasks, assignments, and risk flags."
        )

    async def process(self, state: AgentState) -> AgentState:
        ctx = self.get_context(
            task_id=state.get("task_id", ""),
            trace_id=state.get("trace_id", ""),
        )
        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": state.get("task_description", "")},
        ]

        response = await self.call_llm(messages, temperature=0.3, ctx=ctx)

        try:
            plan = json.loads(response.content)
        except json.JSONDecodeError:
            plan = {"raw_response": response.content, "tasks": []}

        artifacts = dict(state.get("artifacts", {}))
        artifacts["finance_plan"] = plan

        return {
            **state,
            "artifacts": artifacts,
            "status": "planned",
            "current_agent": self.name,
            "token_usage": state.get("token_usage", 0) + response.total_tokens,
        }
