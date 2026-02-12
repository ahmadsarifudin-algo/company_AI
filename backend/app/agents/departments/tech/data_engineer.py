"""
DataEngineerAgent — ETL pipeline design and data quality validation.

Responsibilities:
- Design ETL/ELT pipelines
- Define data warehouse schemas
- Create data quality validation rules
- Plan schema migrations
"""

import json

import structlog

from app.agents.base_agent import BaseAgent
from app.agents.state import AgentState

logger = structlog.get_logger()


class DataEngineerAgent(BaseAgent):
    """Designs ETL pipelines and manages data quality."""

    def get_system_prompt(self) -> str:
        return (
            "You are a Data Engineer Agent in the Tech Department.\n\n"
            "Your responsibilities:\n"
            "1. Design ETL/ELT pipelines (source → transform → load)\n"
            "2. Define data warehouse schemas (star/snowflake)\n"
            "3. Create data quality validation rules (completeness, accuracy, freshness)\n"
            "4. Plan schema migrations with versioning\n"
            "5. Monitor data pipeline health metrics\n\n"
            "Output format (JSON):\n"
            "{\n"
            '  "pipeline": {\n'
            '    "name": "...", "type": "ETL|ELT",\n'
            '    "sources": [{"name": "...", "type": "postgres|api|file", "connection": "..."}],\n'
            '    "transformations": [{"step": "...", "logic": "...", "output": "..."}],\n'
            '    "destination": {"type": "warehouse|lake", "schema": "..."}\n'
            "  },\n"
            '  "schema": {\n'
            '    "tables": [{"name": "...", "columns": [{"name": "...", "type": "...", "nullable": true}]}]\n'
            "  },\n"
            '  "quality_rules": [{"rule": "...", "table": "...", "threshold": "...", "action": "alert|block"}],\n'
            '  "migration_plan": [{"version": "V001", "sql": "...", "rollback": "..."}]\n'
            "}\n"
            "Respond ONLY with valid JSON."
        )

    async def process(self, state: AgentState) -> AgentState:
        ctx = self.get_context(
            task_id=state.get("task_id", ""),
            trace_id=state.get("trace_id", ""),
        )
        task_desc = state.get("task_description", "")
        arch = state.get("artifacts", {}).get("architecture", {})
        context = f"Task: {task_desc}"
        if arch:
            db_changes = arch.get("lld", {}).get("database_changes", [])
            context += f"\nDatabase changes: {json.dumps(db_changes)}"

        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": context},
        ]

        self.log.info("data_pipeline_design_start", trace_id=ctx.trace_id)
        response = await self.call_llm(messages, temperature=0.3, ctx=ctx)

        try:
            data_output = json.loads(response.content)
        except json.JSONDecodeError:
            data_output = {"raw_response": response.content}

        artifacts = dict(state.get("artifacts", {}))
        artifacts["data_pipeline"] = data_output

        return {
            **state,
            "artifacts": artifacts,
            "status": "data_pipeline_complete",
            "current_agent": self.name,
            "token_usage": state.get("token_usage", 0) + response.total_tokens,
        }
