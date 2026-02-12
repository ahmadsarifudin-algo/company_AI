"""
FrontendEngineerAgent — UI code generation and component tests.

Responsibilities:
- Implement UI components from design specs
- Write component tests
- Follow design system patterns
- Create Pull Request descriptions
"""

import json

import structlog

from app.agents.base_agent import BaseAgent
from app.agents.state import AgentState

logger = structlog.get_logger()


class FrontendEngineerAgent(BaseAgent):
    """Generates frontend UI code and component tests."""

    def get_system_prompt(self) -> str:
        return (
            "You are a Frontend Engineer Agent in the Tech Department.\n\n"
            "Your responsibilities:\n"
            "1. Implement UI components from design specifications\n"
            "2. Write component tests (React Testing Library / Vitest)\n"
            "3. Follow the project's design system and component patterns\n"
            "4. Ensure responsive design and accessibility\n"
            "5. Create Pull Request descriptions\n\n"
            "Output format (JSON):\n"
            "{\n"
            '  "files": [\n'
            '    {"path": "src/components/...", "content": "code...", "type": "component|test|style"}\n'
            "  ],\n"
            '  "pr_description": "What changed and why",\n'
            '  "test_commands": ["npm test -- ..."],\n'
            '  "dependencies_added": ["package@version"]\n'
            "}\n"
            "Respond ONLY with valid JSON."
        )

    async def process(self, state: AgentState) -> AgentState:
        ctx = self.get_context(
            task_id=state.get("task_id", ""),
            trace_id=state.get("trace_id", ""),
        )
        arch = state.get("artifacts", {}).get("architecture", {})
        prd = state.get("artifacts", {}).get("prd", {})
        task_desc = state.get("task_description", "")
        context = f"Task: {task_desc}"
        if prd:
            context += f"\nPRD: {json.dumps(prd, indent=2)}"
        if arch:
            lld = arch.get("lld", {})
            context += f"\nAPI Endpoints: {json.dumps(lld.get('api_endpoints', []))}"

        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": context},
        ]

        self.log.info("frontend_code_gen_start", trace_id=ctx.trace_id)
        response = await self.call_llm(messages, temperature=0.2, ctx=ctx)

        try:
            code_output = json.loads(response.content)
        except json.JSONDecodeError:
            code_output = {"raw_response": response.content, "files": []}

        artifacts = dict(state.get("artifacts", {}))
        artifacts["frontend_code"] = code_output

        return {
            **state,
            "artifacts": artifacts,
            "status": "frontend_code_generated",
            "current_agent": self.name,
            "token_usage": state.get("token_usage", 0) + response.total_tokens,
        }
