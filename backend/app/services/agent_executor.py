"""
Agent Executor Service — Bridge between API requests and LangGraph execution.

Handles:
- Loading agent config from DB
- Building the LangGraph execution graph
- Dispatching execution (sync or async via Celery)
- Updating task status in DB
- Collecting results and audit logging
"""

import time
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.supervisor import build_global_graph, create_default_state
from app.core.config import get_settings
from app.models.agent import Agent
from app.models.task import Task
from app.services.audit_service import AuditService

logger = structlog.get_logger()
settings = get_settings()


class AgentExecutorService:
    """Orchestrates agent task execution through the LangGraph pipeline."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit = AuditService(db)

    async def execute_task(
        self,
        task_id: str,
        agent_id: str | None = None,
        input_text: str | None = None,
    ) -> dict[str, Any]:
        """Execute a task through the agent pipeline.

        Flow:
        1. Load task from DB
        2. Find/assign agent
        3. Build LangGraph graph
        4. Run graph with initial state
        5. Update task with results
        6. Log audit entry

        Args:
            task_id: ID of the task to execute.
            agent_id: Optional specific agent ID. If None, auto-select.
            input_text: Optional override for task description.

        Returns:
            Execution result dict with status, output, and metrics.
        """
        start_time = time.time()

        # 1. Load task
        task = await self._get_task(task_id)
        if not task:
            return {"error": f"Task {task_id} not found", "status": "failed"}

        # 2. Find agent
        agent = await self._get_or_assign_agent(
            agent_id=agent_id or task.assigned_agent_id,
            department=task.department,
        )
        if not agent:
            return {"error": "No available agent for this department", "status": "failed"}

        # Update task with assignment
        task.assigned_agent_id = agent.id
        task.status = "running"
        await self.db.flush()

        logger.info(
            "executing_task",
            task_id=task_id,
            agent=agent.name,
            department=task.department,
        )

        # 3. Build graph and initial state
        graph = build_global_graph()
        initial_state = create_default_state(
            task_id=task_id,
            task_description=input_text or task.description or task.title,
            department=task.department,
            agent_id=agent.id,
            agent_name=agent.name,
            agent_tier=agent.tier,
            max_tool_calls=settings.AGENT_MAX_TOOL_CALLS,
            max_tokens=settings.AGENT_MAX_TOKENS,
        )

        # 4. Run graph
        try:
            config = {"configurable": {"thread_id": task_id}}
            final_state = await graph.ainvoke(initial_state, config=config)

            # 5. Update task with results
            task.status = final_state.get("status", "completed")
            task.result_json = final_state.get("result", {})
            await self.db.flush()

            # 6. Audit log
            elapsed_ms = (time.time() - start_time) * 1000
            await self.audit.log_action(
                agent_name=agent.name,
                department=task.department,
                action_type="task_execution",
                details=f"Task '{task.title}' executed. Status: {task.status}",
                execution_time_ms=elapsed_ms,
                cost_estimate=self._estimate_cost(final_state.get("token_usage", 0), agent.tier),
            )

            return {
                "task_id": task_id,
                "agent_id": agent.id,
                "agent_name": agent.name,
                "status": final_state.get("status", "completed"),
                "result": final_state.get("result"),
                "token_usage": final_state.get("token_usage", 0),
                "tool_calls": final_state.get("tool_call_count", 0),
                "artifacts": final_state.get("artifacts", []),
                "errors": final_state.get("errors", []),
                "execution_time_ms": round(elapsed_ms, 2),
            }

        except Exception as e:
            logger.error("task_execution_failed", task_id=task_id, error=str(e), exc_info=True)
            task.status = "failed"
            task.result_json = {"error": str(e)}
            await self.db.flush()

            await self.audit.log_action(
                agent_name=agent.name,
                department=task.department,
                action_type="task_execution_failed",
                details=f"Error: {str(e)}",
                execution_time_ms=(time.time() - start_time) * 1000,
            )

            return {
                "task_id": task_id,
                "status": "failed",
                "error": str(e),
            }

    async def chat_with_agent(
        self,
        agent_id: str,
        message: str,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a chat message to an agent and get a response.

        This creates a lightweight execution for conversational interactions
        without the full task management overhead.

        Args:
            agent_id: The agent to chat with.
            message: User message.
            thread_id: Optional conversation thread ID for continuity.

        Returns:
            Response dict with agent's reply and metadata.
        """
        agent = await self._get_agent(agent_id)
        if not agent:
            return {"error": f"Agent {agent_id} not found", "status": "failed"}

        import uuid
        thread = thread_id or str(uuid.uuid4())

        graph = build_global_graph()
        state = create_default_state(
            task_id=thread,
            task_description=message,
            department=agent.department,
            agent_id=agent.id,
            agent_name=agent.name,
            agent_tier=agent.tier,
        )

        try:
            config = {"configurable": {"thread_id": thread}}
            final_state = await graph.ainvoke(state, config=config)

            # Extract the last AI message as the response
            response_text = ""
            for msg in reversed(final_state.get("messages", [])):
                if hasattr(msg, "content") and msg.content:
                    response_text = msg.content
                    break

            await self.audit.log_action(
                agent_name=agent.name,
                department=agent.department,
                action_type="chat",
                details=f"Chat message: {message[:100]}...",
            )

            return {
                "agent_id": agent.id,
                "agent_name": agent.name,
                "thread_id": thread,
                "response": response_text,
                "status": final_state.get("status", "completed"),
            }

        except Exception as e:
            logger.error("chat_failed", agent_id=agent_id, error=str(e))
            return {"error": str(e), "status": "failed"}

    # ── Private Helpers ──────────────────────────

    async def _get_task(self, task_id: str) -> Task | None:
        """Load a task from the database."""
        result = await self.db.execute(select(Task).where(Task.id == task_id))
        return result.scalar_one_or_none()

    async def _get_agent(self, agent_id: str) -> Agent | None:
        """Load an agent from the database."""
        result = await self.db.execute(select(Agent).where(Agent.id == agent_id))
        return result.scalar_one_or_none()

    async def _get_or_assign_agent(
        self,
        agent_id: str | None,
        department: str,
    ) -> Agent | None:
        """Get a specific agent or auto-select one from the department.

        If agent_id is provided, fetches that agent. Otherwise, picks
        the first idle agent in the department.
        """
        if agent_id:
            return await self._get_agent(agent_id)

        # Auto-select: find first idle agent in department
        result = await self.db.execute(
            select(Agent)
            .where(Agent.department == department, Agent.status == "idle")
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _estimate_cost(tokens: int, tier: str) -> float:
        """Rough cost estimate based on token usage and model tier.

        These are approximate per-1K-token costs for estimation only.
        Actual costs come from LiteLLM's cost tracking.
        """
        cost_per_1k = {
            "nano": 0.00015,       # GPT-4o-mini
            "standard": 0.003,     # Claude 3.5 Sonnet
            "advanced": 0.015,     # Claude 3 Opus
            "code": 0.0002,        # DeepSeek Coder
            "vision": 0.005,       # GPT-4o
        }
        rate = cost_per_1k.get(tier, 0.003)
        return round((tokens / 1000) * rate, 6)
