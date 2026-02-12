"""
DevOpsAgent — CI/CD configuration and deployment preparation.

Responsibilities:
- Generate CI pipeline configurations
- Prepare deployment manifests
- Create rollback plans
- Deployment only via approval gate
"""

import json

import structlog

from app.agents.base_agent import BaseAgent
from app.agents.state import AgentState

logger = structlog.get_logger()


class DevOpsAgent(BaseAgent):
    """Generates CI/CD configs and deployment preparations."""

    def get_system_prompt(self) -> str:
        return (
            "You are a DevOps Agent in the Tech Department.\n\n"
            "Your responsibilities:\n"
            "1. Generate CI/CD pipeline configurations (GitHub Actions / GitLab CI)\n"
            "2. Create Docker / container configurations\n"
            "3. Prepare deployment manifests (Kubernetes / Docker Compose)\n"
            "4. Design rollback plans and blue-green strategies\n"
            "5. NEVER deploy directly — all deployments require approval gate\n\n"
            "Output format (JSON):\n"
            "{\n"
            '  "ci_config": {"filename": ".github/workflows/ci.yml", "content": "..."},\n'
            '  "docker": {"dockerfile": "...", "compose": "..."},\n'
            '  "deployment": {"strategy": "rolling|blue-green|canary", "manifest": "..."},\n'
            '  "rollback_plan": {"steps": ["..."], "validation": "..."},\n'
            '  "approval_required": true\n'
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
            infra = arch.get("infrastructure_impact", {})
            context += f"\nInfrastructure: {json.dumps(infra)}"

        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": context},
        ]

        self.log.info("devops_config_start", trace_id=ctx.trace_id)
        response = await self.call_llm(messages, temperature=0.2, ctx=ctx)

        try:
            devops_output = json.loads(response.content)
        except json.JSONDecodeError:
            devops_output = {"raw_response": response.content}

        artifacts = dict(state.get("artifacts", {}))
        artifacts["devops_config"] = devops_output

        return {
            **state,
            "artifacts": artifacts,
            "status": "devops_complete",
            "current_agent": self.name,
            "token_usage": state.get("token_usage", 0) + response.total_tokens,
        }
