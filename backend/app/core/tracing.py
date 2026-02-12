"""
Tracing — End-to-end request tracing for the enterprise OS.

Provides:
- TraceContext: per-workflow trace ID + per-step span ID
- TraceMiddleware: FastAPI middleware for auto-injecting trace context
- Celery propagation helpers for cross-process tracing

Every request, LLM call, tool execution, and data access shares the
same trace_id. Spans create a tree of parent→child relationships.
"""

from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger()


class TraceContext:
    """Lightweight trace context container.

    Created at request entry and propagated through all gateways.
    Provides child span creation for nested operations.
    """

    def __init__(
        self,
        trace_id: str | None = None,
        span_id: str | None = None,
        parent_span: str | None = None,
    ):
        self.trace_id = trace_id or str(uuid4())
        self.span_id = span_id or str(uuid4())
        self.parent_span = parent_span

    def child(self) -> "TraceContext":
        """Create a child span within the same trace."""
        return TraceContext(
            trace_id=self.trace_id,
            span_id=str(uuid4()),
            parent_span=self.span_id,
        )

    def to_dict(self) -> dict[str, str | None]:
        """Serialize for header propagation or Celery kwargs."""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span": self.parent_span,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str | None]) -> "TraceContext":
        """Reconstruct from header/kwarg dict."""
        return cls(
            trace_id=data.get("trace_id"),
            span_id=data.get("span_id"),
            parent_span=data.get("parent_span"),
        )

    @classmethod
    def from_headers(cls, headers: dict[str, str]) -> "TraceContext":
        """Extract trace context from HTTP headers.

        Headers:
            X-Trace-ID:    workflow trace ID
            X-Span-ID:     current span ID
            X-Parent-Span: parent span ID
        """
        return cls(
            trace_id=headers.get("x-trace-id") or headers.get("X-Trace-ID"),
            span_id=headers.get("x-span-id") or headers.get("X-Span-ID"),
            parent_span=headers.get("x-parent-span") or headers.get("X-Parent-Span"),
        )

    def inject_headers(self) -> dict[str, str]:
        """Create headers dict for outgoing requests."""
        headers = {"X-Trace-ID": self.trace_id, "X-Span-ID": self.span_id}
        if self.parent_span:
            headers["X-Parent-Span"] = self.parent_span
        return headers


class TraceMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that creates/propagates trace context.

    - If X-Trace-ID header is present, it's reused (distributed tracing)
    - Otherwise, a new trace is created
    - Trace context is bound to structlog and stored on request.state
    - Response includes X-Trace-ID and X-Span-ID headers
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Extract or create trace
        trace_id = request.headers.get("X-Trace-ID", str(uuid4()))
        span_id = str(uuid4())
        parent_span = request.headers.get("X-Parent-Span")

        trace = TraceContext(
            trace_id=trace_id,
            span_id=span_id,
            parent_span=parent_span,
        )

        # Store on request state for downstream access
        request.state.trace = trace
        request.state.trace_id = trace_id
        request.state.span_id = span_id

        # Bind to structlog for all logs within this request
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            trace_id=trace_id,
            span_id=span_id,
            method=request.method,
            path=request.url.path,
        )

        logger.info("request_start", method=request.method, path=request.url.path)

        response = await call_next(request)

        # Inject trace headers into response
        response.headers["X-Trace-ID"] = trace_id
        response.headers["X-Span-ID"] = span_id

        logger.info(
            "request_end",
            status=response.status_code,
        )

        return response


# ── Celery Propagation ────────────────────────────

def celery_inject(trace: TraceContext) -> dict[str, str | None]:
    """Inject trace context into Celery task kwargs.

    Usage:
        task.apply_async(
            args=[...],
            kwargs={**celery_inject(trace), ...}
        )
    """
    return {
        "_trace_id": trace.trace_id,
        "_parent_span": trace.span_id,
    }


def celery_extract(**kwargs) -> TraceContext:
    """Extract trace context from Celery task kwargs.

    Usage (inside task):
        trace = celery_extract(**kwargs)
    """
    return TraceContext(
        trace_id=kwargs.pop("_trace_id", None),
        parent_span=kwargs.pop("_parent_span", None),
    )
