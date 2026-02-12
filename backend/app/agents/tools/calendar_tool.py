"""
Calendar Tool — Create meetings via Google Calendar API.

Registered as `create_meeting` in the ToolRegistry.
Risk: MEDIUM — auto-approved for lead+.
"""

from typing import Any

import structlog

from app.services.orchestration.credential_vault import CredentialVault

logger = structlog.get_logger()


async def create_meeting_handler(
    title: str,
    start_time: str,
    end_time: str,
    attendees: list[str] | None = None,
    description: str = "",
    location: str = "",
    add_meet_link: bool = True,
) -> dict[str, Any]:
    """Create a Google Calendar event with optional Meet link.

    Args:
        title: Event title.
        start_time: ISO 8601 datetime string.
        end_time: ISO 8601 datetime string.
        attendees: List of email addresses.
        description: Event description.
        location: Physical or virtual location.
        add_meet_link: If True, generate Google Meet link.

    Returns:
        Dict with event_id, link, meet_link, and attendee status.
    """
    if not CredentialVault.is_configured("google_calendar"):
        return {"status": "error", "error": "Google Calendar not configured"}

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds_dict = CredentialVault.get_google_credentials()
        delegated_email = CredentialVault.get("google_delegated_email")
        calendar_id = CredentialVault.get("google_calendar_id", "primary")

        credentials = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=["https://www.googleapis.com/auth/calendar"],
            subject=delegated_email,
        )
        service = build("calendar", "v3", credentials=credentials)

        event_body: dict[str, Any] = {
            "summary": title,
            "description": description,
            "location": location,
            "start": {"dateTime": start_time, "timeZone": "Asia/Jakarta"},
            "end": {"dateTime": end_time, "timeZone": "Asia/Jakarta"},
        }

        if attendees:
            event_body["attendees"] = [{"email": e} for e in attendees]

        if add_meet_link:
            event_body["conferenceData"] = {
                "createRequest": {
                    "requestId": f"meet_{title[:10]}",
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            }

        event = service.events().insert(
            calendarId=calendar_id,
            body=event_body,
            conferenceDataVersion=1 if add_meet_link else 0,
            sendUpdates="all" if attendees else "none",
        ).execute()

        meet_link = ""
        if event.get("conferenceData"):
            entry_points = event["conferenceData"].get("entryPoints", [])
            for ep in entry_points:
                if ep.get("entryPointType") == "video":
                    meet_link = ep.get("uri", "")
                    break

        logger.info(
            "calendar_event_created",
            event_id=event.get("id"),
            title=title,
            attendees=len(attendees or []),
        )

        return {
            "status": "created",
            "event_id": event.get("id", ""),
            "html_link": event.get("htmlLink", ""),
            "meet_link": meet_link,
            "start": start_time,
            "end": end_time,
            "attendees_count": len(attendees or []),
        }

    except ImportError:
        return {"status": "error", "error": "google-api-python-client not installed"}
    except Exception as e:
        logger.error("calendar_event_error", error=str(e))
        return {"status": "error", "error": str(e)}
