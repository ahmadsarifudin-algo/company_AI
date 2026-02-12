"""
QAAgent — Test plan generation and acceptance validation.

Responsibilities:
- Generate comprehensive test plans from PRD/acceptance criteria
- Validate code against definition-of-done
- Create test reports
- Block release if critical tests fail
"""

import json

import structlog

from app.agents.base_agent import BaseAgent
from app.agents.state import AgentState

logger = structlog.get_logger()


class QAAgent(BaseAgent):
    """Generates test plans and validates acceptance criteria."""

    def get_system_prompt(self) -> str:
        return (
            "You are a QA Agent in the Tech Department.\n\n"
            "Your responsibilities:\n"
            "1. Generate test plans from PRD and acceptance criteria\n"
            "2. Create test cases (unit, integration, E2E)\n"
            "3. Validate implementation against definition-of-done\n"
            "4. Produce test reports with pass/fail status\n"
            "5. Recommend release-blocking issues if found\n\n"
            "Output format (JSON):\n"
            "{\n"
            '  "test_plan": {\n'
            '    "scope": "What is being tested",\n'
            '    "test_cases": [\n'
            '      {"id": "TC-001", "category": "unit|integration|e2e",\n'
            '       "description": "...", "steps": ["..."],\n'
            '       "expected_result": "...", "priority": "critical|high|medium|low"}\n'
            "    ]\n"
            "  },\n"
            '  "test_report": {\n'
            '    "total": 0, "passed": 0, "failed": 0, "blocked": 0,\n'
            '    "release_recommendation": "go|no-go",\n'
            '    "blocking_issues": ["..."]\n'
            "  }\n"
            "}\n"
            "Respond ONLY with valid JSON."
        )

    async def process(self, state: AgentState) -> AgentState:
        ctx = self.get_context(
            task_id=state.get("task_id", ""),
            trace_id=state.get("trace_id", ""),
        )
        prd = state.get("artifacts", {}).get("prd", {})
        task_desc = state.get("task_description", "")
        context = f"Task: {task_desc}"
        if prd:
            ac = prd.get("acceptance_criteria", [])
            context += f"\nAcceptance Criteria: {json.dumps(ac)}"

        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": context},
        ]

        self.log.info("qa_test_plan_start", trace_id=ctx.trace_id)
        response = await self.call_llm(messages, temperature=0.3, ctx=ctx)

        try:
            qa_output = json.loads(response.content)
        except json.JSONDecodeError:
            qa_output = {"raw_response": response.content}

        artifacts = dict(state.get("artifacts", {}))
        artifacts["test_plan"] = qa_output

        return {
            **state,
            "artifacts": artifacts,
            "status": "qa_complete",
            "current_agent": self.name,
            "token_usage": state.get("token_usage", 0) + response.total_tokens,
        }
