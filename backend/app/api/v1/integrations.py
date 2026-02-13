"""
Integrations API — Settings panel CRUD for managing credentials.

Endpoints:
  GET    /api/v1/integrations/status       — Check which services are configured
  GET    /api/v1/integrations/credentials   — List credentials (masked)
  POST   /api/v1/integrations/credentials   — Set a credential
  DELETE /api/v1/integrations/credentials   — Remove a credential
  POST   /api/v1/integrations/test          — Test a service connection
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import structlog

from app.core.deps import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.orchestration.credential_vault import CredentialVault

logger = structlog.get_logger()

router = APIRouter(prefix="/integrations", tags=["integrations"])


class SetCredentialRequest(BaseModel):
    """Request to set a credential."""
    key: str
    value: str
    service: str  # "google" | "twilio" | "smtp"
    is_secret: bool = False


class TestConnectionRequest(BaseModel):
    """Request to test a service connection."""
    service: str  # "google" | "twilio" | "smtp" | "google_calendar" | "google_gmail"


@router.get("/status")
async def get_integration_status(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Check which integration services are configured."""
    # Ensure vault is loaded from DB
    if not CredentialVault._loaded:
        await CredentialVault.load(db)

    services = ["smtp", "twilio", "telegram", "google", "google_calendar", "google_drive", "google_gmail"]

    status = {}
    for svc in services:
        status[svc] = {
            "configured": CredentialVault.is_configured(svc),
        }

    return JSONResponse(content={"integrations": status}, status_code=200)


@router.get("/credentials")
async def list_credentials(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """List all configured credentials (values are masked for secrets)."""
    # Ensure vault is loaded from DB
    if not CredentialVault._loaded:
        await CredentialVault.load(db)
    all_keys = [
        ("smtp_host", "smtp", False),
        ("smtp_port", "smtp", False),
        ("smtp_user", "smtp", False),
        ("smtp_password", "smtp", True),
        ("smtp_from", "smtp", False),
        ("twilio_account_sid", "twilio", True),
        ("twilio_auth_token", "twilio", True),
        ("twilio_whatsapp_from", "twilio", False),
        ("telegram_bot_token", "telegram", True),
        ("telegram_webhook_secret", "telegram", True),
        ("google_service_account_json", "google", True),
        ("google_delegated_email", "google", False),
        ("google_calendar_id", "google", False),
        ("google_drive_folder_id", "google", False),
        ("allowed_email_domains", "channels", False),
        ("notification_channels", "channels", False),
    ]

    credentials = []
    for key, service, is_secret in all_keys:
        value = CredentialVault.get(key, "")
        credentials.append({
            "key": key,
            "service": service,
            "value": _mask_value(str(value)) if is_secret and value else str(value),
            "is_secret": is_secret,
            "is_set": bool(value),
        })

    return JSONResponse(content={"credentials": credentials}, status_code=200)


@router.post("/credentials")
async def set_credential(req: SetCredentialRequest, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Set/update a credential value. Persisted to DB."""
    # Update in-memory cache
    CredentialVault._cache[req.key] = req.value

    # Persist to DB via ORM
    from sqlalchemy import select
    from app.models.integration_credential import IntegrationCredential

    result = await db.execute(
        select(IntegrationCredential).where(IntegrationCredential.key == req.key)
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.value = req.value
        existing.service = req.service
        existing.is_secret = req.is_secret
    else:
        cred = IntegrationCredential(
            key=req.key,
            value=req.value,
            service=req.service,
            is_secret=req.is_secret,
            is_active=True,
        )
        db.add(cred)

    await db.commit()

    logger.info(
        "credential_set",
        key=req.key,
        service=req.service,
        is_secret=req.is_secret,
    )

    return JSONResponse(
        content={
            "status": "saved",
            "key": req.key,
            "service": req.service,
        },
        status_code=200,
    )


@router.delete("/credentials/{key}")
async def delete_credential(key: str) -> JSONResponse:
    """Remove a credential."""
    await CredentialVault.set(key, "")
    logger.info("credential_deleted", key=key)
    return JSONResponse(content={"status": "deleted", "key": key}, status_code=200)


@router.post("/test")
async def test_connection(req: TestConnectionRequest) -> JSONResponse:
    """Test if a service is properly configured and can connect."""
    if not CredentialVault.is_configured(req.service):
        return JSONResponse(
            content={
                "service": req.service,
                "status": "not_configured",
                "message": f"{req.service} credentials are not set",
            },
            status_code=200,
        )

    # Service-specific connection tests
    if req.service == "smtp":
        result = await _test_smtp()
    elif req.service in ("google", "google_calendar", "google_drive", "google_gmail"):
        result = await _test_google(req.service)
    elif req.service == "twilio":
        result = await _test_twilio()
    elif req.service == "telegram":
        result = await _test_telegram()
    else:
        result = {"status": "unknown", "message": f"No test for {req.service}"}

    return JSONResponse(
        content={"service": req.service, **result},
        status_code=200,
    )


# ── Helpers ──────────────────────────────────────


def _mask_value(value: str) -> str:
    """Mask a secret value, showing only first 4 and last 4 chars."""
    if len(value) <= 8:
        return "••••••••"
    return f"{value[:4]}{'•' * (len(value) - 8)}{value[-4:]}"


async def _test_smtp() -> dict:
    """Test SMTP connection."""
    try:
        import aiosmtplib
        smtp = aiosmtplib.SMTP(
            hostname=CredentialVault.get("smtp_host"),
            port=CredentialVault.get("smtp_port"),
        )
        await smtp.connect()
        await smtp.quit()
        return {"status": "connected", "message": "SMTP connection successful"}
    except ImportError:
        return {"status": "error", "message": "aiosmtplib not installed"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def _test_google(service: str) -> dict:
    """Test Google API connection."""
    try:
        from google.oauth2 import service_account
        creds_dict = CredentialVault.get_google_credentials()
        if not creds_dict:
            return {"status": "error", "message": "Invalid service account JSON"}

        credentials = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=["https://www.googleapis.com/auth/calendar.readonly"],
        )
        return {
            "status": "valid",
            "message": f"Service account: {creds_dict.get('client_email', 'unknown')}",
            "project": creds_dict.get("project_id", "unknown"),
        }
    except ImportError:
        return {"status": "error", "message": "google-auth not installed"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def _test_twilio() -> dict:
    """Test Twilio connection."""
    try:
        from twilio.rest import Client
        client = Client(
            CredentialVault.get("twilio_account_sid"),
            CredentialVault.get("twilio_auth_token"),
        )
        account = client.api.accounts(
            CredentialVault.get("twilio_account_sid")
        ).fetch()
        return {
            "status": "connected",
            "message": f"Account: {account.friendly_name}",
        }
    except ImportError:
        return {"status": "error", "message": "twilio package not installed"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def _test_telegram() -> dict:
    """Test Telegram Bot API connection via getMe."""
    try:
        import httpx
        token = CredentialVault.get("telegram_bot_token")
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"https://api.telegram.org/bot{token}/getMe")
            data = resp.json()
            if data.get("ok"):
                bot = data["result"]
                return {
                    "status": "connected",
                    "message": f"Bot: @{bot.get('username', 'unknown')} ({bot.get('first_name', '')})",
                }
            return {"status": "error", "message": data.get("description", "Unknown error")}
    except ImportError:
        return {"status": "error", "message": "httpx package not installed"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

