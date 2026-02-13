"""
HTTP Gateway — Core chokepoint for all outbound HTTP requests.

Agents and tools MUST use this gateway (not httpx/requests directly)
to ensure network policies, audit logging, and egress control.
"""

from typing import Any

import httpx
import structlog

logger = structlog.get_logger()


async def http_post(
    url: str,
    *,
    json: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Send an HTTP POST request through the gateway.

    Args:
        url: Target URL.
        json: Optional JSON payload.
        data: Optional form data.
        headers: Optional headers.
        timeout: Request timeout in seconds.

    Returns:
        Dict with status_code and parsed JSON body.
    """
    logger.info("http_gateway_post", url=url)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=json, data=data, headers=headers)
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text}
        return {"status_code": resp.status_code, "body": body}


async def http_get(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Send an HTTP GET request through the gateway.

    Args:
        url: Target URL.
        params: Optional query parameters.
        headers: Optional headers.
        timeout: Request timeout in seconds.

    Returns:
        Dict with status_code and parsed JSON body.
    """
    logger.info("http_gateway_get", url=url)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url, params=params, headers=headers)
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text}
        return {"status_code": resp.status_code, "body": body}
