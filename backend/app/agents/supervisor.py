"""
Supervisor Graphs — LangGraph-based agent orchestration.

Two-level hierarchy:
1. GlobalSupervisor: Routes tasks to the correct department
2. DepartmentSupervisor: Selects and runs the best agent within a department

Includes a RAG context retrieval node that injects relevant knowledge
before agent execution. Uses LangGraph StateGraph with MemorySaver
checkpointer for persistence and human-in-the-loop approval flows.
"""

from typing import Any, Literal

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.agents.state import AgentState

logger = structlog.get_logger()

# Valid departments matching the enterprise structure
DEPARTMENTS = [
    "development",
    "finance",
    "hr",
    "sales",
    "marketing",
    "legal",
    "business_dev",
]


# ── Node Functions ───────────────────────────────


def route_to_department(state: AgentState) -> AgentState:
    """GlobalSupervisor node: validate and prepare routing.

    Examines the task's department field and prepares state for
    the department supervisor. If department is invalid, marks task as failed.
    """
    department = state.get("department", "")
    logger.info("global_supervisor_routing", department=department, task=state["current_task"])

    if department not in DEPARTMENTS:
        state["status"] = "failed"
        state["errors"] = state.get("errors", []) + [
            f"Unknown department: '{department}'. Valid: {DEPARTMENTS}"
        ]
        state["result"] = {"error": f"Unknown department: {department}"}
        return state

    # Add routing message to conversation
    state["messages"] = [
        AIMessage(
            content=f"[GlobalSupervisor] Routing task to {department} department. "
            f"Task: {state['current_task']}"
        )
    ]
    return state


def department_supervisor(state: AgentState) -> AgentState:
    """DepartmentSupervisor node: select agent and prepare execution.

    In the full implementation, this would:
    1. Query the DB for available agents in this department
    2. Select the best agent based on task type and agent capabilities
    3. Invoke the agent's LangGraph subgraph

    For now, it prepares the state for the agent executor.
    """
    department = state["department"]
    agent_name = state.get("agent_name", "unknown")

    logger.info(
        "department_supervisor",
        department=department,
        agent=agent_name,
        task=state["current_task"],
    )

    state["messages"] = [
        AIMessage(
            content=f"[{department.title()}Supervisor] Assigned to agent '{agent_name}'. "
            f"Executing task: {state['current_task']}"
        )
    ]
    state["status"] = "running"
    return state


def retrieve_context(state: AgentState) -> AgentState:
    """RAG context retrieval node: queries knowledge base for relevant context.

    Runs between department_supervisor and agent_executor. Injects
    relevant knowledge documents as a SystemMessage so the agent
    has domain context before processing.

    NOTE: This is a synchronous wrapper. The actual async retrieval
    happens in AgentExecutorService which can inject context directly.
    This node acts as a placeholder for the graph structure and can
    be enhanced when the full async pipeline is integrated.
    """
    department = state["department"]
    task = state.get("current_task", "")

    logger.info(
        "retrieve_context",
        department=department,
        task=task[:100],
    )

    # Context injection message (actual RAG retrieval is done
    # by AgentExecutorService before graph invocation)
    state["messages"] = [
        SystemMessage(
            content=f"[KnowledgeBase] Context retrieval prepared for department '{department}'."
        )
    ]
    return state


def agent_executor_node(state: AgentState) -> AgentState:
    """Agent execution node: placeholder for actual agent processing.

    In the full flow, the AgentExecutorService injects the real agent's
    `process()` method here. This node is replaced at runtime.
    """
    logger.info(
        "agent_executor_node",
        agent=state.get("agent_name"),
        status=state["status"],
    )

    # Default behavior: mark as needing actual agent implementation
    if state["status"] == "running":
        state["messages"] = [
            AIMessage(
                content=f"[AgentExecutor] Agent '{state.get('agent_name')}' processing complete."
            )
        ]
        state["status"] = "completed"

    return state


def check_approval(state: AgentState) -> AgentState:
    """Check if the task requires human approval before continuing.

    High-risk actions (cost > threshold, sensitive data access) trigger
    an approval checkpoint. The graph pauses here until a human approves.
    """
    logger.info("checking_approval", status=state["status"])

    if state.get("human_feedback") == "rejected":
        state["status"] = "failed"
        state["errors"] = state.get("errors", []) + ["Task rejected by human reviewer"]
        state["messages"] = [
            AIMessage(content="[Approval] Task rejected by human reviewer.")
        ]

    return state


