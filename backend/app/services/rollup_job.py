"""
Metrics Rollup Job — Periodic aggregation of audit_events into hourly buckets.

Designed to run as a Celery beat task or standalone cron job.
Generates metrics_rollups_hourly rows for dashboard charts.
"""

from datetime import datetime, timezone, timedelta

import structlog
from sqlalchemy import func, select, case, literal_column, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.audit import AuditEvent
from app.models.metrics_rollup import MetricsRollupHourly
from app.models.trace_index import TraceIndex

logger = structlog.get_logger()


def compute_hourly_rollup(
    db: Session,
    bucket_start: datetime | None = None,
) -> int:
    """Compute metrics rollup for a single hourly bucket.

    Args:
        db: Synchronous DB session.
        bucket_start: Start of the hour to compute. Defaults to previous hour.

    Returns:
        Number of rollup rows upserted.
    """
    if bucket_start is None:
        now = datetime.now(timezone.utc)
        bucket_start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)

    bucket_end = bucket_start + timedelta(hours=1)

    # Query audit_events for this bucket, grouped by department + agent_id
    events = (
        db.query(
            AuditEvent.department,
            AuditEvent.agent_id,
            func.count().label("total_events"),
            # Trace counts (approximate from events)
            func.count(func.distinct(
                case(
                    (AuditEvent.event_type.in_(["workflow_started", "agent_started"]),
                     AuditEvent.trace_id),
                    else_=None,
                )
            )).label("traces_started"),
            func.count(func.distinct(
                case(
                    (AuditEvent.event_type.in_(["workflow_completed", "agent_completed"]),
                     AuditEvent.trace_id),
                    else_=None,
                )
            )).label("traces_completed"),
            func.count(func.distinct(
                case(
                    (AuditEvent.event_type.in_(["workflow_failed", "agent_failed"]),
                     AuditEvent.trace_id),
                    else_=None,
                )
            )).label("traces_failed"),
            func.count(func.distinct(
                case(
                    (AuditEvent.event_type == "approval_requested",
                     AuditEvent.trace_id),
                    else_=None,
                )
            )).label("traces_needs_approval"),
            # Tool stats
            func.sum(case(
                (AuditEvent.event_type.in_(["tool_called", "tool_call_allowed"]), 1),
                else_=0,
            )).label("tool_calls"),
            func.sum(case(
                (AuditEvent.event_type == "tool_call_denied", 1),
                else_=0,
            )).label("tool_denied"),
            func.sum(case(
                (AuditEvent.event_type == "tool_failed", 1),
                else_=0,
            )).label("tool_failed"),
            # LLM stats
            func.sum(case(
                (AuditEvent.event_type == "llm_call_completed", 1),
                else_=0,
            )).label("llm_calls"),
            func.sum(case(
                (AuditEvent.event_type == "llm_call_failed", 1),
                else_=0,
            )).label("llm_failed"),
            func.coalesce(func.sum(AuditEvent.tokens_in), 0).label("tokens_in"),
            func.coalesce(func.sum(AuditEvent.tokens_out), 0).label("tokens_out"),
            func.coalesce(func.sum(AuditEvent.cost_usd), 0).label("cost_usd"),
            # Approval stats
            func.sum(case(
                (AuditEvent.event_type == "approval_requested", 1),
                else_=0,
            )).label("approval_requests"),
            func.sum(case(
                (AuditEvent.event_type == "approval_granted", 1),
                else_=0,
            )).label("approvals_granted"),
            func.sum(case(
                (AuditEvent.event_type == "approval_denied", 1),
                else_=0,
            )).label("approvals_denied"),
        )
        .filter(
            AuditEvent.created_at >= bucket_start,
            AuditEvent.created_at < bucket_end,
        )
        .group_by(AuditEvent.department, AuditEvent.agent_id)
        .all()
    )

    upserted = 0
    for row in events:
        # Agent-level rollup
        rollup = MetricsRollupHourly(
            bucket_start=bucket_start,
            department=row.department,
            agent_id=row.agent_id,
            metric_scope="agent",
            traces_started=row.traces_started or 0,
            traces_completed=row.traces_completed or 0,
            traces_failed=row.traces_failed or 0,
            traces_needs_approval=row.traces_needs_approval or 0,
            tool_calls=row.tool_calls or 0,
            tool_denied=row.tool_denied or 0,
            tool_failed=row.tool_failed or 0,
            llm_calls=row.llm_calls or 0,
            llm_failed=row.llm_failed or 0,
            tokens_in=row.tokens_in or 0,
            tokens_out=row.tokens_out or 0,
            cost_usd=row.cost_usd or 0,
            approval_requests=row.approval_requests or 0,
            approvals_granted=row.approvals_granted or 0,
            approvals_denied=row.approvals_denied or 0,
        )
        db.merge(rollup)
        upserted += 1

    # Department-level rollups (aggregate across agents)
    dept_aggregates: dict[str, dict] = {}
    for row in events:
        dept = row.department
        if dept not in dept_aggregates:
            dept_aggregates[dept] = {
                "traces_started": 0, "traces_completed": 0,
                "traces_failed": 0, "traces_needs_approval": 0,
                "tool_calls": 0, "tool_denied": 0, "tool_failed": 0,
                "llm_calls": 0, "llm_failed": 0,
                "tokens_in": 0, "tokens_out": 0, "cost_usd": 0,
                "approval_requests": 0, "approvals_granted": 0,
                "approvals_denied": 0,
            }
        agg = dept_aggregates[dept]
        for key in agg:
            agg[key] += getattr(row, key, 0) or 0

    for dept, agg in dept_aggregates.items():
        rollup = MetricsRollupHourly(
            bucket_start=bucket_start,
            department=dept,
            agent_id="*",
            metric_scope="dept",
            **agg,
        )
        db.merge(rollup)
        upserted += 1

    db.commit()

    logger.info(
        "rollup_computed",
        bucket=bucket_start.isoformat(),
        rows_upserted=upserted,
        departments=len(dept_aggregates),
    )

    return upserted


def run_rollup() -> int:
    """Entry point for Celery task or CLI."""
    from app.core.deps import get_sync_session

    session = get_sync_session()
    try:
        return compute_hourly_rollup(session)
    finally:
        session.close()
