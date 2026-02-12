"""
Gateway API — Webhook endpoints for WhatsApp and Email inbound messages.

WhatsApp: POST /api/v1/gateway/whatsapp  (Twilio webhook)
Email:    POST /api/v1/gateway/email     (Gmail push notification)
"""

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse

import structlog

from app.services.orchestration.message_gateway import MessageGateway
from app.services.orchestration.task_orchestrator import TaskOrchestrator

logger = structlog.get_logger()

router = APIRouter(prefix="/gateway", tags=["gateway"])


@router.post("/whatsapp")
async def whatsapp_webhook(
    From: str = Form(""),
    Body: str = Form(""),
    ProfileName: str = Form(""),
    MessageSid: str = Form(""),
    NumMedia: str = Form("0"),
    WaId: str = Form(""),
    MediaUrl0: str = Form(""),
) -> JSONResponse:
    """Receive incoming WhatsApp message from Twilio webhook.

    Twilio sends form-encoded data with the message content.
    We normalize it and submit to the orchestrator.
    """
    payload = {
        "From": From,
        "Body": Body,
        "ProfileName": ProfileName,
        "MessageSid": MessageSid,
        "NumMedia": NumMedia,
        "WaId": WaId,
        "MediaUrl0": MediaUrl0,
    }

    message = MessageGateway.from_whatsapp(payload)

    # Check for approval replies
    body_lower = Body.strip().lower()
    if body_lower in ("approve", "approved", "setuju", "ya"):
        # TODO: Find pending approval for this sender and approve
        logger.info("whatsapp_approval_reply", sender=From, decision="approved")
        return JSONResponse(
            content={"status": "approval_processed", "decision": "approved"},
            status_code=200,
        )
    elif body_lower in ("reject", "rejected", "tolak", "tidak"):
        logger.info("whatsapp_approval_reply", sender=From, decision="rejected")
        return JSONResponse(
            content={"status": "approval_processed", "decision": "rejected"},
            status_code=200,
        )

    # Submit as new task
    task = await TaskOrchestrator.submit(message)

    return JSONResponse(
        content={
            "status": "received",
            "task_id": task.task_id,
            "trace_id": task.trace_id,
            "agent": task.routing.agent,
        },
        status_code=200,
    )


@router.post("/email")
async def email_webhook(request: Request) -> JSONResponse:
    """Receive incoming email notification.

    Accepts a parsed email payload (from Gmail push or IMAP poller).
    """
    payload = await request.json()
    message = MessageGateway.from_email(payload)

    # Submit as new task
    task = await TaskOrchestrator.submit(message)

    return JSONResponse(
        content={
            "status": "received",
            "task_id": task.task_id,
            "trace_id": task.trace_id,
            "agent": task.routing.agent,
        },
        status_code=200,
    )


@router.get("/status/{task_id}")
async def get_task_status(task_id: str) -> JSONResponse:
    """Get the status of an orchestrated task."""
    task = TaskOrchestrator.get_task(task_id)
    if not task:
        return JSONResponse(content={"error": "Task not found"}, status_code=404)

    return JSONResponse(
        content={
            "task_id": task.task_id,
            "trace_id": task.trace_id,
            "status": task.status.value,
            "agent": task.routing.agent,
            "department": task.routing.department,
            "response": task.agent_response,
            "error": task.error,
        },
        status_code=200,
    )
