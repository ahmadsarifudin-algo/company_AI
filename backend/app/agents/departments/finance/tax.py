"""
TaxAgent — Tax calculations, filing summaries, tax planning, compliance.
"""
from __future__ import annotations
import json, uuid, structlog
from app.agents.base_agent import BaseAgent
from app.agents.output_schemas import TaxOutput
from app.agents.state import AgentState
from app.core.telemetry import now_ms
logger = structlog.get_logger()

class TaxAgent(BaseAgent):
    """Performs tax calculations, filing, compliance checks, and planning."""
    name = "tax_agent"
    department = "finance"
    role = "agent"

    def _default_system_prompt(self) -> str:
        return (
            "You are a Tax Agent in the Finance Department.\n\n"
            "Responsibilities:\n"
            "1) Calculate tax obligations\n"
            "2) Prepare filing summaries\n"
            "3) Develop tax planning strategies\n"
            "4) Verify compliance status\n\n"
            "Return ONLY valid JSON (no markdown), with keys:\n"
            '{"calculations": {}, "filing_summary": {}, "tax_planning": [], '
            '"compliance_status": "compliant"}\n'
        )

    async def process(self, state: AgentState) -> AgentState:
        start_ms = now_ms()
        span_id = uuid.uuid4().hex
        task_id = state.get("task_id", ""); trace_id = state.get("trace_id", "")
        task_description = state.get("task_description", "")
        ctx = self.get_context(task_id=task_id, trace_id=trace_id, span_id=span_id,
            department=state.get("department", self.department),
            role=state.get("role", self.role), risk_level=state.get("risk_level", "medium"))
        self._emit_lifecycle("agent_started", ctx, {"agent": self.name, "task_id": task_id,
            "trace_id": trace_id, "span_id": span_id})
        response = await self.call_llm([
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": task_description},
        ], temperature=0.1, ctx=ctx)
        content = "" if response is None else getattr(response, "content", "") or ""
        result = self._safe_json_loads(content)
        result = self._validate_output(result, TaxOutput)
        artifact_id = f"tax_{task_id}_{span_id}"
        artifact = {"artifact_id": artifact_id, "type": "finance.tax.report",
            "created_at_ms": now_ms(), "trace_id": trace_id, "span_id": span_id,
            "agent": self.name, "payload": result}
        artifacts = dict(state.get("artifacts", {})); artifacts["tax_report"] = artifact
        total_tokens = int(getattr(response, "total_tokens", 0) or 0)
        prev_tokens = int(state.get("token_usage", 0) or 0)
        end_ms = now_ms(); duration_ms = end_ms - start_ms
        backend_output = self._build_output(
            task_id=task_id, status="completed",
            summary=result.get("summary", "Tax analysis completed."),
            artifact_id=artifact_id, artifact_type=artifact["type"],
            telemetry={"duration_ms": duration_ms, "tokens_used": total_tokens,
                        "span_id": span_id, "trace_id": trace_id})
        self._emit_lifecycle("agent_completed", ctx, {"agent": self.name, "task_id": task_id,
            "duration_ms": duration_ms, "artifact_ids": [artifact_id], "tokens_used": total_tokens})
        return {**state, "status": "tax_complete", "current_agent": self.name,
            "trace_id": trace_id, "last_run_ms": end_ms, "duration_ms": duration_ms,
            "token_usage": prev_tokens + total_tokens, "artifacts": artifacts,
            "output": backend_output}