def finalize(state: AgentState) -> AgentState:
    """Final node: prepare the execution result."""
    logger.info(
        "finalizing",
        status=state["status"],
        tool_calls=state["tool_call_count"],
        tokens=state["token_usage"],
    )

    if state["status"] not in ("completed", "failed"):
        state["status"] = "completed"

    if state.get("result") is None:
        state["result"] = {
            "status": state["status"],
            "agent": state.get("agent_name"),
            "department": state["department"],
            "tool_calls": state["tool_call_count"],
            "tokens_used": state["token_usage"],
            "artifacts": state.get("artifacts", []),
            "errors": state.get("errors", []),
        }

    return state


# ── Routing Logic ────────────────────────────────


def should_continue_after_routing(state: AgentState) -> Literal["department_supervisor", "finalize"]:
    """After global routing, check if we should proceed or abort."""
    if state["status"] == "failed":
        return "finalize"
    return "department_supervisor"


def should_check_approval(state: AgentState) -> Literal["check_approval", "finalize"]:
    """After agent execution, check if approval is needed."""
    if state["status"] == "waiting_approval":
        return "check_approval"
    return "finalize"


def after_approval(state: AgentState) -> Literal["agent_executor", "finalize"]:
    """After approval check, either continue or finalize."""
    if state["status"] == "failed":
        return "finalize"
    if state.get("human_feedback") == "approved":
        return "agent_executor"
    return "finalize"


# ── Graph Builders ───────────────────────────────


def build_global_graph(checkpointer: Any | None = None) -> StateGraph:
    """Build the full agent execution graph.

    Graph flow:
        route_to_department → department_supervisor → retrieve_context
        → agent_executor → [check_approval?] → finalize → END

    Args:
        checkpointer: LangGraph checkpointer for persistence.
                      Defaults to MemorySaver if None.

    Returns:
        Compiled StateGraph ready for invocation.
    """
    if checkpointer is None:
        checkpointer = MemorySaver()

    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("route_to_department", route_to_department)
    graph.add_node("department_supervisor", department_supervisor)
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("agent_executor", agent_executor_node)
    graph.add_node("check_approval", check_approval)
    graph.add_node("finalize", finalize)

    # Set entry point
    graph.set_entry_point("route_to_department")

    # Add edges with conditional routing
    graph.add_conditional_edges(
        "route_to_department",
        should_continue_after_routing,
        {
            "department_supervisor": "department_supervisor",
            "finalize": "finalize",
        },
    )
    graph.add_edge("department_supervisor", "retrieve_context")
    graph.add_edge("retrieve_context", "agent_executor")
    graph.add_conditional_edges(
        "agent_executor",
        should_check_approval,
        {
            "check_approval": "check_approval",
            "finalize": "finalize",
        },
    )
    graph.add_conditional_edges(
        "check_approval",
        after_approval,
        {
            "agent_executor": "agent_executor",
            "finalize": "finalize",
        },
    )
    graph.add_edge("finalize", END)

    return graph.compile(checkpointer=checkpointer)


def create_default_state(
    task_id: str,
    task_description: str,
    department: str,
    agent_id: str = "",
    agent_name: str = "",
    agent_tier: str = "standard",
    max_tool_calls: int = 50,
    max_tokens: int = 100_000,
) -> AgentState:
    """Create a default AgentState for a new execution.

    Args:
        task_id: Database task ID.
        task_description: Human-readable task description.
        department: Target department.
        agent_id: Specific agent ID (optional, auto-selected if empty).
        agent_name: Agent display name.
        agent_tier: Model tier for LLM routing.
        max_tool_calls: Tool call limit.
        max_tokens: Token budget.

    Returns:
        Initialized AgentState ready for graph invocation.
    """
    return AgentState(
        messages=[HumanMessage(content=task_description)],
        current_task=task_description,
        task_id=task_id,
        department=department,
        agent_id=agent_id,
        agent_name=agent_name,
        agent_tier=agent_tier,
        artifacts=[],
        errors=[],
        tool_call_count=0,
        token_usage=0,
        max_tool_calls=max_tool_calls,
        max_tokens=max_tokens,
        human_feedback=None,
        status="pending",
        result=None,
    )
