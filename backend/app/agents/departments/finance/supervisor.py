"""
FinanceSupervisor — Decomposes financial tasks and delegates to specialist agents.

Key goals:
- Deterministic output: always produce a FinancePlanOutput-compatible payload
- Telemetry: duration_ms, token deltas, span_id
- Artifact-driven: produce artifact_id + artifact payload for dashboard rendering
"""

from __future__ import annotations

import json
import uuid
import structlog

from app.agents.base_agent import BaseAgent
from app.agents.output_schemas import FinancePlanOutput
from app.agents.state import AgentState
from app.core.telemetry import now_ms

logger = structlog.get_logger()


class FinanceSupervisor(BaseAgent):
    """Decomposes financial tasks and orchestrates finance specialist agents."""

    name = "finance_supervisor"
    department = "finance"
    role = "supervisor"

    def _default_system_prompt(self) -> str:
        return (
            "You are the Finance Department Supervisor.\n\n"
            "Responsibilities:\n"
            "1) Analyze incoming financial tasks\n"
            "2) Decompose into sub-tasks for specialist agents\n"
            "3) Assign priorities and dependencies\n\n"
            "Available agents:\n"
            "- accounting: Ledger reconciliation, journal entries\n"
            "- budget_planning: Budget proposals, variance analysis\n"
            "- forecasting: Cash-flow projections, revenue scenarios\n"
            "- audit: Internal audit, control testing\n"
            "- risk_compliance: Regulatory compliance, risk assessment\n"
            "- treasury: Cash position, liquidity, FX exposure\n"
            "- invoicing: AR/AP management, aging reports\n"
            "- tax: Tax calculations, filing, compliance\n\n"
            "Return ONLY valid JSON (no markdown), with keys:\n"
            '{"tasks": [{"task_id":"","description":"","assigned_to":"","priority":"medium","depends_on":[]}], '
            '"summary": "", "estimated_steps": 0}\n'
        )

    async def process(self, state: AgentState) -> AgentState:
        start_ms = now_ms()
        span_id = uuid.uuid4().hex

        task_id = state.get("task_id", "")
        trace_id = state.get("trace_id", "")
        task_description = state.get("task_description", "")

        ctx = self.get_context(
            task_id=task_id, trace_id=trace_id, span_id=span_id,
            department=state.get("department", self.department),
            role=state.get("role", self.role),
            risk_level=state.get("risk_level", "medium"),
        )

        self._emit_lifecycle("agent_started", ctx, {
            "agent": self.name, "task_id": task_id,
            "trace_id": trace_id, "span_id": span_id,
        })

        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": task_description},
        ]

        response = await self.call_llm(messages, temperature=0.3, ctx=ctx)

        content = "" if response is None else getattr(response, "content", "") or ""
        result = self._safe_json_loads(content)
        result = self._validate_output(result, FinancePlanOutput)

        artifact_id = f"fin_plan_{task_id}_{span_id}"
        artifact = {
            "artifact_id": artifact_id,
            "type": "finance.supervisor.plan",
            "created_at_ms": now_ms(),
            "trace_id": trace_id, "span_id": span_id,
            "agent": self.name, "payload": result,
        }

        artifacts = dict(state.get("artifacts", {}))
        artifacts["finance_plan"] = artifact

        total_tokens = int(getattr(response, "total_tokens", 0) or 0)
        prev_tokens = int(state.get("token_usage", 0) or 0)
        end_ms = now_ms()
        duration_ms = end_ms - start_ms

        backend_output = self._build_output(
            task_id=task_id,
            status="completed",
            summary=result.get("summary", "Finance task plan generated."),
            artifact_id=artifact_id, artifact_type=artifact["type"],
            telemetry={"duration_ms": duration_ms, "tokens_used": total_tokens,
                        "span_id": span_id, "trace_id": trace_id},
        )

        self._emit_lifecycle("agent_completed", ctx, {
            "agent": self.name, "task_id": task_id,
            "duration_ms": duration_ms, "artifact_ids": [artifact_id],
            "tokens_used": total_tokens,
        })

        return {
            **state, "status": "finance_plan_complete",
            "current_agent": self.name, "trace_id": trace_id,
            "last_run_ms": end_ms, "duration_ms": duration_ms,
            "token_usage": prev_tokens + total_tokens,
            "artifacts": artifacts, "output": backend_output,
        }
