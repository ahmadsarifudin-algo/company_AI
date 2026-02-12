"""
ProductAnalystAgent — Generates PRDs, acceptance criteria, and KPIs.

Responsibilities:
- Transform stakeholder requests into structured PRDs
- Define acceptance criteria in Gherkin format
- Identify KPIs and success metrics
- Flag risks and out-of-scope items
"""

import json
from typing import Any

import structlog

from app.agents.base_agent import BaseAgent
from app.agents.state import AgentState

logger = structlog.get_logger()


class ProductAnalystAgent(BaseAgent):
    """Generates Product Requirements Documents from stakeholder input."""

    def get_system_prompt(self) -> str:
        return (
            "You are a Product Analyst Agent in the Tech Department.\n\n"
            "Your responsibilities:\n"
            "1. Generate structured PRDs from feature requests\n"
            "2. Write acceptance criteria in Gherkin format (Given/When/Then)\n"
            "3. Define measurable KPIs and success metrics\n"
            "4. Identify risks, dependencies, and out-of-scope items\n"
            "5. Estimate effort and priority\n\n"
            "Output format (JSON):\n"
            "{\n"
            '  "title": "Feature title",\n'
            '  "summary": "Brief description",\n'
            '  "user_stories": ["As a..., I want..., so that..."],\n'
            '  "acceptance_criteria": [\n'
            '    {"scenario": "name", "given": "...", "when": "...", "then": "..."}\n'
            "  ],\n"
            '  "kpis": [{"metric": "name", "target": "value", "measurement": "how"}],\n'
            '  "risks": ["identified risks"],\n'
            '  "out_of_scope": ["excluded items"],\n'
            '  "priority": "P0|P1|P2|P3",\n'
            '  "estimated_effort": "XS|S|M|L|XL"\n'
            "}\n"
            "Respond ONLY with valid JSON."
        )

    async def process(self, state: AgentState) -> AgentState:
        """Generate a PRD from the task description."""
        ctx = self.get_context(
            task_id=state.get("task_id", ""),
            trace_id=state.get("trace_id", ""),
        )

        task_desc = state.get("task_description", "")
        plan = state.get("artifacts", {}).get("plan_json", {})
        context = f"Task: {task_desc}"
        if plan:
            context += f"\nProject plan context: {json.dumps(plan, indent=2)}"

        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": context},
        ]

        self.log.info("prd_generation_start", trace_id=ctx.trace_id)
        response = await self.call_llm(messages, temperature=0.4, ctx=ctx)

        try:
            prd = json.loads(response.content)
        except json.JSONDecodeError:
            prd = {"raw_response": response.content, "title": task_desc[:80]}

        artifacts = dict(state.get("artifacts", {}))
        artifacts["prd"] = prd

        self.log.info(
            "prd_generation_complete",
            trace_id=ctx.trace_id,
            title=prd.get("title", "unknown"),
            cost_usd=response.cost_usd,
        )

        return {
            **state,
            "artifacts": artifacts,
            "status": "prd_complete",
            "current_agent": self.name,
            "token_usage": state.get("token_usage", 0) + response.total_tokens,
        }
