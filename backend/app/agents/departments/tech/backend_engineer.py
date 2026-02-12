"""
BackendEngineerAgent — Server-side code generation and unit tests.

Responsibilities:
- Generate implementation code from architecture design
- Write unit tests for generated code
- Follow coding standards and patterns
- No direct deployment — outputs code artifacts only
"""

import json

import structlog

from app.agents.base_agent import BaseAgent
from app.agents.state import AgentState

logger = structlog.get_logger()


class BackendEngineerAgent(BaseAgent):
    """Generates server-side code and unit tests from design documents."""

    def get_system_prompt(self) -> str:
        return (
            "You are a Backend Engineer Agent in the Tech Department.\n\n"
            "Your responsibilities:\n"
            "1. Implement server-side code from architecture designs\n"
            "2. Write comprehensive unit tests (pytest)\n"
            "3. Follow clean code principles and project patterns\n"
            "4. Create Pull Request descriptions\n"
            "5. Never deploy — only produce code artifacts\n\n"
            "Output format (JSON):\n"
            "{\n"
            '  "files": [\n'
            '    {"path": "relative/path/to/file.py", "content": "code...", "type": "implementation|test"}\n'
            "  ],\n"
            '  "pr_description": "What changed and why",\n'
            '  "test_commands": ["pytest tests/..."],\n'
            '  "dependencies_added": ["package==version"]\n'
            "}\n"
            "Respond ONLY with valid JSON."
        )

    async def process(self, state: AgentState) -> AgentState:
        ctx = self.get_context(
            task_id=state.get("task_id", ""),
            trace_id=state.get("trace_id", ""),
        )
        arch = state.get("artifacts", {}).get("architecture", {})
        task_desc = state.get("task_description", "")
        context = f"Task: {task_desc}"
        if arch:
            context += f"\nArchitecture: {json.dumps(arch, indent=2)}"

        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": context},
        ]

        self.log.info("backend_code_gen_start", trace_id=ctx.trace_id)
        response = await self.call_llm(messages, temperature=0.2, ctx=ctx)

        try:
            code_output = json.loads(response.content)
        except json.JSONDecodeError:
            code_output = {"raw_response": response.content, "files": []}

        artifacts = dict(state.get("artifacts", {}))
        artifacts["backend_code"] = code_output

        self.log.info(
            "backend_code_gen_complete",
            trace_id=ctx.trace_id,
            file_count=len(code_output.get("files", [])),
            cost_usd=response.cost_usd,
        )

        return {
            **state,
            "artifacts": artifacts,
            "status": "code_generated",
            "current_agent": self.name,
            "token_usage": state.get("token_usage", 0) + response.total_tokens,
        }
