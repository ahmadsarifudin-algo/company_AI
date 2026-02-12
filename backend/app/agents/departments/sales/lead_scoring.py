"""LeadScoringAgent — Lead qualification and prioritization."""

import json, structlog
from app.agents.base_agent import BaseAgent
from app.agents.state import AgentState
logger = structlog.get_logger()

class LeadScoringAgent(BaseAgent):
    """Scores and qualifies leads based on firmographic and behavioral data."""

    def get_system_prompt(self) -> str:
        return (
            "You are a Lead Scoring Agent in the Sales Department.\n\n"
            "Responsibilities:\n"
            "1. Score leads using firmographic criteria (company size, industry, revenue)\n"
            "2. Analyze behavioral signals (website visits, email engagement)\n"
            "3. Classify leads as MQL/SQL/SAL\n"
            "4. Prioritize leads for sales team follow-up\n"
            "5. Generate lead pipeline reports\n\n"
            "Output JSON: {\"leads\": [{\"name\": \"\", \"company\": \"\", "
            "\"score\": 0, \"grade\": \"A|B|C|D\", \"qualification\": \"MQL|SQL|SAL\", "
            "\"next_action\": \"\"}], \"pipeline_summary\": {}}"
        )

    async def process(self, state: AgentState) -> AgentState:
        ctx = self.get_context(task_id=state.get("task_id", ""), trace_id=state.get("trace_id", ""))
        messages = [{"role": "system", "content": self.get_system_prompt()},
                    {"role": "user", "content": state.get("task_description", "")}]
        response = await self.call_llm(messages, temperature=0.3, ctx=ctx)
        try: result = json.loads(response.content)
        except json.JSONDecodeError: result = {"raw_response": response.content}
        artifacts = dict(state.get("artifacts", {}))
        artifacts["lead_scoring"] = result
        return {**state, "artifacts": artifacts, "status": "lead_scoring_complete",
                "current_agent": self.name,
                "token_usage": state.get("token_usage", 0) + response.total_tokens}
