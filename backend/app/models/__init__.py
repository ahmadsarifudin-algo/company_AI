"""Models package — import all models for Alembic discovery."""

from app.models.agent import Agent
from app.models.audit import AuditEvent, AuditLog  # AuditLog = backward compat alias
from app.models.base import Base
from app.models.knowledge import KnowledgeDocument
from app.models.metrics_rollup import MetricsRollupHourly
from app.models.prompt_history import PromptHistory
from app.models.task import Task
from app.models.trace_index import TraceIndex
from app.models.user import User

__all__ = [
    "Base",
    "User",
    "Agent",
    "Task",
    "AuditEvent",
    "AuditLog",
    "TraceIndex",
    "MetricsRollupHourly",
    "KnowledgeDocument",
    "PromptHistory",
]

