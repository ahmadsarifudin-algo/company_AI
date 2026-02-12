"""
Gateway API — Webhook endpoints for WhatsApp, Telegram, and Email inbound messages.

WhatsApp:  POST /api/v1/gateway/whatsapp   (Twilio webhook)
Telegram:  POST /api/v1/gateway/telegram   (Bot API webhook)
Email:     POST /api/v1/gateway/email      (Gmail push notification)
"""

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse

import structlog

from app.services.orchestration.message_gateway import MessageGateway, UnifiedMessage
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
        from app.core.approval_gate import ApprovalGate
        pending = await ApprovalGate.get_pending_for_sender(From)
        if pending:
            await ApprovalGate.grant(pending.approval_id, From)
            logger.info("whatsapp_approval_granted", sender=From, approval_id=pending.approval_id)
            # Trigger resume
            import asyncio
            asyncio.create_task(_resume_approved_tool(pending))
            return JSONResponse(
                content={"status": "approval_processed", "decision": "approved", "approval_id": pending.approval_id},
                status_code=200,
            )
        logger.info("whatsapp_approval_reply_no_pending", sender=From)
        return JSONResponse(
            content={"status": "no_pending_approval"},
            status_code=200,
        )
    elif body_lower in ("reject", "rejected", "tolak", "tidak"):
        from app.core.approval_gate import ApprovalGate
        pending = await ApprovalGate.get_pending_for_sender(From)
        if pending:
            await ApprovalGate.reject(pending.approval_id, From, "Rejected via WhatsApp")
            logger.info("whatsapp_approval_rejected", sender=From, approval_id=pending.approval_id)
            return JSONResponse(
                content={"status": "approval_processed", "decision": "rejected", "approval_id": pending.approval_id},
                status_code=200,
            )
        return JSONResponse(
            content={"status": "no_pending_approval"},
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


@router.post("/telegram")
async def telegram_webhook(request: Request) -> JSONResponse:
    """Receive incoming Telegram message via Bot API webhook.

    Telegram sends a JSON Update object with the message content.
    ACKs immediately (< 1s) and processes in background to avoid
    Telegram's webhook timeout (60s limit, but LLM can take 10-30s).
    """
    import asyncio

    payload = await request.json()

    # Telegram webhook verification — ignore non-message updates
    if "message" not in payload:
        return JSONResponse(content={"status": "ignored"}, status_code=200)

    message = MessageGateway.from_telegram(payload)

    # Check for approval replies (fast path — no LLM needed)
    body_lower = message.content.strip().lower()
    if body_lower in ("approve", "approved", "setuju", "ya"):
        from app.core.approval_gate import ApprovalGate
        pending = await ApprovalGate.get_pending_for_sender(message.sender)
        if pending:
            await ApprovalGate.grant(pending.approval_id, message.sender)
            logger.info("telegram_approval_granted", sender=message.sender, approval_id=pending.approval_id)
            # Trigger resume
            import asyncio
            asyncio.create_task(_resume_approved_tool(pending))
            return JSONResponse(
                content={"status": "approval_processed", "decision": "approved", "approval_id": pending.approval_id},
                status_code=200,
            )
        logger.info("telegram_approval_reply_no_pending", sender=message.sender)
        return JSONResponse(
            content={"status": "no_pending_approval"},
            status_code=200,
        )
    elif body_lower in ("reject", "rejected", "tolak", "tidak"):
        from app.core.approval_gate import ApprovalGate
        pending = await ApprovalGate.get_pending_for_sender(message.sender)
        if pending:
            await ApprovalGate.reject(pending.approval_id, message.sender, "Rejected via Telegram")
            logger.info("telegram_approval_rejected", sender=message.sender, approval_id=pending.approval_id)
            return JSONResponse(
                content={"status": "approval_processed", "decision": "rejected", "approval_id": pending.approval_id},
                status_code=200,
            )
        return JSONResponse(
            content={"status": "no_pending_approval"},
            status_code=200,
        )

    # Fire-and-forget: ACK Telegram immediately, process in background
    asyncio.create_task(_process_telegram_message(message))

    return JSONResponse(content={"status": "accepted"}, status_code=200)


async def _process_telegram_message(message: UnifiedMessage) -> None:
    """Background task: run orchestrator and handle errors gracefully."""
    try:
        task = await TaskOrchestrator.submit(message)
        logger.info(
            "telegram_webhook_completed",
            task_id=task.task_id,
            trace_id=task.trace_id,
            agent=task.routing.agent,
            status=task.status.value,
        )
    except Exception as e:
        logger.error(
            "telegram_webhook_background_error",
            sender=message.sender,
            error=str(e),
        )
        # Try to send fallback error reply directly
        try:
            from app.services.orchestration.notification_dispatcher import (
                NotificationDispatcher,
            )

            await NotificationDispatcher.send(
                channel="telegram",
                recipient=message.sender,
                content="⚠️ Sorry, something went wrong processing your message. Please try again.",
            )
        except Exception:
            pass  # Last resort — can't do anything more


async def _resume_approved_tool(approval_request) -> None:
    """Resume tool execution after approval is granted.

    Executes the approved tool via ToolBroker and sends the result
    back to the user via the original channel.

    Args:
        approval_request: The ApprovalRequest with tool context.
    """
    import json

    from app.core.approval_gate import ApprovalRequest
    from app.services.orchestration.notification_dispatcher import NotificationDispatcher

    req: ApprovalRequest = approval_request

    if not req.tool_name:
        logger.info(
            "resume_skip_no_tool",
            approval_id=req.approval_id,
        )
        return

    try:
        # Execute the tool via ToolBroker
        from app.core.llm_client import AgentContext
        from app.core.tool_broker import get_tool_broker

        broker = get_tool_broker()
        tool_args = json.loads(req.tool_args) if req.tool_args else {}

        ctx = AgentContext(
            agent_id=req.agent_name,
            agent_name=req.agent_name,
            department=req.department,
            role="agent",
            tier="standard",
            trace_id=req.trace_id,
            span_id="",
            parent_span="",
            task_id=req.task_id,
            requester_id=req.sender,
        )

        result = await broker.execute(ctx, req.tool_name, tool_args)

        # Send result back to user
        if result.success:
            reply = f"✅ Tool '{req.tool_name}' approved and executed.\n\nResult: {str(result.output)[:500]}"
        else:
            reply = f"❌ Tool '{req.tool_name}' was approved but failed: {result.error}"

        if req.channel and req.sender:
            await NotificationDispatcher.send(
                channel=req.channel,
                recipient=req.chat_id or req.sender,
                content=reply,
                trace_id=req.trace_id,
            )

        logger.info(
            "approval_resume_completed",
            approval_id=req.approval_id,
            tool=req.tool_name,
            success=result.success,
        )

    except Exception as e:
        logger.error(
            "approval_resume_failed",
            approval_id=req.approval_id,
            tool=req.tool_name,
            error=str(e),
        )
        # Try to notify user of failure
        try:
            from app.services.orchestration.notification_dispatcher import NotificationDispatcher
            if req.channel and req.sender:
                await NotificationDispatcher.send(
                    channel=req.channel,
                    recipient=req.chat_id or req.sender,
                    content=f"⚠️ Approved tool '{req.tool_name}' failed to execute: {str(e)[:200]}",
                    trace_id=req.trace_id,
                )
        except Exception:
            pass


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
