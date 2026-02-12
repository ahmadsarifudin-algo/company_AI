"""
DataAccessLayer (DAL) — Single Chokepoint for all database access.

Every data read/write by agents MUST go through this layer.
It enforces: access logging, department scoping, and future policy+masking hooks.

No agent or service may directly construct SQLAlchemy queries.
"""

from typing import Any

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class PolicyDenied(Exception):
    """Raised when a data access is denied by policy."""

    def __init__(self, resource: str, reason: str, agent_name: str = ""):
        self.resource = resource
        self.reason = reason
        self.agent_name = agent_name
        super().__init__(f"Data access denied: resource='{resource}' — {reason}")


class DataAccessLayer:
    """Sole gateway for all database operations by agents.

    Enforces:
    1. Department scoping (agents can only see their department's data)
    2. Access logging (all reads/writes are audited)
    3. Future: ABAC policy evaluation and field masking

    Usage:
        dal = DataAccessLayer(db_session)
        results = await dal.read(ctx, "agents", filters={"department": "tech"})
        await dal.write(ctx, "tasks", data={...})
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def read(
        self,
        ctx: "AgentContext",
        resource: str,
        model_class: Any = None,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> list[Any]:
        """Read data with policy enforcement and audit logging.

        Args:
            ctx: Agent context for tracing and department scope.
            resource: Resource name (e.g. "agents", "tasks", "knowledge_documents").
            model_class: SQLAlchemy model class to query.
            filters: Additional query filters as {column_name: value}.
            limit: Max rows to return.

        Returns:
            List of model instances.

        Raises:
            PolicyDenied: If access is denied by policy.
        """
        if model_class is None:
            raise PolicyDenied(resource, "No model class provided", ctx.agent_name)

        logger.info(
            "dal_read_start",
            trace_id=ctx.trace_id,
            span_id=ctx.span_id,
            agent=ctx.agent_name,
            department=ctx.department,
            resource=resource,
            filters=filters,
        )

        # Build query
        query = select(model_class)

        # Apply department scoping if model has a department column
        if hasattr(model_class, "department"):
            query = query.where(model_class.department == ctx.department)

        # Apply additional filters
        if filters:
            for col_name, value in filters.items():
                if hasattr(model_class, col_name):
                    query = query.where(getattr(model_class, col_name) == value)

        query = query.limit(limit)

        result = await self.db.execute(query)
        rows = list(result.scalars().all())

        logger.info(
            "dal_read_complete",
            trace_id=ctx.trace_id,
            agent=ctx.agent_name,
            resource=resource,
            row_count=len(rows),
        )

        return rows

    async def read_one(
        self,
        ctx: "AgentContext",
        resource: str,
        model_class: Any,
        record_id: str,
    ) -> Any | None:
        """Read a single record by ID.

        Args:
            ctx: Agent context.
            resource: Resource name.
            model_class: SQLAlchemy model class.
            record_id: Primary key value.

        Returns:
            Model instance or None.
        """
        logger.info(
            "dal_read_one",
            trace_id=ctx.trace_id,
            agent=ctx.agent_name,
            resource=resource,
            record_id=record_id,
        )

        query = select(model_class).where(model_class.id == record_id)

        # Department scoping
        if hasattr(model_class, "department"):
            query = query.where(model_class.department == ctx.department)

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def write(
        self,
        ctx: "AgentContext",
        resource: str,
        model_instance: Any,
    ) -> Any:
        """Write (insert) a record with policy enforcement.

        Args:
            ctx: Agent context.
            resource: Resource name.
            model_instance: SQLAlchemy model instance to insert.

        Returns:
            The inserted model instance.
        """
        logger.info(
            "dal_write",
            trace_id=ctx.trace_id,
            span_id=ctx.span_id,
            agent=ctx.agent_name,
            department=ctx.department,
            resource=resource,
        )

        # Enforce department assignment
        if hasattr(model_instance, "department"):
            model_instance.department = ctx.department

        self.db.add(model_instance)
        await self.db.flush()

        logger.info(
            "dal_write_complete",
            trace_id=ctx.trace_id,
            agent=ctx.agent_name,
            resource=resource,
            record_id=getattr(model_instance, "id", "unknown"),
        )

        return model_instance

    async def update(
        self,
        ctx: "AgentContext",
        resource: str,
        model_instance: Any,
        updates: dict[str, Any],
    ) -> Any:
        """Update a record's fields.

        Args:
            ctx: Agent context.
            resource: Resource name.
            model_instance: Existing model instance.
            updates: Dict of {field: new_value} to apply.

        Returns:
            Updated model instance.
        """
        logger.info(
            "dal_update",
            trace_id=ctx.trace_id,
            agent=ctx.agent_name,
            resource=resource,
            record_id=getattr(model_instance, "id", "unknown"),
            fields=list(updates.keys()),
        )

        for field_name, value in updates.items():
            if hasattr(model_instance, field_name):
                setattr(model_instance, field_name, value)

        await self.db.flush()
        return model_instance

    async def delete(
        self,
        ctx: "AgentContext",
        resource: str,
        model_instance: Any,
    ) -> None:
        """Delete a record.

        Args:
            ctx: Agent context.
            resource: Resource name.
            model_instance: Model instance to delete.
        """
        logger.info(
            "dal_delete",
            trace_id=ctx.trace_id,
            agent=ctx.agent_name,
            resource=resource,
            record_id=getattr(model_instance, "id", "unknown"),
        )

        await self.db.delete(model_instance)
        await self.db.flush()

    async def execute_raw(
        self,
        ctx: "AgentContext",
        resource: str,
        sql: str,
        params: dict[str, Any] | None = None,
    ) -> list[Any]:
        """Execute a raw SQL query (restricted — audit logged).

        This should be used sparingly. All raw queries are logged.

        Args:
            ctx: Agent context.
            resource: Resource category for audit.
            sql: Raw SQL string.
            params: Query parameters.

        Returns:
            List of result rows.
        """
        logger.warning(
            "dal_raw_query",
            trace_id=ctx.trace_id,
            agent=ctx.agent_name,
            resource=resource,
            sql_preview=sql[:100],
        )

        result = await self.db.execute(text(sql), params or {})
        return list(result.fetchall())
