"""
MarketingDigitalAgent — Handles conversations with unknown/external users.

This agent serves as the default handler for users who are not registered
in the system. It provides friendly, informative responses about the company
and can direct users to appropriate resources.
"""

from __future__ import annotations

import json
import uuid
import structlog

from app.agents.base_agent import BaseAgent
from app.agents.state import AgentState
from app.core.telemetry import now_ms

logger = structlog.get_logger()


class MarketingDigitalAgent(BaseAgent):
    """Handles external/unknown user conversations with a marketing focus."""

    name = "marketing_digital"
    department = "marketing"
    role = "agent"

    def _default_system_prompt(self) -> str:
        return (
            "You are the Marketing Digital Agent.\n\n"
            "Responsibilities:\n"
            "1) Greet visitors and external users warmly\n"
            "2) Provide general information about the company\n"
            "3) Answer product and service inquiries\n"
            "4) Direct users to appropriate channels or registration\n"
            "5) Collect lead information when appropriate\n\n"
            "Guidelines:\n"
            "- Be friendly, welcoming, and professional\n"
            "- Answer in the user's language\n"
            "- Do NOT share internal/confidential information\n"
            "- Encourage users to register for full access\n"
            "- If asked about specific department topics, explain that\n"
            "  they need to register and contact the relevant department\n"
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

        response = await self.call_llm(messages, temperature=0.7, ctx=ctx)

        content = "" if response is None else getattr(response, "content", "") or ""

        artifact_id = f"marketing_response_{task_id}_{span_id}"
        total_tokens = int(getattr(response, "total_tokens", 0) or 0)
        prev_tokens = int(state.get("token_usage", 0) or 0)

        end_ms = now_ms()
        duration_ms = end_ms - start_ms

        backend_output = self._build_output(
            task_id=task_id,
            status="completed",
            summary=content[:200] or "Marketing response generated.",
            artifact_id=artifact_id,
            artifact_type="marketing.digital.response",
            telemetry={
                "duration_ms": duration_ms,
                "tokens_used": total_tokens,
                "span_id": span_id,
                "trace_id": trace_id,
            },
        )

        self._emit_lifecycle("agent_completed", ctx, {
            "agent": self.name, "task_id": task_id,
            "duration_ms": duration_ms,
            "tokens_used": total_tokens,
        })

        return {
            **state,
            "status": "marketing_response_complete",
            "current_agent": self.name,
            "trace_id": trace_id,
            "last_run_ms": end_ms,
            "duration_ms": duration_ms,
            "token_usage": prev_tokens + total_tokens,
            "output": backend_output,
        }
