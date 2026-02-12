"""
Browser Tool — Control Chrome/Chromium browser via CDP (Chrome DevTools Protocol).

Uses Playwright under the hood for robust CDP communication.
Provides agents with the ability to:
  - Navigate to URLs
  - Take screenshots
  - Extract page content (text, HTML, structured data)
  - Click elements and fill forms
  - Execute JavaScript
  - Wait for elements / network idle
  - Manage browser sessions (open/close)

Registered as multiple tools in the ToolRegistry:
  - browser_open     (LOW)   — Launch browser session
  - browser_navigate (MEDIUM) — Navigate to URL
  - browser_screenshot (LOW)  — Take screenshot
  - browser_extract  (LOW)   — Extract page content
  - browser_click    (MEDIUM) — Click element
  - browser_fill     (MEDIUM) — Fill form field
  - browser_exec_js  (HIGH)  — Execute JavaScript
  - browser_close    (LOW)   — Close browser session
"""

from __future__ import annotations

import asyncio
import os
from typing import Any
from uuid import uuid4

import structlog

logger = structlog.get_logger()


# ── Session Manager ──────────────────────────

class BrowserSessionManager:
    """Manages browser sessions (one per agent task).

    Each session gets a unique ID and an isolated browser context
    so agents don't interfere with each other.
    """

    _sessions: dict[str, dict[str, Any]] = {}
    _playwright: Any = None

    @classmethod
    async def _ensure_playwright(cls) -> Any:
        """Lazily initialize Playwright."""
        if cls._playwright is None:
            try:
                from playwright.async_api import async_playwright
                pw = await async_playwright().start()
                cls._playwright = pw
                logger.info("playwright_initialized")
            except ImportError:
                raise ImportError(
                    "Playwright is not installed. "
                    "Install with: pip install playwright && playwright install chromium"
                )
        return cls._playwright

    @classmethod
    async def open(
        cls,
        headless: bool = True,
        viewport_width: int = 1280,
        viewport_height: int = 720,
        user_agent: str = "",
        proxy: str = "",
        session_id: str = "",
    ) -> dict[str, Any]:
        """Launch a new browser session.

        Args:
            headless: Run browser in headless mode (no GUI).
            viewport_width: Browser viewport width.
            viewport_height: Browser viewport height.
            user_agent: Custom user agent string.
            proxy: Proxy server URL (e.g. http://proxy:8080).
            session_id: Reuse existing session ID (optional).

        Returns:
            Dict with session_id and browser info.
        """
        sid = session_id or f"browser_{uuid4().hex[:8]}"

        # If session exists, return it
        if sid in cls._sessions:
            return {
                "status": "reused",
                "session_id": sid,
                "message": "Browser session already open.",
            }

        pw = await cls._ensure_playwright()

        # Launch Chromium (also works with Chrome/Edge via channel)
        launch_args: dict[str, Any] = {
            "headless": headless,
            "args": [
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        }

        if proxy:
            launch_args["proxy"] = {"server": proxy}

        # Try to find Chrome/Edge system install, fallback to Chromium
        browser = None
        for channel in ("chrome", "msedge", "chromium", None):
            try:
                if channel:
                    launch_args["channel"] = channel
                elif "channel" in launch_args:
                    del launch_args["channel"]
                browser = await pw.chromium.launch(**launch_args)
                logger.info("browser_launched", channel=channel or "chromium-bundled")
                break
            except Exception:
                continue

        if browser is None:
            return {
                "status": "error",
                "error": (
                    "Could not launch any browser. "
                    "Install Chromium with: playwright install chromium"
                ),
            }

        # Create isolated context
        context_args: dict[str, Any] = {
            "viewport": {"width": viewport_width, "height": viewport_height},
        }
        if user_agent:
            context_args["user_agent"] = user_agent

        context = await browser.new_context(**context_args)
        page = await context.new_page()

        cls._sessions[sid] = {
            "browser": browser,
            "context": context,
            "page": page,
            "channel": channel,
        }

        logger.info(
            "browser_session_opened",
            session_id=sid,
            headless=headless,
            viewport=f"{viewport_width}x{viewport_height}",
        )

        return {
            "status": "opened",
            "session_id": sid,
            "headless": headless,
            "viewport": f"{viewport_width}x{viewport_height}",
        }

    @classmethod
    def _get_page(cls, session_id: str) -> Any:
        """Get the active page for a session."""
        session = cls._sessions.get(session_id)
        if session is None:
            raise ValueError(f"Browser session '{session_id}' not found. Call browser_open first.")
        return session["page"]

    @classmethod
    async def close(cls, session_id: str) -> dict[str, Any]:
        """Close a browser session and release resources."""
        session = cls._sessions.pop(session_id, None)
        if session is None:
            return {"status": "not_found", "session_id": session_id}

        try:
            await session["context"].close()
            await session["browser"].close()
        except Exception as e:
            logger.warning("browser_close_error", error=str(e))

        logger.info("browser_session_closed", session_id=session_id)
        return {"status": "closed", "session_id": session_id}

    @classmethod
    async def close_all(cls) -> int:
        """Close all browser sessions (cleanup)."""
        count = len(cls._sessions)
        for sid in list(cls._sessions.keys()):
            await cls.close(sid)
        if cls._playwright:
            await cls._playwright.stop()
            cls._playwright = None
        return count


# ── Tool Handlers ────────────────────────────

async def browser_open_handler(
    headless: bool = True,
    viewport_width: int = 1280,
    viewport_height: int = 720,
    user_agent: str = "",
    proxy: str = "",
    session_id: str = "",
) -> dict[str, Any]:
    """Open a new Chrome browser session via CDP.

    The browser tries system Chrome first, then Edge, then
    bundled Chromium as fallback.
    """
    try:
        return await BrowserSessionManager.open(
            headless=headless,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
            user_agent=user_agent,
            proxy=proxy,
            session_id=session_id,
        )
    except ImportError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        logger.error("browser_open_error", error=str(e))
        return {"status": "error", "error": str(e)}


async def browser_navigate_handler(
    url: str,
    session_id: str,
    wait_until: str = "domcontentloaded",
    timeout_ms: int = 30000,
) -> dict[str, Any]:
    """Navigate the browser to a URL.

    Args:
        url: Target URL to navigate to.
        session_id: Browser session ID.
        wait_until: Wait condition — "load", "domcontentloaded", "networkidle".
        timeout_ms: Navigation timeout in milliseconds.

    Returns:
        Dict with final URL, title, and status code.
    """
    try:
        page = BrowserSessionManager._get_page(session_id)
        response = await page.goto(url, wait_until=wait_until, timeout=timeout_ms)

        title = await page.title()
        final_url = page.url

        logger.info(
            "browser_navigated",
            session_id=session_id,
            url=final_url,
            title=title,
            status=response.status if response else None,
        )

        return {
            "status": "navigated",
            "url": final_url,
            "title": title,
            "http_status": response.status if response else None,
            "session_id": session_id,
        }

    except ValueError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        logger.error("browser_navigate_error", url=url, error=str(e))
        return {"status": "error", "error": str(e)}


async def browser_screenshot_handler(
    session_id: str,
    selector: str = "",
    full_page: bool = False,
    save_path: str = "",
) -> dict[str, Any]:
    """Take a screenshot of the current page or a specific element.

    Args:
        session_id: Browser session ID.
        selector: CSS selector to screenshot (optional, defaults to full page).
        full_page: If True, capture full scrollable page.
        save_path: Path to save screenshot (auto-generated if empty).

    Returns:
        Dict with file path and image base64 preview.
    """
    try:
        page = BrowserSessionManager._get_page(session_id)

        if not save_path:
            os.makedirs("/tmp/browser_screenshots", exist_ok=True)
            save_path = f"/tmp/browser_screenshots/shot_{uuid4().hex[:8]}.png"

        if selector:
            element = await page.query_selector(selector)
            if element is None:
                return {"status": "error", "error": f"Element not found: {selector}"}
            await element.screenshot(path=save_path)
        else:
            await page.screenshot(path=save_path, full_page=full_page)

        logger.info(
            "browser_screenshot_taken",
            session_id=session_id,
            path=save_path,
            selector=selector or "full_page",
        )

        return {
            "status": "captured",
            "file_path": save_path,
            "selector": selector or ("full_page" if full_page else "viewport"),
            "session_id": session_id,
        }

    except ValueError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        logger.error("browser_screenshot_error", error=str(e))
        return {"status": "error", "error": str(e)}


async def browser_extract_handler(
    session_id: str,
    selector: str = "body",
    extract_type: str = "text",
    attribute: str = "",
    wait_for: str = "",
    timeout_ms: int = 10000,
) -> dict[str, Any]:
    """Extract content from the current page.

    Args:
        session_id: Browser session ID.
        selector: CSS selector to extract content from.
        extract_type: "text" | "html" | "attribute" | "all_links" | "table_data".
        attribute: HTML attribute to extract (when extract_type="attribute").
        wait_for: Wait for this selector to appear before extracting.
        timeout_ms: Wait timeout in milliseconds.

    Returns:
        Dict with extracted content.
    """
    try:
        page = BrowserSessionManager._get_page(session_id)

        # Wait for element if specified
        if wait_for:
            await page.wait_for_selector(wait_for, timeout=timeout_ms)

        if extract_type == "text":
            content = await page.inner_text(selector)
            return {
                "status": "extracted",
                "type": "text",
                "content": content[:10000],  # Cap at 10k chars
                "truncated": len(content) > 10000,
                "session_id": session_id,
            }

        elif extract_type == "html":
            content = await page.inner_html(selector)
            return {
                "status": "extracted",
                "type": "html",
                "content": content[:20000],
                "truncated": len(content) > 20000,
                "session_id": session_id,
            }

        elif extract_type == "attribute" and attribute:
            element = await page.query_selector(selector)
            if element is None:
                return {"status": "error", "error": f"Element not found: {selector}"}
            value = await element.get_attribute(attribute)
            return {
                "status": "extracted",
                "type": "attribute",
                "attribute": attribute,
                "value": value,
                "session_id": session_id,
            }

        elif extract_type == "all_links":
            links = await page.eval_on_selector_all(
                "a[href]",
                "elements => elements.map(e => ({text: e.innerText.trim(), href: e.href}))"
            )
            return {
                "status": "extracted",
                "type": "all_links",
                "links": links[:200],  # Cap at 200 links
                "count": len(links),
                "session_id": session_id,
            }

        elif extract_type == "table_data":
            tables = await page.eval_on_selector_all(
                f"{selector} table, {selector}",
                """tables => tables.filter(t => t.tagName === 'TABLE').map(table => {
                    const rows = Array.from(table.querySelectorAll('tr'));
                    return rows.map(row => {
                        const cells = Array.from(row.querySelectorAll('th, td'));
                        return cells.map(c => c.innerText.trim());
                    });
                })"""
            )
            return {
                "status": "extracted",
                "type": "table_data",
                "tables": tables[:10],  # Cap at 10 tables
                "session_id": session_id,
            }

        return {"status": "error", "error": f"Unknown extract_type: {extract_type}"}

    except ValueError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        logger.error("browser_extract_error", error=str(e))
        return {"status": "error", "error": str(e)}


async def browser_click_handler(
    session_id: str,
    selector: str,
    click_count: int = 1,
    button: str = "left",
    wait_after_ms: int = 1000,
) -> dict[str, Any]:
    """Click an element on the page.

    Args:
        session_id: Browser session ID.
        selector: CSS selector of element to click.
        click_count: Number of clicks (1=single, 2=double).
        button: Mouse button ("left", "right", "middle").
        wait_after_ms: Milliseconds to wait after clicking.

    Returns:
        Dict with click result and new page state.
    """
    try:
        page = BrowserSessionManager._get_page(session_id)

        await page.click(
            selector,
            click_count=click_count,
            button=button,
        )

        # Wait for potential navigation or DOM changes
        if wait_after_ms > 0:
            await asyncio.sleep(wait_after_ms / 1000)

        title = await page.title()
        current_url = page.url

        logger.info(
            "browser_clicked",
            session_id=session_id,
            selector=selector,
            new_url=current_url,
        )

        return {
            "status": "clicked",
            "selector": selector,
            "current_url": current_url,
            "title": title,
            "session_id": session_id,
        }

    except ValueError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        logger.error("browser_click_error", selector=selector, error=str(e))
        return {"status": "error", "error": str(e)}


async def browser_fill_handler(
    session_id: str,
    selector: str,
    value: str,
    press_enter: bool = False,
    clear_first: bool = True,
) -> dict[str, Any]:
    """Fill a form field with text.

    Args:
        session_id: Browser session ID.
        selector: CSS selector of the input/textarea.
        value: Text to fill in.
        press_enter: Press Enter key after filling.
        clear_first: Clear existing content before filling.

    Returns:
        Dict with fill result.
    """
    try:
        page = BrowserSessionManager._get_page(session_id)

        if clear_first:
            await page.fill(selector, value)
        else:
            await page.type(selector, value)

        if press_enter:
            await page.press(selector, "Enter")
            await asyncio.sleep(1)  # Wait for form submission

        logger.info(
            "browser_filled",
            session_id=session_id,
            selector=selector,
            value_len=len(value),
        )

        return {
            "status": "filled",
            "selector": selector,
            "value_length": len(value),
            "pressed_enter": press_enter,
            "current_url": page.url,
            "session_id": session_id,
        }

    except ValueError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        logger.error("browser_fill_error", selector=selector, error=str(e))
        return {"status": "error", "error": str(e)}


async def browser_exec_js_handler(
    session_id: str,
    script: str,
    arg: Any = None,
) -> dict[str, Any]:
    """Execute JavaScript in the browser page context.

    Args:
        session_id: Browser session ID.
        script: JavaScript code to execute.
        arg: Optional argument passed to the script.

    Returns:
        Dict with execution result.

    Security: This is a HIGH risk tool — requires approval.
    """
    try:
        page = BrowserSessionManager._get_page(session_id)

        if arg is not None:
            result = await page.evaluate(script, arg)
        else:
            result = await page.evaluate(script)

        # Serialize result safely
        import json
        try:
            result_str = json.dumps(result, default=str)
            if len(result_str) > 20000:
                result_str = result_str[:20000] + "... (truncated)"
        except (TypeError, ValueError):
            result_str = str(result)[:20000]

        logger.info(
            "browser_js_executed",
            session_id=session_id,
            script_len=len(script),
            result_len=len(result_str),
        )

        return {
            "status": "executed",
            "result": result,
            "result_preview": result_str[:500],
            "session_id": session_id,
        }

    except ValueError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        logger.error("browser_js_error", error=str(e))
        return {"status": "error", "error": str(e)}


async def browser_close_handler(
    session_id: str,
) -> dict[str, Any]:
    """Close a browser session and free resources."""
    return await BrowserSessionManager.close(session_id)
