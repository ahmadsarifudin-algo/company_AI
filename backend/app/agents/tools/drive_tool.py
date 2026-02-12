"""
Drive Tool — Upload/read files via Google Drive API.

Registered as `upload_file` and `read_file` in the ToolRegistry.
Risk: upload=MEDIUM, read=LOW.
"""

from typing import Any

import structlog

from app.services.orchestration.credential_vault import CredentialVault

logger = structlog.get_logger()


async def upload_file_handler(
    file_path: str,
    file_name: str = "",
    mime_type: str = "application/octet-stream",
    folder_id: str = "",
) -> dict[str, Any]:
    """Upload a file to Google Drive.

    Args:
        file_path: Local path to the file.
        file_name: Name in Drive (defaults to local filename).
        mime_type: MIME type of the file.
        folder_id: Drive folder ID (defaults to config).

    Returns:
        Dict with file_id, web_link, and file name.
    """
    if not CredentialVault.is_configured("google_drive"):
        return {"status": "error", "error": "Google Drive not configured"}

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        import os

        creds_dict = CredentialVault.get_google_credentials()
        credentials = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=["https://www.googleapis.com/auth/drive.file"],
        )
        service = build("drive", "v3", credentials=credentials)

        if not file_name:
            file_name = os.path.basename(file_path)

        target_folder = folder_id or CredentialVault.get("google_drive_folder_id")

        file_metadata: dict[str, Any] = {"name": file_name}
        if target_folder:
            file_metadata["parents"] = [target_folder]

        media = MediaFileUpload(file_path, mimetype=mime_type)

        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, name, webViewLink, size",
        ).execute()

        logger.info(
            "drive_file_uploaded",
            file_id=file.get("id"),
            name=file_name,
        )

        return {
            "status": "uploaded",
            "file_id": file.get("id", ""),
            "file_name": file.get("name", ""),
            "web_link": file.get("webViewLink", ""),
            "size": file.get("size", 0),
        }

    except ImportError:
        return {"status": "error", "error": "google-api-python-client not installed"}
    except Exception as e:
        logger.error("drive_upload_error", error=str(e))
        return {"status": "error", "error": str(e)}


async def read_file_handler(
    file_id: str,
    download_path: str = "",
) -> dict[str, Any]:
    """Read/download a file from Google Drive.

    Args:
        file_id: Google Drive file ID.
        download_path: Local path to save file (optional).

    Returns:
        Dict with file metadata and content preview.
    """
    if not CredentialVault.is_configured("google"):
        return {"status": "error", "error": "Google Drive not configured"}

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds_dict = CredentialVault.get_google_credentials()
        credentials = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=["https://www.googleapis.com/auth/drive.readonly"],
        )
        service = build("drive", "v3", credentials=credentials)

        # Get metadata
        file_meta = service.files().get(
            fileId=file_id,
            fields="id, name, mimeType, size, modifiedTime",
        ).execute()

        result: dict[str, Any] = {
            "status": "found",
            "file_id": file_meta.get("id", ""),
            "name": file_meta.get("name", ""),
            "mime_type": file_meta.get("mimeType", ""),
            "size": file_meta.get("size", 0),
            "modified": file_meta.get("modifiedTime", ""),
        }

        # Download if path specified
        if download_path:
            import io
            request = service.files().get_media(fileId=file_id)
            with open(download_path, "wb") as f:
                downloader = request.execute()
                if isinstance(downloader, bytes):
                    f.write(downloader)
            result["downloaded_to"] = download_path

        logger.info("drive_file_read", file_id=file_id, name=file_meta.get("name"))
        return result

    except ImportError:
        return {"status": "error", "error": "google-api-python-client not installed"}
    except Exception as e:
        logger.error("drive_read_error", error=str(e))
        return {"status": "error", "error": str(e)}
