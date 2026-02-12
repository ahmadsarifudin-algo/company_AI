"""RecruitmentAgent — CV screening, candidate ranking, interview scheduling."""

import json
import structlog
from app.agents.base_agent import BaseAgent
from app.agents.state import AgentState

logger = structlog.get_logger()


class RecruitmentAgent(BaseAgent):
    """Screens resumes, ranks candidates, and coordinates recruitment."""

    def get_system_prompt(self) -> str:
        return (
            "You are a Recruitment Agent in the HR Department.\n\n"
            "Responsibilities:\n"
            "1. Screen CVs/resumes against job requirements\n"
            "2. Rank candidates by fit score\n"
            "3. Generate interview question sets\n"
            "4. Coordinate interview scheduling\n"
            "5. Produce recruitment pipeline reports\n\n"
            "Output JSON: {\"candidates\": [{\"name\": \"\", \"score\": 0, "
            "\"strengths\": [], \"gaps\": [], \"recommendation\": \"advance|hold|reject\"}], "
            "\"interview_questions\": [], \"pipeline_summary\": {}}"
        )

    async def process(self, state: AgentState) -> AgentState:
        ctx = self.get_context(task_id=state.get("task_id", ""), trace_id=state.get("trace_id", ""))
        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": state.get("task_description", "")},
        ]
        response = await self.call_llm(messages, temperature=0.3, ctx=ctx)
        try:
            result = json.loads(response.content)
        except json.JSONDecodeError:
            result = {"raw_response": response.content}
        artifacts = dict(state.get("artifacts", {}))
        artifacts["recruitment_result"] = result
        return {**state, "artifacts": artifacts, "status": "recruitment_complete",
                "current_agent": self.name,
                "token_usage": state.get("token_usage", 0) + response.total_tokens}
