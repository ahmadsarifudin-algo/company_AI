"""
Email Tool — Send emails via Gmail API or SMTP.

Registered as `send_email` in the ToolRegistry.
Risk: HIGH — requires human approval before sending.
"""

from typing import Any

import structlog

from app.services.orchestration.credential_vault import CredentialVault

logger = structlog.get_logger()


async def send_email_handler(
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
    attachments: list[str] | None = None,
    html: bool = False,
) -> dict[str, Any]:
    """Send an email via Gmail API or SMTP fallback.

    Args:
        to: Recipient email address.
        subject: Email subject.
        body: Email body text.
        cc: CC recipients (comma-separated).
        bcc: BCC recipients (comma-separated).
        attachments: List of file paths to attach.
        html: If True, body is HTML.

    Returns:
        Dict with status, message_id, and delivery info.
    """
    # Validate allowed domains
    allowed_domains = CredentialVault.get("allowed_email_domains", "")
    if allowed_domains:
        domain = to.split("@")[-1] if "@" in to else ""
        allowed = [d.strip() for d in allowed_domains.split(",") if d.strip()]
        if allowed and domain not in allowed:
            return {
                "status": "denied",
                "error": f"Domain @{domain} not in allowed list: {allowed}",
            }

    # Try Gmail API first
    if CredentialVault.is_configured("google_gmail"):
        return await _send_via_gmail(to, subject, body, cc, bcc, attachments, html)

    # Fallback to SMTP
    if CredentialVault.is_configured("smtp"):
        return await _send_via_smtp(to, subject, body, cc, html)

    return {"status": "error", "error": "No email service configured"}


async def _send_via_gmail(
    to: str, subject: str, body: str,
    cc: str, bcc: str, attachments: list[str] | None, html: bool,
) -> dict:
    """Send email using Gmail API with service account delegation."""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        import base64
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        creds_dict = CredentialVault.get_google_credentials()
        delegated_email = CredentialVault.get("google_delegated_email")

        credentials = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=["https://www.googleapis.com/auth/gmail.send"],
            subject=delegated_email,
        )
        service = build("gmail", "v1", credentials=credentials)

        if attachments:
            msg = MIMEMultipart()
            msg.attach(MIMEText(body, "html" if html else "plain"))
            # TODO: Add file attachments
        else:
            msg = MIMEText(body, "html" if html else "plain")

        msg["to"] = to
        msg["from"] = delegated_email
        msg["subject"] = subject
        if cc:
            msg["cc"] = cc
        if bcc:
            msg["bcc"] = bcc

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        result = service.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()

        logger.info("email_sent_gmail", to=to, message_id=result.get("id"))
        return {"status": "sent", "message_id": result.get("id", ""), "method": "gmail"}

    except ImportError:
        return {"status": "error", "error": "google-api-python-client not installed"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def _send_via_smtp(
    to: str, subject: str, body: str, cc: str, html: bool,
) -> dict:
    """Send email using SMTP."""
    try:
        import aiosmtplib
        from email.mime.text import MIMEText

        msg = MIMEText(body, "html" if html else "plain")
        msg["Subject"] = subject
        msg["From"] = CredentialVault.get("smtp_from")
        msg["To"] = to
        if cc:
            msg["Cc"] = cc

        await aiosmtplib.send(
            msg,
            hostname=CredentialVault.get("smtp_host"),
            port=CredentialVault.get("smtp_port"),
            username=CredentialVault.get("smtp_user"),
            password=CredentialVault.get("smtp_password"),
            use_tls=CredentialVault.get("smtp_use_tls", True),
        )
        logger.info("email_sent_smtp", to=to)
        return {"status": "sent", "method": "smtp"}

    except ImportError:
        return {"status": "error", "error": "aiosmtplib not installed"}
    except Exception as e:
        return {"status": "error", "error": str(e)}
