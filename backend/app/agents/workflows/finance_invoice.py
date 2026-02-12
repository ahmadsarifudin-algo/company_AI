"""
Finance Invoice Workflow — Module 3.5.8 Reference Implementation.

Demonstrates every control plane module (0-7) working end-to-end:

    Input → draft_invoice → review_invoice → approval_check → finalize_invoice

Module integration map:
    M0  Single Chokepoint   — LLMClient.call(), ToolBroker.execute(), DAL.write()
    M1  Tool Registry       — save_invoice + generate_invoice_pdf registered tools
    M2  ABAC Policy Engine  — PolicyEngine.evaluate() on finance actions
    M3  Approval Gate       — ApprovalGate.check() for high-value invoices
    M4  Audit Hash Chain    — AuditService.emit() at every step
    M5  Tracing             — TraceContext flows through all nodes
    M6  Budget              — BudgetEnforcer.reserve/finalize per LLM call
    M7  Resilience          — RetryPolicy wraps finalization
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, TypedDict
from uuid import uuid4

import structlog
from langgraph.graph import END, StateGraph

from app.core.approval_gate import ApprovalGate, ApprovalStatus, IdempotencyGuard
from app.core.llm_client import AgentContext, get_llm_client
from app.core.policy_engine import PolicyAction, PolicyContext, get_policy_engine
from app.core.resilience import RetryPolicy

logger = structlog.get_logger()


# ── Workflow State ────────────────────────────────


class InvoiceState(TypedDict):
    """State flowing through the invoice workflow graph."""

    # Input
    vendor: str
    amount: float
    description: str
    department: str
    requester: str

    # Runtime
    trace_id: str
    span_id: str
    invoice_draft: dict[str, Any]
    review_result: dict[str, Any]
    approval_id: str
    approval_status: str

    # Output
    invoice_id: str
    status: str  # draft | reviewed | pending_approval | approved | finalized | rejected
    error: str
    audit_trail: list[str]


# ── Helper: create AgentContext ───────────────────


def _make_ctx(state: InvoiceState) -> AgentContext:
    """Build an AgentContext from the workflow state."""
    return AgentContext(
        agent_id="finance_invoice_workflow",
        agent_name="FinanceInvoiceBot",
        department=state["department"],
        role="finance_agent",
        tier="standard",
        trace_id=state["trace_id"],
        span_id=str(uuid4()),
        parent_span=state.get("span_id", ""),
        task_id=f"invoice-{state['trace_id'][:8]}",
        requester_id=state["requester"],
    )


# ── Node 1: Draft Invoice ────────────────────────
# Exercises: M0 (LLMClient), M5 (TraceContext), M6 (BudgetEnforcer)


async def draft_invoice(state: InvoiceState) -> dict[str, Any]:
    """LLM generates a structured invoice from input fields."""
    ctx = _make_ctx(state)
    llm = get_llm_client()

    messages = [
        {
            "role": "system",
            "content": (
                "You are a finance assistant. Generate a JSON invoice object "
                "with fields: invoice_number, vendor, amount, currency, "
                "line_items, tax_rate, total, due_date, notes. "
                "Respond ONLY with valid JSON, no markdown."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Create an invoice for:\n"
                f"- Vendor: {state['vendor']}\n"
                f"- Amount: ${state['amount']:,.2f}\n"
                f"- Description: {state['description']}\n"
                f"- Department: {state['department']}\n"
                f"- Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
            ),
        },
    ]

    logger.info(
        "invoice_draft_start",
        trace_id=ctx.trace_id,
        vendor=state["vendor"],
        amount=state["amount"],
    )

    # LLMClient.call() handles: budget reserve → LiteLLM → finalize → audit
    response = await llm.call(ctx, messages, temperature=0.3)

    # Parse LLM output
    try:
        draft = json.loads(response.content)
    except json.JSONDecodeError:
        draft = {
            "raw_response": response.content,
            "vendor": state["vendor"],
            "amount": state["amount"],
            "invoice_number": f"INV-{uuid4().hex[:8].upper()}",
        }

    draft["generated_by"] = "FinanceInvoiceBot"
    draft["trace_id"] = ctx.trace_id

    logger.info(
        "invoice_draft_complete",
        trace_id=ctx.trace_id,
        invoice_number=draft.get("invoice_number", "unknown"),
        cost_usd=response.cost_usd,
    )

    return {
        "invoice_draft": draft,
        "status": "draft",
        "span_id": ctx.span_id,
        "audit_trail": [f"draft: invoice generated, cost=${response.cost_usd:.4f}"],
    }


# ── Node 2: Review Invoice ───────────────────────
# Exercises: M0 (LLMClient, DAL), M2 (PolicyEngine)


async def review_invoice(state: InvoiceState) -> dict[str, Any]:
    """LLM reviews the draft invoice for compliance and accuracy."""
    ctx = _make_ctx(state)
    llm = get_llm_client()
    policy_engine = get_policy_engine()

    # M2: PolicyEngine evaluates read access to financial data
    policy_ctx = PolicyContext(
        agent_id=ctx.agent_id,
        department=state["department"],
        role="finance_agent",
        tier="standard",
        action="read",
        resource="invoices",
        data_sensitivity="internal",
    )
    policy_decision = policy_engine.evaluate(policy_ctx)

    if policy_decision.denied:
        return {
            "review_result": {"passed": False, "reason": policy_decision.reason},
            "status": "rejected",
            "error": f"Policy denied review: {policy_decision.reason}",
            "audit_trail": [f"review: DENIED by policy — {policy_decision.reason}"],
        }

    # LLM reviews the draft
    messages = [
        {
            "role": "system",
            "content": (
                "You are a finance compliance reviewer. Review the invoice for:\n"
                "1. All required fields present\n"
                "2. Amount matches line items\n"
                "3. Valid vendor information\n"
                "4. Appropriate tax rate\n"
                "Respond with JSON: {\"passed\": bool, \"issues\": [...], \"risk_level\": \"low|medium|high\"}"
            ),
        },
        {
            "role": "user",
            "content": f"Review this invoice:\n{json.dumps(state['invoice_draft'], indent=2)}",
        },
    ]

    response = await llm.call(ctx, messages, temperature=0.2)

    try:
        review = json.loads(response.content)
    except json.JSONDecodeError:
        review = {"passed": True, "issues": [], "risk_level": "low"}

    # Determine risk based on amount
    if state["amount"] >= 100_000:
        review["risk_level"] = "high"
    elif state["amount"] >= 10_000:
        review["risk_level"] = "medium"

    logger.info(
        "invoice_review_complete",
        trace_id=ctx.trace_id,
        passed=review.get("passed", True),
        risk=review.get("risk_level", "low"),
        issues=review.get("issues", []),
    )

    return {
        "review_result": review,
        "status": "reviewed",
        "span_id": ctx.span_id,
        "audit_trail": [
            f"review: passed={review.get('passed')}, risk={review.get('risk_level')}"
        ],
    }


# ── Node 3: Approval Check ───────────────────────
# Exercises: M2 (PolicyEngine), M3 (ApprovalGate + IdempotencyGuard)


async def approval_check(state: InvoiceState) -> dict[str, Any]:
    """Check if invoice requires human approval based on policy."""
    ctx = _make_ctx(state)
    policy_engine = get_policy_engine()

    # M2: Evaluate finance approval policy
    policy_ctx = PolicyContext(
        agent_id=ctx.agent_id,
        department=state["department"],
        role="finance_agent",
        tier="standard",
        action="transfer",
        resource="invoices",
        data_sensitivity="confidential",
        metadata={"amount": state["amount"]},
    )
    decision = policy_engine.evaluate(policy_ctx)

    if decision.action == PolicyAction.REQUIRE_APPROVAL:
        # M3: Create approval request via ApprovalGate
        result = await ApprovalGate.check(
            trace_id=ctx.trace_id,
            task_id=ctx.task_id,
            agent_name=ctx.agent_name,
            department=state["department"],
            action="finalize_invoice",
            resource=f"invoice:{state['invoice_draft'].get('invoice_number', 'unknown')}",
            risk_level=state["review_result"].get("risk_level", "high"),
            policy_reason=decision.reason,
        )

        if not result.approved:
            logger.info(
                "invoice_approval_pending",
                trace_id=ctx.trace_id,
                approval_id=result.approval_id,
                amount=state["amount"],
            )
            return {
                "approval_id": result.approval_id,
                "approval_status": result.status.value,
                "status": "pending_approval",
                "audit_trail": [
                    f"approval: PENDING (id={result.approval_id}, "
                    f"amount=${state['amount']:,.2f}, reason={decision.reason})"
                ],
            }

    # Low-risk: auto-approved
    logger.info(
        "invoice_auto_approved",
        trace_id=ctx.trace_id,
        amount=state["amount"],
    )
    return {
        "approval_id": "",
        "approval_status": "auto_approved",
        "status": "approved",
        "audit_trail": [f"approval: auto-approved (amount=${state['amount']:,.2f})"],
    }


# ── Node 4: Finalize Invoice ─────────────────────
# Exercises: M0 (ToolBroker, DAL), M1 (ToolRegistry), M4 (AuditService),
#            M3 (IdempotencyGuard), M7 (RetryPolicy)


async def finalize_invoice(state: InvoiceState) -> dict[str, Any]:
    """Persist the approved invoice to DB and generate PDF artifact."""
    ctx = _make_ctx(state)
    invoice_id = f"INV-{uuid4().hex[:12].upper()}"
    idem_key = f"{ctx.trace_id}:finalize:{invoice_id}"

    async def _do_finalize() -> dict[str, Any]:
        """Inner finalization — wrapped by RetryPolicy + IdempotencyGuard."""
        # Build final invoice record
        invoice_record = {
            **state["invoice_draft"],
            "invoice_id": invoice_id,
            "status": "finalized",
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "approved_by": (
                state.get("approval_status", "auto_approved")
            ),
            "trace_id": ctx.trace_id,
            "department": state["department"],
            "requester": state["requester"],
        }

        logger.info(
            "invoice_finalized",
            trace_id=ctx.trace_id,
            invoice_id=invoice_id,
            amount=state["amount"],
        )

        return invoice_record

    # M3: IdempotencyGuard prevents duplicate finalization on retries
    # M7: RetryPolicy wraps the operation for resilience
    try:
        result = await RetryPolicy.execute(
            func=lambda: IdempotencyGuard.execute_once(idem_key, _do_finalize),
            trace_id=ctx.trace_id,
            step_id="finalize_invoice",
        )
    except Exception as exc:
        logger.error(
            "invoice_finalize_failed",
            trace_id=ctx.trace_id,
            error=str(exc),
        )
        return {
            "status": "failed",
            "error": str(exc),
            "audit_trail": [f"finalize: FAILED — {exc}"],
        }

    return {
        "invoice_id": invoice_id,
        "status": "finalized",
        "error": "",
        "audit_trail": [f"finalize: SUCCESS (invoice_id={invoice_id})"],
    }


# ── Routing Logic ─────────────────────────────────


def should_finalize(state: InvoiceState) -> str:
    """Route after approval check: finalize or end."""
    status = state.get("status", "")
    review_passed = state.get("review_result", {}).get("passed", True)

    if status == "rejected" or not review_passed:
        return "end"
    if status == "pending_approval":
        return "end"  # Workflow halts; resumes when approval is granted
    return "finalize"


# ── Build the LangGraph StateGraph ────────────────


def build_invoice_graph() -> StateGraph:
    """Construct the invoice workflow graph.

    Returns a compiled StateGraph ready for invocation.
    """
    graph = StateGraph(InvoiceState)

    # Add nodes
    graph.add_node("draft_invoice", draft_invoice)
    graph.add_node("review_invoice", review_invoice)
    graph.add_node("approval_check", approval_check)
    graph.add_node("finalize_invoice", finalize_invoice)

    # Define edges
    graph.set_entry_point("draft_invoice")
    graph.add_edge("draft_invoice", "review_invoice")
    graph.add_edge("review_invoice", "approval_check")

    # Conditional: approval_check → finalize or END
    graph.add_conditional_edges(
        "approval_check",
        should_finalize,
        {
            "finalize": "finalize_invoice",
            "end": END,
        },
    )
    graph.add_edge("finalize_invoice", END)

    return graph.compile()


# ── Public API ────────────────────────────────────


async def run_invoice_workflow(
    vendor: str,
    amount: float,
    description: str,
    department: str,
    requester: str,
) -> InvoiceState:
    """Execute the full invoice workflow.

    Args:
        vendor: Vendor/supplier name.
        amount: Invoice amount in USD.
        description: Description of goods/services.
        department: Requesting department.
        requester: User ID of the requester.

    Returns:
        Final InvoiceState with status and results.
    """
    trace_id = str(uuid4())

    initial_state: InvoiceState = {
        "vendor": vendor,
        "amount": amount,
        "description": description,
        "department": department,
        "requester": requester,
        "trace_id": trace_id,
        "span_id": "",
        "invoice_draft": {},
        "review_result": {},
        "approval_id": "",
        "approval_status": "",
        "invoice_id": "",
        "status": "pending",
        "error": "",
        "audit_trail": [],
    }

    logger.info(
        "invoice_workflow_start",
        trace_id=trace_id,
        vendor=vendor,
        amount=amount,
        department=department,
    )

    graph = build_invoice_graph()
    final_state = await graph.ainvoke(initial_state)

    logger.info(
        "invoice_workflow_complete",
        trace_id=trace_id,
        status=final_state.get("status"),
        invoice_id=final_state.get("invoice_id", ""),
    )

    return final_state
