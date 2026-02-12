"""
Shared Tools Registration — Registers tools available to ALL departments.

These tools are added to the ToolRegistry alongside department-specific tools.
All shared tools go through the ToolBroker chokepoint.
"""

from app.agents.tools.browser_tool import (
    browser_click_handler,
    browser_close_handler,
    browser_exec_js_handler,
    browser_extract_handler,
    browser_fill_handler,
    browser_navigate_handler,
    browser_open_handler,
    browser_screenshot_handler,
)
from app.agents.tools.calendar_tool import create_meeting_handler
from app.agents.tools.claude_code_tool import (
    code_convert_handler,
    code_debug_handler,
    code_document_handler,
    code_explain_handler,
    code_generate_handler,
    code_refactor_handler,
    code_review_handler,
    code_test_handler,
)
from app.agents.tools.drive_tool import read_file_handler, upload_file_handler
from app.agents.tools.email_tool import send_email_handler
from app.agents.tools.scraper_tool import (
    scrape_multiple_handler,
    scrape_page_handler,
    scrape_pricing_handler,
    scrape_seo_handler,
)
from app.agents.tools.search_tool import generate_report_handler, search_data_handler
from app.agents.tools.terminal_tool import (
    terminal_exec_handler,
    terminal_git_handler,
    terminal_install_handler,
    terminal_script_handler,
)
from app.agents.tools.whatsapp_tool import send_whatsapp_handler
from app.agents.tools.telegram_tool import send_telegram_handler
from app.core.tool_registry import RiskLevel, ToolRegistry


