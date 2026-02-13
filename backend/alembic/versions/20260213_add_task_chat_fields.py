"""add_task_chat_fields

Add chat-originated task fields to tasks table:
- channel, sender_name, sender_identifier
- agent_response, trace_id, original_message
"""

from alembic import op
import sqlalchemy as sa

revision = "20260213_add_task_chat_fields"
down_revision = None  # Will be adjusted based on existing migrations
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("channel", sa.String(20), nullable=True))
    op.add_column("tasks", sa.Column("sender_name", sa.String(200), nullable=True))
    op.add_column("tasks", sa.Column("sender_identifier", sa.String(200), nullable=True))
    op.add_column("tasks", sa.Column("agent_response", sa.Text(), nullable=True))
    op.add_column("tasks", sa.Column("trace_id", sa.String(36), nullable=True))
    op.add_column("tasks", sa.Column("original_message", sa.Text(), nullable=True))

    op.create_index("ix_tasks_channel", "tasks", ["channel"])
    op.create_index("ix_tasks_trace_id", "tasks", ["trace_id"])


def downgrade() -> None:
    op.drop_index("ix_tasks_trace_id", table_name="tasks")
    op.drop_index("ix_tasks_channel", table_name="tasks")

    op.drop_column("tasks", "original_message")
    op.drop_column("tasks", "trace_id")
    op.drop_column("tasks", "agent_response")
    op.drop_column("tasks", "sender_identifier")
    op.drop_column("tasks", "sender_name")
    op.drop_column("tasks", "channel")
