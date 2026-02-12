"""OnboardingAgent — New hire checklists and contract drafts."""

import json, structlog
from app.agents.base_agent import BaseAgent
from app.agents.state import AgentState
logger = structlog.get_logger()

class OnboardingAgent(BaseAgent):
    """Manages new hire onboarding: checklists, contracts, orientation."""

    def get_system_prompt(self) -> str:
        return (
            "You are an Onboarding Agent in the HR Department.\n\n"
            "Responsibilities:\n"
            "1. Generate onboarding checklists for new hires\n"
            "2. Draft employment contracts from templates\n"
            "3. Schedule orientation sessions\n"
            "4. Track onboarding completion status\n"
            "5. Coordinate IT setup and access provisioning\n\n"
            "Output JSON: {\"checklist\": [{\"task\": \"\", \"assignee\": \"\", "
            "\"due_date\": \"\", \"status\": \"pending|complete\"}], "
            "\"contract_draft\": {\"type\": \"\", \"terms\": {}}, "
            "\"orientation_schedule\": []}"
        )

    async def process(self, state: AgentState) -> AgentState:
        ctx = self.get_context(task_id=state.get("task_id", ""), trace_id=state.get("trace_id", ""))
        messages = [{"role": "system", "content": self.get_system_prompt()},
                    {"role": "user", "content": state.get("task_description", "")}]
        response = await self.call_llm(messages, temperature=0.3, ctx=ctx)
        try: result = json.loads(response.content)
        except json.JSONDecodeError: result = {"raw_response": response.content}
        artifacts = dict(state.get("artifacts", {}))
        artifacts["onboarding_result"] = result
        return {**state, "artifacts": artifacts, "status": "onboarding_complete",
                "current_agent": self.name,
                "token_usage": state.get("token_usage", 0) + response.total_tokens}