def register_shared_tools() -> None:
    """Register all shared tools in the ToolRegistry.

    Call this at startup to make shared tools available to all agents.
    """
    tools = [
        # ── Communication ────────────────────────
        {
            "name": "send_email",
            "description": (
                "Send an email to a specified recipient. "
                "Supports HTML body, CC/BCC, and attachments. "
                "Uses Gmail API or SMTP fallback."
            ),
            "handler": send_email_handler,
            "risk_level": RiskLevel.HIGH,
            "departments": ["*"],
            "roles": ["*"],
            "has_egress": True,
            "egress_domains": ["gmail.googleapis.com", "smtp.gmail.com"],
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email"},
                    "subject": {"type": "string", "description": "Email subject"},
                    "body": {"type": "string", "description": "Email body text"},
                    "cc": {"type": "string", "description": "CC recipients (comma-separated)"},
                    "html": {"type": "boolean", "description": "If true, body is HTML"},
                },
                "required": ["to", "subject", "body"],
            },
        },
        {
            "name": "send_whatsapp",
            "description": (
                "Send a WhatsApp message via Twilio. "
                "Can include text and media attachments."
            ),
            "handler": send_whatsapp_handler,
            "risk_level": RiskLevel.HIGH,
            "departments": ["*"],
            "roles": ["*"],
            "has_egress": True,
            "egress_domains": ["api.twilio.com"],
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Phone number e.g. +6281234567890"},
                    "message": {"type": "string", "description": "Message text"},
                    "media_url": {"type": "string", "description": "Optional media URL"},
                },
                "required": ["to", "message"],
            },
        },
        {
            "name": "send_telegram",
            "description": (
                "Send a Telegram message via Bot API. "
                "Can include text with HTML/Markdown formatting and photos."
            ),
            "handler": send_telegram_handler,
            "risk_level": RiskLevel.HIGH,
            "departments": ["*"],
            "roles": ["*"],
            "has_egress": True,
            "egress_domains": ["api.telegram.org"],
            "parameters": {
                "type": "object",
                "properties": {
                    "chat_id": {"type": "string", "description": "Target chat ID or @channel_username"},
                    "message": {"type": "string", "description": "Message text"},
                    "parse_mode": {"type": "string", "description": "Optional: HTML or Markdown"},
                    "photo_url": {"type": "string", "description": "Optional photo URL"},
                },
                "required": ["chat_id", "message"],
            },
        },

        # ── Scheduling ───────────────────────────
        {
            "name": "create_meeting",
            "description": (
                "Create a Google Calendar event with optional Google Meet link. "
                "Sends invites to all attendees."
            ),
            "handler": create_meeting_handler,
            "risk_level": RiskLevel.MEDIUM,
            "departments": ["*"],
            "roles": ["*"],
            "has_egress": True,
            "egress_domains": ["www.googleapis.com"],
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Event title"},
                    "start_time": {"type": "string", "description": "ISO 8601 start time"},
                    "end_time": {"type": "string", "description": "ISO 8601 end time"},
                    "attendees": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of attendee emails",
                    },
                    "description": {"type": "string", "description": "Event description"},
                    "add_meet_link": {"type": "boolean", "description": "Generate Meet link"},
                },
                "required": ["title", "start_time", "end_time"],
            },
        },

        # ── File Management ──────────────────────
        {
            "name": "upload_file",
            "description": "Upload a file to Google Drive.",
            "handler": upload_file_handler,
            "risk_level": RiskLevel.MEDIUM,
            "departments": ["*"],
            "roles": ["*"],
            "has_egress": True,
            "has_file_access": True,
            "egress_domains": ["www.googleapis.com"],
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Local file path"},
                    "file_name": {"type": "string", "description": "Name in Drive"},
                    "mime_type": {"type": "string", "description": "MIME type"},
                },
                "required": ["file_path"],
            },
        },
        {
            "name": "read_file",
            "description": "Read/download a file from Google Drive.",
            "handler": read_file_handler,
            "risk_level": RiskLevel.LOW,
            "departments": ["*"],
            "roles": ["*"],
            "has_egress": True,
            "egress_domains": ["www.googleapis.com"],
            "parameters": {
                "type": "object",
                "properties": {
                    "file_id": {"type": "string", "description": "Google Drive file ID"},
                    "download_path": {"type": "string", "description": "Local path to save"},
                },
                "required": ["file_id"],
            },
        },

        # ── Data ─────────────────────────────────
        {
            "name": "search_data",
            "description": "Search company database and knowledge base for information.",
            "handler": search_data_handler,
            "risk_level": RiskLevel.LOW,
            "departments": ["*"],
            "roles": ["*"],
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "table": {"type": "string", "description": "Specific table to search"},
                    "department": {"type": "string", "description": "Department scope"},
                    "limit": {"type": "integer", "description": "Max results"},
                },
                "required": ["query"],
            },
        },
        {
            "name": "generate_report",
            "description": "Generate a formatted report (PDF, Excel, CSV).",
            "handler": generate_report_handler,
            "risk_level": RiskLevel.LOW,
            "departments": ["*"],
            "roles": ["*"],
            "parameters": {
                "type": "object",
                "properties": {
                    "report_type": {"type": "string", "description": "Report type (P&L, pipeline, etc.)"},
                    "period": {"type": "string", "description": "Time period (Q1 2026, etc.)"},
                    "department": {"type": "string", "description": "Department scope"},
                    "format": {"type": "string", "description": "Output format: pdf, xlsx, csv"},
                },
                "required": ["report_type"],
            },
        },

        # ── Browser (CDP) ────────────────────────
        {
            "name": "browser_open",
            "description": (
                "Open a Chrome/Chromium browser session via CDP. "
                "Auto-detects installed Chrome, Edge, or bundled Chromium."
            ),
            "handler": browser_open_handler,
            "risk_level": RiskLevel.LOW,
            "departments": ["*"],
            "roles": ["*"],
            "parameters": {
                "type": "object",
                "properties": {
                    "headless": {"type": "boolean", "description": "Run headless (no GUI), default true"},
                    "viewport_width": {"type": "integer", "description": "Viewport width, default 1280"},
                    "viewport_height": {"type": "integer", "description": "Viewport height, default 720"},
                    "user_agent": {"type": "string", "description": "Custom user agent"},
                    "proxy": {"type": "string", "description": "Proxy server URL"},
                    "session_id": {"type": "string", "description": "Reuse existing session ID"},
                },
                "required": [],
            },
        },
        {
            "name": "browser_navigate",
            "description": "Navigate the browser to a URL. Returns page title and status.",
            "handler": browser_navigate_handler,
            "risk_level": RiskLevel.MEDIUM,
            "departments": ["*"],
            "roles": ["*"],
            "has_egress": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to navigate to"},
                    "session_id": {"type": "string", "description": "Browser session ID"},
                    "wait_until": {"type": "string", "description": "load | domcontentloaded | networkidle"},
                    "timeout_ms": {"type": "integer", "description": "Navigation timeout in ms"},
                },
                "required": ["url", "session_id"],
            },
        },
        {
            "name": "browser_screenshot",
            "description": "Take a screenshot of the page or a specific element.",
            "handler": browser_screenshot_handler,
            "risk_level": RiskLevel.LOW,
            "departments": ["*"],
            "roles": ["*"],
            "has_file_access": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Browser session ID"},
                    "selector": {"type": "string", "description": "CSS selector to capture (optional)"},
                    "full_page": {"type": "boolean", "description": "Capture full scrollable page"},
                    "save_path": {"type": "string", "description": "File path to save screenshot"},
                },
                "required": ["session_id"],
            },
        },
        {
            "name": "browser_extract",
            "description": (
                "Extract content from the page: text, HTML, attribute values, "
                "all links, or table data. Used for data analysis and scraping."
            ),
            "handler": browser_extract_handler,
            "risk_level": RiskLevel.LOW,
            "departments": ["*"],
            "roles": ["*"],
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Browser session ID"},
                    "selector": {"type": "string", "description": "CSS selector to extract from"},
                    "extract_type": {"type": "string", "description": "text | html | attribute | all_links | table_data"},
                    "attribute": {"type": "string", "description": "HTML attribute name (for extract_type=attribute)"},
                    "wait_for": {"type": "string", "description": "Wait for this selector before extracting"},
                },
                "required": ["session_id"],
            },
        },
        {
            "name": "browser_click",
            "description": "Click an element on the page by CSS selector.",
            "handler": browser_click_handler,
            "risk_level": RiskLevel.MEDIUM,
            "departments": ["*"],
            "roles": ["*"],
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Browser session ID"},
                    "selector": {"type": "string", "description": "CSS selector to click"},
                    "click_count": {"type": "integer", "description": "1=single, 2=double click"},
                    "button": {"type": "string", "description": "left | right | middle"},
                },
                "required": ["session_id", "selector"],
            },
        },
        {
            "name": "browser_fill",
            "description": "Fill a form input or textarea with text.",
            "handler": browser_fill_handler,
            "risk_level": RiskLevel.MEDIUM,
            "departments": ["*"],
            "roles": ["*"],
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Browser session ID"},
                    "selector": {"type": "string", "description": "CSS selector of the input"},
                    "value": {"type": "string", "description": "Text to fill"},
                    "press_enter": {"type": "boolean", "description": "Press Enter after filling"},
                    "clear_first": {"type": "boolean", "description": "Clear existing content first"},
                },
                "required": ["session_id", "selector", "value"],
            },
        },
        {
            "name": "browser_exec_js",
            "description": (
                "Execute JavaScript in the browser context. "
                "Returns the evaluation result. HIGH risk — requires approval."
            ),
            "handler": browser_exec_js_handler,
            "risk_level": RiskLevel.HIGH,
            "departments": ["*"],
            "roles": ["*"],
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Browser session ID"},
                    "script": {"type": "string", "description": "JavaScript code to execute"},
                    "arg": {"type": "string", "description": "Optional argument passed to script"},
                },
                "required": ["session_id", "script"],
            },
        },
        {
            "name": "browser_close",
            "description": "Close a browser session and release resources.",
            "handler": browser_close_handler,
            "risk_level": RiskLevel.LOW,
            "departments": ["*"],
            "roles": ["*"],
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Browser session ID to close"},
                },
                "required": ["session_id"],
            },
        },

        # ── Web Scraping (Digital Marketing & Data Analysis) ─
        {
            "name": "scrape_page",
            "description": (
                "Scrape structured data from a single web page using CSS selectors. "
                "Can also extract all links, images, and table data. "
                "Ideal for competitor analysis and market research."
            ),
            "handler": scrape_page_handler,
            "risk_level": RiskLevel.MEDIUM,
            "departments": ["*"],
            "roles": ["*"],
            "has_egress": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to scrape"},
                    "selectors": {
                        "type": "object",
                        "description": "Map of {field_name: css_selector} for data extraction",
                    },
                    "wait_for": {"type": "string", "description": "Wait for selector (JS pages)"},
                    "extract_links": {"type": "boolean", "description": "Extract all page links"},
                    "extract_images": {"type": "boolean", "description": "Extract all image URLs"},
                    "extract_tables": {"type": "boolean", "description": "Extract all table data"},
                },
                "required": ["url"],
            },
        },
        {
            "name": "scrape_multiple",
            "description": (
                "Crawl and scrape multiple pages sequentially with rate limiting. "
                "Apply the same selectors to all pages for batch data collection."
            ),
            "handler": scrape_multiple_handler,
            "risk_level": RiskLevel.MEDIUM,
            "departments": ["*"],
            "roles": ["*"],
            "has_egress": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of URLs to scrape",
                    },
                    "selectors": {"type": "object", "description": "CSS selectors map"},
                    "delay_ms": {"type": "integer", "description": "Delay between pages (ms)"},
                    "max_pages": {"type": "integer", "description": "Max pages to scrape"},
                },
                "required": ["urls"],
            },
        },
        {
            "name": "scrape_seo",
            "description": (
                "SEO audit of a page: meta tags, heading hierarchy, link analysis, "
                "image alt coverage, word count, structured data, and page load performance. "
                "Essential for digital marketing optimization."
            ),
            "handler": scrape_seo_handler,
            "risk_level": RiskLevel.MEDIUM,
            "departments": ["*"],
            "roles": ["*"],
            "has_egress": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to audit"},
                    "timeout_ms": {"type": "integer", "description": "Navigation timeout"},
                },
                "required": ["url"],
            },
        },
        {
            "name": "scrape_pricing",
            "description": (
                "Scrape product listings and pricing from e-commerce / competitor sites. "
                "Auto-detects product cards, names, and prices. Supports pagination."
            ),
            "handler": scrape_pricing_handler,
            "risk_level": RiskLevel.MEDIUM,
            "departments": ["*"],
            "roles": ["*"],
            "has_egress": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Product listing page URL"},
                    "product_selector": {"type": "string", "description": "CSS selector for product cards"},
                    "name_selector": {"type": "string", "description": "CSS selector for product name"},
                    "price_selector": {"type": "string", "description": "CSS selector for price"},
                    "next_page_selector": {"type": "string", "description": "CSS selector for next page button"},
                    "max_pages": {"type": "integer", "description": "Max pages to scrape"},
                },
                "required": ["url"],
            },
        },

        # ── Claude Code (Developer AI) ───────────
        {
            "name": "code_generate",
            "description": (
                "Generate production-ready code from a description or spec. "
                "Supports any language and framework. Includes type hints, "
                "docstrings, and error handling."
            ),
            "handler": code_generate_handler,
            "risk_level": RiskLevel.LOW,
            "departments": ["*"],
            "roles": ["*"],
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {"type": "string", "description": "What the code should do"},
                    "language": {"type": "string", "description": "Target language (default: python)"},
                    "framework": {"type": "string", "description": "Framework (FastAPI, React, etc.)"},
                    "requirements": {"type": "string", "description": "Specific requirements"},
                },
                "required": ["description"],
            },
        },
        {
            "name": "code_review",
            "description": (
                "Review code for bugs, security vulnerabilities, performance issues, "
                "and best practice violations. Returns findings with severity ratings."
            ),
            "handler": code_review_handler,
            "risk_level": RiskLevel.LOW,
            "departments": ["*"],
            "roles": ["*"],
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Source code to review"},
                    "language": {"type": "string", "description": "Programming language"},
                    "focus": {"type": "string", "description": "Focus: security, performance, bugs, all"},
                },
                "required": ["code"],
            },
        },
        {
            "name": "code_refactor",
            "description": (
                "Refactor and improve existing code. Applies SOLID, DRY, KISS principles, "
                "optimizes performance, and uses modern language idioms."
            ),
            "handler": code_refactor_handler,
            "risk_level": RiskLevel.LOW,
            "departments": ["*"],
            "roles": ["*"],
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Source code to refactor"},
                    "language": {"type": "string", "description": "Programming language"},
                    "goals": {"type": "string", "description": "Refactoring goals"},
                },
                "required": ["code"],
            },
        },
        {
            "name": "code_debug",
            "description": (
                "Analyze code and errors to find root cause, explain the bug, "
                "and provide the exact fix with corrected code."
            ),
            "handler": code_debug_handler,
            "risk_level": RiskLevel.LOW,
            "departments": ["*"],
            "roles": ["*"],
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Source code with the bug"},
                    "error": {"type": "string", "description": "Error message or stack trace"},
                    "expected_behavior": {"type": "string", "description": "What it should do"},
                    "language": {"type": "string", "description": "Programming language"},
                },
                "required": ["code"],
            },
        },
        {
            "name": "code_test",
            "description": (
                "Generate comprehensive unit and integration tests. "
                "Supports pytest, unittest, jest, mocha, and more."
            ),
            "handler": code_test_handler,
            "risk_level": RiskLevel.LOW,
            "departments": ["*"],
            "roles": ["*"],
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Source code to test"},
                    "language": {"type": "string", "description": "Language (default: python)"},
                    "framework": {"type": "string", "description": "Test framework (default: pytest)"},
                    "coverage_targets": {"type": "string", "description": "Specific functions to target"},
                },
                "required": ["code"],
            },
        },
        {
            "name": "code_explain",
            "description": (
                "Explain code in plain language — what it does, how it works, "
                "key patterns and design choices."
            ),
            "handler": code_explain_handler,
            "risk_level": RiskLevel.LOW,
            "departments": ["*"],
            "roles": ["*"],
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Source code to explain"},
                    "language": {"type": "string", "description": "Programming language"},
                    "detail_level": {"type": "string", "description": "brief, medium, or detailed"},
                    "audience": {"type": "string", "description": "beginner, developer, or architect"},
                },
                "required": ["code"],
            },
        },
        {
            "name": "code_convert",
            "description": (
                "Convert code between programming languages while maintaining "
                "equivalent functionality and idiomatic patterns."
            ),
            "handler": code_convert_handler,
            "risk_level": RiskLevel.LOW,
            "departments": ["*"],
            "roles": ["*"],
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Source code to convert"},
                    "source_language": {"type": "string", "description": "Original language"},
                    "target_language": {"type": "string", "description": "Target language"},
                    "target_framework": {"type": "string", "description": "Target framework"},
                },
                "required": ["code", "source_language", "target_language"],
            },
        },
        {
            "name": "code_document",
            "description": (
                "Generate documentation from source code — module overview, "
                "function signatures, parameters, return values, and usage examples."
            ),
            "handler": code_document_handler,
            "risk_level": RiskLevel.LOW,
            "departments": ["*"],
            "roles": ["*"],
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Source code to document"},
                    "language": {"type": "string", "description": "Programming language"},
                    "doc_format": {"type": "string", "description": "markdown, docstring, jsdoc, openapi"},
                    "include_examples": {"type": "boolean", "description": "Include usage examples"},
                },
                "required": ["code"],
            },
        },

        # ── Sandboxed Terminal (Docker Isolation) ──
        {
            "name": "terminal_exec",
            "description": (
                "Execute a shell command in an isolated Docker container. "
                "Has CPU/memory limits, read-only FS, network isolation, "
                "and command allowlist. Safe for dev tasks."
            ),
            "handler": terminal_exec_handler,
            "risk_level": RiskLevel.HIGH,
            "departments": ["*"],
            "roles": ["*"],
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute"},
                    "image": {"type": "string", "description": "Docker image (default: python:3.12-slim)"},
                    "timeout_sec": {"type": "integer", "description": "Timeout in seconds (max 300)"},
                    "network": {"type": "string", "description": "none (isolated) or bridge (internet)"},
                },
                "required": ["command"],
            },
        },
        {
            "name": "terminal_git",
            "description": (
                "Execute git operations in a sandboxed container. "
                "Supports clone, pull, push, commit, status, log, diff, branch, checkout."
            ),
            "handler": terminal_git_handler,
            "risk_level": RiskLevel.HIGH,
            "departments": ["*"],
            "roles": ["*"],
            "has_egress": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {"type": "string", "description": "Git operation: clone, pull, push, commit, status, log, diff, branch, checkout"},
                    "repo_url": {"type": "string", "description": "Repository URL"},
                    "branch": {"type": "string", "description": "Branch name (default: main)"},
                    "message": {"type": "string", "description": "Commit message"},
                    "args": {"type": "string", "description": "Additional git arguments"},
                },
                "required": ["operation"],
            },
        },
        {
            "name": "terminal_install",
            "description": (
                "Install packages in a sandboxed container (ephemeral, does NOT affect host). "
                "Supports pip, npm, yarn, apt, apk, cargo."
            ),
            "handler": terminal_install_handler,
            "risk_level": RiskLevel.HIGH,
            "departments": ["*"],
            "roles": ["*"],
            "has_egress": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "packages": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of packages to install",
                    },
                    "manager": {"type": "string", "description": "pip, npm, yarn, apt, apk, cargo"},
                    "image": {"type": "string", "description": "Custom Docker image"},
                },
                "required": ["packages"],
            },
        },
        {
            "name": "terminal_script",
            "description": (
                "Run a multi-line script in a sandboxed container. "
                "Supports bash, python, node, ruby. No network by default."
            ),
            "handler": terminal_script_handler,
            "risk_level": RiskLevel.HIGH,
            "departments": ["*"],
            "roles": ["*"],
            "parameters": {
                "type": "object",
                "properties": {
                    "script": {"type": "string", "description": "Script content (multi-line)"},
                    "language": {"type": "string", "description": "bash, python, node, ruby"},
                    "image": {"type": "string", "description": "Custom Docker image"},
                    "timeout_sec": {"type": "integer", "description": "Timeout in seconds"},
                },
                "required": ["script"],
            },
        },
    ]

    for tool_def in tools:
        ToolRegistry.register_shared_tool(**tool_def)

