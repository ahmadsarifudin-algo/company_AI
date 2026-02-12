"""PayrollAgent — Payroll validation and anomaly detection."""

import json, structlog
from app.agents.base_agent import BaseAgent
from app.agents.state import AgentState
logger = structlog.get_logger()

class PayrollAgent(BaseAgent):
    """Validates payroll data, detects anomalies, benchmarks salaries."""

    def get_system_prompt(self) -> str:
        return (
            "You are a Payroll Validation Agent in the HR Department.\n\n"
            "Responsibilities:\n"
            "1. Validate payroll calculations and deductions\n"
            "2. Detect anomalies (unusual overtime, duplicate payments)\n"
            "3. Benchmark salaries against market data\n"
            "4. Verify tax withholding compliance (PPh 21)\n"
            "5. Generate payroll summary reports\n\n"
            "Output JSON: {\"validation\": {\"total_employees\": 0, \"total_gross\": 0, "
            "\"anomalies\": [{\"employee_id\": \"\", \"type\": \"\", \"details\": \"\"}]}, "
            "\"compliance_status\": \"compliant|issues_found\"}"
        )

    async def process(self, state: AgentState) -> AgentState:
        ctx = self.get_context(task_id=state.get("task_id", ""), trace_id=state.get("trace_id", ""))
        messages = [{"role": "system", "content": self.get_system_prompt()},
                    {"role": "user", "content": state.get("task_description", "")}]
        response = await self.call_llm(messages, temperature=0.2, ctx=ctx)
        try: result = json.loads(response.content)
        except json.JSONDecodeError: result = {"raw_response": response.content}
        artifacts = dict(state.get("artifacts", {}))
        artifacts["payroll_result"] = result
        return {**state, "artifacts": artifacts, "status": "payroll_complete",
                "current_agent": self.name,
                "token_usage": state.get("token_usage", 0) + response.total_tokens}
