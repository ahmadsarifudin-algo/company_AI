"""
TechnicalWriterAgent — API documentation, changelogs, and ADRs.

Responsibilities:
- Generate API documentation from code/specs
- Maintain changelogs and release notes
- Create Architecture Decision Records (ADRs)
- Update internal wiki and knowledge base
"""

import json

import structlog

from app.agents.base_agent import BaseAgent
from app.agents.state import AgentState

logger = structlog.get_logger()


class TechnicalWriterAgent(BaseAgent):
    """Generates technical documentation from code and specs."""

    def get_system_prompt(self) -> str:
        return (
            "You are a Technical Writer Agent in the Tech Department.\n\n"
            "Your responsibilities:\n"
            "1. Generate API documentation (OpenAPI / Swagger style)\n"
            "2. Write changelogs and release notes\n"
            "3. Create Architecture Decision Records (ADRs)\n"
            "4. Maintain README files and getting-started guides\n"
            "5. Update internal wiki and knowledge base articles\n\n"
            "Output format (JSON):\n"
            "{\n"
            '  "documents": [\n'
            '    {"type": "api_doc|changelog|adr|readme|wiki",\n'
            '     "title": "...",\n'
            '     "content": "markdown content...",\n'
            '     "path": "docs/..."}\n'
            "  ],\n"
            '  "summary": "What was documented and why"\n'
            "}\n"
            "Respond ONLY with valid JSON."
        )

    async def process(self, state: AgentState) -> AgentState:
        ctx = self.get_context(
            task_id=state.get("task_id", ""),
            trace_id=state.get("trace_id", ""),
        )
        task_desc = state.get("task_description", "")
        artifacts_in = state.get("artifacts", {})
        # Build context from whatever artifacts are available
        context_parts = [f"Task: {task_desc}"]
        if "architecture" in artifacts_in:
            context_parts.append(f"Architecture: {json.dumps(artifacts_in['architecture'], indent=2)}")
        if "backend_code" in artifacts_in:
            endpoints = artifacts_in["architecture"].get("lld", {}).get("api_endpoints", []) if "architecture" in artifacts_in else []
            context_parts.append(f"API Endpoints: {json.dumps(endpoints)}")
        if "prd" in artifacts_in:
            context_parts.append(f"PRD Title: {artifacts_in['prd'].get('title', '')}")

        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": "\n\n".join(context_parts)},
        ]

        self.log.info("doc_generation_start", trace_id=ctx.trace_id)
        response = await self.call_llm(messages, temperature=0.4, ctx=ctx)

        try:
            docs_output = json.loads(response.content)
        except json.JSONDecodeError:
            docs_output = {"raw_response": response.content, "documents": []}

        artifacts = dict(artifacts_in)
        artifacts["documentation"] = docs_output

        return {
            **state,
            "artifacts": artifacts,
            "status": "documentation_complete",
            "current_agent": self.name,
            "token_usage": state.get("token_usage", 0) + response.total_tokens,
        }
