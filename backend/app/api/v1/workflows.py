"""Workflow endpoints — execute LangGraph workflows via API."""

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.agents.workflows.finance_invoice import run_invoice_workflow

router = APIRouter(prefix="/workflows", tags=["workflows"])


# ── Request / Response models ─────────────────────


class InvoiceRequest(BaseModel):
    """Request to create and process a finance invoice."""

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "vendor": "Acme Corp",
            "amount": 150000.00,
            "description": "Cloud infrastructure services Q1 2026",
            "department": "tech",
            "requester": "user-001",
        }
    })

    vendor: str = Field(..., min_length=1, description="Vendor/supplier name")
    amount: float = Field(..., gt=0, description="Invoice amount in USD")
    description: str = Field(..., min_length=1, description="Description of goods/services")
    department: str = Field(..., min_length=1, description="Requesting department")
    requester: str = Field(..., min_length=1, description="User ID of the requester")


class InvoiceResponse(BaseModel):
    """Response from the invoice workflow."""

    trace_id: str
    status: str
    invoice_id: str = ""
    invoice_draft: dict = {}
    review_result: dict = {}
    approval_id: str = ""
    approval_status: str = ""
    error: str = ""
    audit_trail: list[str] = []


# ── Endpoints ─────────────────────────────────────


@router.post(
    "/invoice",
    response_model=InvoiceResponse,
    summary="Run Finance Invoice Workflow",
    description=(
        "Execute the full invoice workflow: Input → Draft → Review → Approval → Finalize. "
        "Demonstrates all control plane modules (M0-M7) working end-to-end."
    ),
)
async def create_invoice(req: InvoiceRequest) -> InvoiceResponse:
    """Execute the finance invoice workflow."""
    result = await run_invoice_workflow(
        vendor=req.vendor,
        amount=req.amount,
        description=req.description,
        department=req.department,
        requester=req.requester,
    )

    return InvoiceResponse(
        trace_id=result.get("trace_id", ""),
        status=result.get("status", "unknown"),
        invoice_id=result.get("invoice_id", ""),
        invoice_draft=result.get("invoice_draft", {}),
        review_result=result.get("review_result", {}),
        approval_id=result.get("approval_id", ""),
        approval_status=result.get("approval_status", ""),
        error=result.get("error", ""),
        audit_trail=result.get("audit_trail", []),
    )


@router.post(
    "/invoice/{approval_id}/approve",
    response_model=dict,
    summary="Approve a pending invoice",
)
async def approve_invoice(approval_id: str, approver_id: str = "admin") -> dict:
    """Grant approval for a pending invoice.

    After approval, the workflow can be re-invoked to complete finalization.
    """
    from app.core.approval_gate import ApprovalGate

    request = await ApprovalGate.grant(approval_id, approver_id)
    if request is None:
        return {"error": f"Approval {approval_id} not found"}

    return {
        "approval_id": approval_id,
        "status": request.status.value,
        "approved_by": approver_id,
    }


@router.post(
    "/invoice/{approval_id}/reject",
    response_model=dict,
    summary="Reject a pending invoice",
)
async def reject_invoice(
    approval_id: str,
    rejector_id: str = "admin",
    reason: str = "",
) -> dict:
    """Reject a pending invoice approval."""
    from app.core.approval_gate import ApprovalGate

    request = await ApprovalGate.reject(approval_id, rejector_id, reason)
    if request is None:
        return {"error": f"Approval {approval_id} not found"}

    return {
        "approval_id": approval_id,
        "status": request.status.value,
        "rejected_by": rejector_id,
        "reason": reason,
    }
