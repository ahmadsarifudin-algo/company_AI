"""
SREAgent — Monitoring, incident response, and postmortem drafting.

Responsibilities:
- Define monitoring rules and alerts
- Draft incident response runbooks
- Generate postmortem documents
- Analyze system reliability metrics
"""

import json

import structlog

from app.agents.base_agent import BaseAgent
from app.agents.state import AgentState

logger = structlog.get_logger()


class SREAgent(BaseAgent):
    """Generates monitoring configs, incident response, and postmortems."""

    def get_system_prompt(self) -> str:
        return (
            "You are an SRE (Site Reliability Engineer) Agent in the Tech Department.\n\n"
            "Your responsibilities:\n"
            "1. Define monitoring rules and alerting thresholds\n"
            "2. Create incident response runbooks\n"
            "3. Draft blameless postmortem documents\n"
            "4. Analyze reliability metrics (SLOs, SLIs, error budgets)\n"
            "5. Recommend scaling and resilience improvements\n\n"
            "Output format (JSON):\n"
            "{\n"
            '  "monitoring": {\n'
            '    "alerts": [{"name": "...", "condition": "...", "severity": "critical|warning|info", "channel": "..."}],\n'
            '    "dashboards": [{"name": "...", "panels": ["..."]}]\n'
            "  },\n"
            '  "runbook": {"title": "...", "steps": ["..."], "escalation": ["..."]},\n'
            '  "postmortem": {"incident": "...", "timeline": ["..."], "root_cause": "...", "action_items": ["..."]},\n'
            '  "slo": {"target": "99.9%", "current": "...", "error_budget_remaining": "..."}\n'
            "}\n"
            "Respond ONLY with valid JSON."
        )

    async def process(self, state: AgentState) -> AgentState:
        ctx = self.get_context(
            task_id=state.get("task_id", ""),
            trace_id=state.get("trace_id", ""),
        )
        task_desc = state.get("task_description", "")
        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": task_desc},
        ]

        self.log.info("sre_analysis_start", trace_id=ctx.trace_id)
        response = await self.call_llm(messages, temperature=0.3, ctx=ctx)

        try:
            sre_output = json.loads(response.content)
        except json.JSONDecodeError:
            sre_output = {"raw_response": response.content}

        artifacts = dict(state.get("artifacts", {}))
        artifacts["sre_output"] = sre_output

        return {
            **state,
            "artifacts": artifacts,
            "status": "sre_complete",
            "current_agent": self.name,
            "token_usage": state.get("token_usage", 0) + response.total_tokens,
        }
