"""TrainingAgent — Skill gap analysis and learning path design."""

import json, structlog
from app.agents.base_agent import BaseAgent
from app.agents.state import AgentState
logger = structlog.get_logger()

class TrainingAgent(BaseAgent):
    """Analyzes skill gaps and designs training programs."""

    def get_system_prompt(self) -> str:
        return (
            "You are a Training & Development Agent in the HR Department.\n\n"
            "Responsibilities:\n"
            "1. Analyze skill gaps against role requirements\n"
            "2. Design personalized learning paths\n"
            "3. Track certification and training completion\n"
            "4. Recommend training resources and courses\n"
            "5. Measure training ROI and effectiveness\n\n"
            "Output JSON: {\"skill_gaps\": [{\"skill\": \"\", \"current_level\": 0, "
            "\"target_level\": 0, \"priority\": \"high|medium|low\"}], "
            "\"learning_path\": [{\"course\": \"\", \"provider\": \"\", "
            "\"duration\": \"\", \"cost\": 0}], \"training_roi\": {}}"
        )

    async def process(self, state: AgentState) -> AgentState:
        ctx = self.get_context(task_id=state.get("task_id", ""), trace_id=state.get("trace_id", ""))
        messages = [{"role": "system", "content": self.get_system_prompt()},
                    {"role": "user", "content": state.get("task_description", "")}]
        response = await self.call_llm(messages, temperature=0.4, ctx=ctx)
        try: result = json.loads(response.content)
        except json.JSONDecodeError: result = {"raw_response": response.content}
        artifacts = dict(state.get("artifacts", {}))
        artifacts["training_result"] = result
        return {**state, "artifacts": artifacts, "status": "training_complete",
                "current_agent": self.name,
                "token_usage": state.get("token_usage", 0) + response.total_tokens}
