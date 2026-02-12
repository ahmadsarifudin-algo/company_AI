"""
ArchitectAgent — Produces HLD/LLD, API contracts, and threat models.

Responsibilities:
- Generate High-Level Design from PRD
- Produce Low-Level Design with component details
- Define API contracts (OpenAPI-style)
- Assess infrastructure impact
- Create threat model summary
"""

import json
from typing import Any

import structlog

from app.agents.base_agent import BaseAgent
from app.agents.state import AgentState

logger = structlog.get_logger()


class ArchitectAgent(BaseAgent):
    """Produces architecture design documents from PRDs."""

    def get_system_prompt(self) -> str:
        return (
            "You are a Software Architect Agent in the Tech Department.\n\n"
            "Your responsibilities:\n"
            "1. Produce High-Level Design (HLD) from PRD\n"
            "2. Create Low-Level Design (LLD) with component breakdown\n"
            "3. Define API contracts in OpenAPI-style JSON\n"
            "4. Assess infrastructure impact (new services, DB changes, scaling)\n"
            "5. Create a threat model summary (STRIDE)\n\n"
            "Output format (JSON):\n"
            "{\n"
            '  "hld": {\n'
            '    "overview": "Architecture summary",\n'
            '    "components": [{"name": "...", "type": "service|db|queue", "description": "..."}],\n'
            '    "data_flow": "Description of data flow between components",\n'
            '    "tech_stack": ["technology choices"]\n'
            "  },\n"
            '  "lld": {\n'
            '    "modules": [{"name": "...", "files": ["..."], "dependencies": ["..."]}],\n'
            '    "database_changes": [{"table": "...", "action": "create|alter", "columns": ["..."]}],\n'
            '    "api_endpoints": [{"method": "GET|POST", "path": "/...", "request": {}, "response": {}}]\n'
            "  },\n"
            '  "infrastructure_impact": {"new_services": [], "scaling_notes": "..."},\n'
            '  "threat_model": {"threats": [{"category": "STRIDE", "description": "...", "mitigation": "..."}]}\n'
            "}\n"
            "Respond ONLY with valid JSON."
        )

    async def process(self, state: AgentState) -> AgentState:
        """Generate architecture design from PRD."""
        ctx = self.get_context(
            task_id=state.get("task_id", ""),
            trace_id=state.get("trace_id", ""),
        )

        prd = state.get("artifacts", {}).get("prd", {})
        task_desc = state.get("task_description", "")
        context = f"Task: {task_desc}\nPRD: {json.dumps(prd, indent=2)}" if prd else task_desc

        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": context},
        ]

        self.log.info("architecture_design_start", trace_id=ctx.trace_id)
        response = await self.call_llm(messages, temperature=0.3, ctx=ctx)

        try:
            design = json.loads(response.content)
        except json.JSONDecodeError:
            design = {"raw_response": response.content}

        artifacts = dict(state.get("artifacts", {}))
        artifacts["architecture"] = design

        self.log.info(
            "architecture_design_complete",
            trace_id=ctx.trace_id,
            cost_usd=response.cost_usd,
        )

        return {
            **state,
            "artifacts": artifacts,
            "status": "architecture_complete",
            "current_agent": self.name,
            "token_usage": state.get("token_usage", 0) + response.total_tokens,
        }
