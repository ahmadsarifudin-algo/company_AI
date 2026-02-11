"""
Agent State — LangGraph state definition for agent execution.

This TypedDict drives the entire agent workflow graph. Each node reads
and writes to these fields as the task progresses through the pipeline.
"""

import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage


class AgentState(TypedDict):
    """State that flows through the LangGraph agent execution graph.

    Fields:
        messages: Accumulated LLM conversation messages (append-only via operator.add).
        current_task: Description of the task being executed.
        task_id: Database task ID for status tracking.
        department: Department scope for RLS and routing.
        agent_id: The specific agent executing the task.
        agent_name: Human-readable agent name for audit logging.
        agent_tier: Model tier (nano, standard, advanced, code).
        artifacts: List of generated artifact references (file paths, URLs).
        errors: List of error messages encountered during execution.
        tool_call_count: Running count of tool invocations (for rate limiting).
        token_usage: Running count of tokens consumed (for budget tracking).
        max_tool_calls: Configurable limit on tool calls per task.
        max_tokens: Configurable token budget per task.
        human_feedback: Set when a human provides approval/rejection at a checkpoint.
        status: Current execution status.
        result: Final output of the agent execution.
    """

    messages: Annotated[list[AnyMessage], operator.add]
    current_task: str
    task_id: str
    department: str
    agent_id: str
    agent_name: str
    agent_tier: str
    artifacts: list[str]
    errors: list[str]
    tool_call_count: int
    token_usage: int
    max_tool_calls: int
    max_tokens: int
    human_feedback: str | None
    status: str  # "pending" | "running" | "waiting_approval" | "completed" | "failed"
    result: dict[str, Any] | None
