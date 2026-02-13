"""
Supervisor Graphs — LangGraph-based agent orchestration.

Two-level hierarchy:
1. GlobalSupervisor: Routes tasks to the correct department
2. DepartmentSupervisor: Selects and runs the best agent within a department

Includes a RAG context retrieval node that injects relevant knowledge
before agent execution. Uses LangGraph StateGraph with MemorySaver
checkpointer for persistence and human-in-the-loop approval flows.
"""

import os
from typing import Any, Literal

import httpx
import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.agents.state import AgentState

logger = structlog.get_logger()

# Valid departments matching the enterprise structure
# Synced with actual agent departments in the database
DEPARTMENTS = [
    "tech",
    "finance",
    "hr",
    "sales",
    "marketing_digital",
    "legal",
    "business_dev",
    "development",  # legacy alias
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


async def agent_executor_node(state: AgentState) -> AgentState:
    """Agent execution node: calls LLM to process the task (with tools).

    Uses the agent's system prompt (from DB, injected via state) and the
    task description to generate an actual AI response via Google/OpenAI.
    Supports tool calling via ToolBroker for agents that have tools available.
    """
    logger.info(
        "agent_executor_node",
        agent=state.get("agent_name"),
        status=state["status"],
    )

    if state["status"] != "running":
        return state

    task_description = state.get("current_task", "")
    agent_name = state.get("agent_name", "AI Assistant")
    department = state.get("department", "general")
    agent_id = state.get("agent_id", "")

    # Build system prompt — prefer DB system prompt, fallback to generic
    db_prompt = state.get("system_prompt", "")
    if db_prompt:
        system_prompt = db_prompt
    else:
        system_prompt = (
            f"You are {agent_name}, an AI assistant in the {department} department. "
            f"You help with tasks related to {department}. "
            f"Provide detailed, actionable responses in the same language as the task. "
            f"If the task is in Indonesian, respond in Indonesian."
        )

    # Collect context from prior messages (RAG context etc.)
    context_parts: list[str] = []
    for msg in state.get("messages", []):
        if hasattr(msg, "content") and isinstance(msg, SystemMessage):
            context_parts.append(msg.content)
    if context_parts:
        system_prompt += "\n\nAdditional context:\n" + "\n".join(context_parts)

    # Get available tools from ToolBroker
    tools_for_llm: list[dict] = []
    broker = None
    agent_ctx = None
    try:
        from app.core.tool_broker import get_tool_broker
        from app.core.llm_client import AgentContext

        broker = get_tool_broker()
        agent_ctx = AgentContext(
            agent_id=agent_id,
            agent_name=agent_name,
            department=department,
            tier=state.get("agent_tier", "standard"),
            role="agent",
            task_id=state.get("task_id", ""),
        )
        tools_for_llm = broker.get_available_tools(role="agent", department=department)
        if tools_for_llm:
            logger.info("tools_loaded", agent=agent_name, count=len(tools_for_llm))
    except Exception as e:
        logger.warning("tools_load_failed", error=str(e))

    # Call LLM (with tool-call loop)
    try:
        response_text = await _call_llm_with_tools(
            system_prompt, task_description, tools_for_llm, broker, agent_ctx, state,
        )
        state["messages"] = [
            AIMessage(content=response_text)
        ]
        state["result"] = {
            "output": response_text,
            "agent": agent_name,
            "department": department,
            "tool_calls": state.get("tool_call_count", 0),
        }
        state["status"] = "completed"
        logger.info(
            "agent_executor_completed",
            agent=agent_name,
            response_len=len(response_text),
            tool_calls=state.get("tool_call_count", 0),
        )
    except Exception as e:
        logger.error("agent_executor_llm_failed", error=str(e))
        state["status"] = "failed"
        state["errors"] = state.get("errors", []) + [f"LLM call failed: {str(e)}"]
        state["result"] = {"error": str(e)}
        state["messages"] = [
            AIMessage(content=f"[AgentExecutor] Failed: {str(e)}")
        ]

    return state


async def _call_llm(system_prompt: str, user_content: str) -> str:
    """Call Google Gemini or OpenAI to generate a response.

    Tries Google first, falls back to OpenAI.
    """
    google_key = os.environ.get("GOOGLE_API_KEY", "")
    openai_key = os.environ.get("OPENAI_API_KEY", "")

    if google_key:
        return await _call_google(google_key, system_prompt, user_content)
    elif openai_key:
        return await _call_openai(openai_key, system_prompt, user_content)
    else:
        raise RuntimeError("No LLM API key configured (GOOGLE_API_KEY or OPENAI_API_KEY)")


async def _call_llm_with_tools(
    system_prompt: str,
    user_content: str,
    tools: list[dict],
    broker: "Any | None",
    agent_ctx: "Any | None",
    state: AgentState,
    max_iterations: int = 5,
) -> str:
    """Call LLM with tool-calling support.

    If tools are provided and Google API is available, uses Gemini function calling.
    Otherwise falls back to plain _call_llm.
    """
    from typing import Any as _Any

    google_key = os.environ.get("GOOGLE_API_KEY", "")

    # No tools or no broker or no Google key → plain call
    if not tools or not broker or not agent_ctx or not google_key:
        return await _call_llm(system_prompt, user_content)

    # Convert OpenAI-format tools to Gemini function declarations
    gemini_tools = []
    for t in tools:
        fn = t.get("function", {})
        params = fn.get("parameters", {"type": "object", "properties": {}})
        gemini_tools.append({
            "name": fn.get("name", ""),
            "description": fn.get("description", ""),
            "parameters": params,
        })

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={google_key}"

    # Build conversation history for the loop
    contents: list[dict] = [
        {"role": "user", "parts": [{"text": user_content}]}
    ]

    for iteration in range(max_iterations):
        payload: dict[str, _Any] = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": contents,
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 4096},
            "tools": [{"functionDeclarations": gemini_tools}],
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        candidate = data["candidates"][0]["content"]
        parts = candidate.get("parts", [])

        # Check if the response contains function calls
        function_calls = [p for p in parts if "functionCall" in p]

        if not function_calls:
            # Pure text response — extract and return
            text_parts = [p.get("text", "") for p in parts if "text" in p]
            return "\n".join(text_parts) or "(no response)"

        # Process function calls
        # Add model's response to conversation history
        contents.append({"role": "model", "parts": parts})

        # Execute each function call via ToolBroker
        function_responses: list[dict] = []
        for fc_part in function_calls:
            fc = fc_part["functionCall"]
            tool_name = fc.get("name", "")
            tool_args = fc.get("args", {})

            logger.info("tool_call_executing", tool=tool_name, args=tool_args, iteration=iteration)
            state["tool_call_count"] = state.get("tool_call_count", 0) + 1

            try:
                result = await broker.execute(agent_ctx, tool_name, tool_args)
                output = str(result.output) if result.output else "(no output)"
                function_responses.append({
                    "functionResponse": {
                        "name": tool_name,
                        "response": {"result": output},
                    }
                })
                logger.info("tool_call_success", tool=tool_name, output_len=len(output))
            except Exception as tool_err:
                error_msg = f"Tool error: {str(tool_err)}"
                function_responses.append({
                    "functionResponse": {
                        "name": tool_name,
                        "response": {"error": error_msg},
                    }
                })
                logger.warning("tool_call_failed", tool=tool_name, error=str(tool_err))

        # Add tool responses to conversation and loop back
        contents.append({"role": "user", "parts": function_responses})

    # Max iterations reached — return last available text
    return "(max tool iterations reached, no final response)"


async def _call_google(api_key: str, system_prompt: str, user_content: str) -> str:
    """Call Google Gemini API."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_content}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 4096},
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]


async def _call_openai(api_key: str, system_prompt: str, user_content: str) -> str:
    """Call OpenAI API."""
    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.7,
        "max_tokens": 4096,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


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
    system_prompt: str = "",
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
        system_prompt=system_prompt,
        status="pending",
        result=None,
    )
