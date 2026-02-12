"""RecruitmentAgent — Candidate sourcing, interview questions, pipeline summary."""
from __future__ import annotations
import json, uuid, structlog
from app.agents.base_agent import BaseAgent
from app.agents.output_schemas import RecruitmentOutput
from app.agents.state import AgentState
from app.core.telemetry import now_ms
logger = structlog.get_logger()

class RecruitmentAgent(BaseAgent):
    """Sources candidates, generates interview questions, tracks pipeline."""
    name = "recruitment_agent"; department = "hr"; role = "agent"

    def _default_system_prompt(self) -> str:
        return (
            "You are a Recruitment Agent in the HR Department.\n\n"
            "Responsibilities:\n1) Source and screen candidates\n"
            "2) Generate role-specific interview questions\n"
            "3) Summarize hiring pipeline status\n\n"
            "Return ONLY valid JSON:\n"
            '{"candidates": [], "interview_questions": [], "pipeline_summary": {}}\n'
        )

    async def process(self, state: AgentState) -> AgentState:
        start_ms = now_ms(); span_id = uuid.uuid4().hex
        task_id = state.get("task_id", ""); trace_id = state.get("trace_id", "")
        ctx = self.get_context(task_id=task_id, trace_id=trace_id, span_id=span_id,
            department=state.get("department", self.department), role=state.get("role", self.role),
            risk_level=state.get("risk_level", "low"))
        self._emit_lifecycle("agent_started", ctx, {"agent": self.name, "task_id": task_id,
            "trace_id": trace_id, "span_id": span_id})
        response = await self.call_llm([{"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": state.get("task_description", "")}], temperature=0.3, ctx=ctx)
        content = "" if response is None else getattr(response, "content", "") or ""
        result = self._safe_json_loads(content)
        result = self._validate_output(result, RecruitmentOutput)
        artifact_id = f"recruit_{task_id}_{span_id}"
        artifact = {"artifact_id": artifact_id, "type": "hr.recruitment.pipeline",
            "created_at_ms": now_ms(), "trace_id": trace_id, "span_id": span_id,
            "agent": self.name, "payload": result}
        artifacts = dict(state.get("artifacts", {})); artifacts["recruitment"] = artifact
        total_tokens = int(getattr(response, "total_tokens", 0) or 0)
        prev_tokens = int(state.get("token_usage", 0) or 0)
        end_ms = now_ms(); duration_ms = end_ms - start_ms
        backend_output = self._build_output(
            task_id=task_id, status="completed",
            summary=result.get("summary", "Recruitment analysis completed."),
            artifact_id=artifact_id, artifact_type=artifact["type"],
            telemetry={"duration_ms": duration_ms, "tokens_used": total_tokens,
                        "span_id": span_id, "trace_id": trace_id})
        self._emit_lifecycle("agent_completed", ctx, {"agent": self.name, "task_id": task_id,
            "duration_ms": duration_ms, "artifact_ids": [artifact_id], "tokens_used": total_tokens})
        return {**state, "status": "recruitment_complete", "current_agent": self.name,
            "trace_id": trace_id, "last_run_ms": end_ms, "duration_ms": duration_ms,
            "token_usage": prev_tokens + total_tokens, "artifacts": artifacts, "output": backend_output}
