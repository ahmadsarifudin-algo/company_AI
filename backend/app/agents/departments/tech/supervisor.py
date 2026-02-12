"""
TechSupervisor — Decomposes technical tasks and delegates to specialist agents.

Key goals:
- Deterministic output: always produce a SupervisorPlanOutput-compatible payload
- Telemetry: duration_ms, token deltas, span_id
- Artifact-driven: produce artifact_id + artifact payload for dashboard rendering
"""

from __future__ import annotations

import json
import uuid
import structlog

from app.agents.base_agent import BaseAgent
from app.agents.output_schemas import TechPlanOutput
from app.agents.state import AgentState
from app.core.telemetry import now_ms

logger = structlog.get_logger()


class TechSupervisor(BaseAgent):
    """
    Decomposes technical tasks and orchestrates specialist agents.

    Notes:
    - Assumes orchestration layer already injected trace_id, task_id, etc.
    - Policy checks & tool sandboxing happen in the gateway / broker layer.
    """

    name = "tech_supervisor"
    department = "tech"
    role = "supervisor"

    def _default_system_prompt(self) -> str:
        return (
            "You are the Tech Department Supervisor.\n\n"
            "Responsibilities:\n"
            "1) Analyze incoming technical tasks\n"
            "2) Decompose into sub-tasks for specialist agents\n"
            "3) Assign priorities and dependencies\n"
            "4) Estimate effort and timeline\n\n"
            "Available agents:\n"
            "- product_analyst: PRD, acceptance criteria, KPIs\n"
            "- architect: HLD/LLD, API contracts, threat model\n"
            "- backend_engineer: Backend code, tests, PR descriptions\n"
            "- frontend_engineer: UI components, tests, PR descriptions\n"
            "- qa: Test plans, coverage analysis, release readiness\n"
            "- devops: CI/CD, Dockerfiles, deployment manifests\n"
            "- sre: Monitoring, alerts, runbooks, postmortem\n"
            "- security: Vuln scanning, OWASP review, secrets audit\n"
            "- data_engineer: Data pipelines, schema design, migrations\n"
            "- technical_writer: API docs, changelogs, ADRs\n\n"
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
            task_id=task_id,
            trace_id=trace_id,
            span_id=span_id,
            department=state.get("department", self.department),
            role=state.get("role", self.role),
            risk_level=state.get("risk_level", "low"),
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
        result = self._validate_output(result, TechPlanOutput)

        artifact_id = f"tech_plan_{task_id}_{span_id}"
        artifact = {
            "artifact_id": artifact_id,
            "type": "tech.supervisor.plan",
            "created_at_ms": now_ms(),
            "trace_id": trace_id,
            "span_id": span_id,
            "agent": self.name,
            "payload": result,
        }

        artifacts = dict(state.get("artifacts", {}))
        artifacts["tech_plan"] = artifact

        total_tokens = int(getattr(response, "total_tokens", 0) or 0)
        prev_tokens = int(state.get("token_usage", 0) or 0)

        end_ms = now_ms()
        duration_ms = end_ms - start_ms

        backend_output = self._build_output(
            task_id=task_id,
            status="completed",
            summary=result.get("summary", "Tech task plan generated."),
            artifact_id=artifact_id,
            artifact_type=artifact["type"],
            telemetry={
                "duration_ms": duration_ms,
                "tokens_used": total_tokens,
                "span_id": span_id,
                "trace_id": trace_id,
            },
        )

        self._emit_lifecycle("agent_completed", ctx, {
            "agent": self.name, "task_id": task_id,
            "duration_ms": duration_ms, "artifact_ids": [artifact_id],
            "tokens_used": total_tokens,
        })

        return {
            **state,
            "status": "tech_plan_complete",
            "current_agent": self.name,
            "trace_id": trace_id,
            "last_run_ms": end_ms,
            "duration_ms": duration_ms,
            "token_usage": prev_tokens + total_tokens,
            "artifacts": artifacts,
            "output": backend_output,
        }
