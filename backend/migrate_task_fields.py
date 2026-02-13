"""Quick migration script to add new task columns."""
import asyncio
from app.core.deps import async_session
from sqlalchemy import text

COLUMNS = [
    ("channel", "VARCHAR(20)"),
    ("sender_name", "VARCHAR(200)"),
    ("sender_identifier", "VARCHAR(200)"),
    ("agent_response", "TEXT"),
    ("trace_id", "VARCHAR(36)"),
    ("original_message", "TEXT"),
]

async def migrate():
    async with async_session() as db:
        for col, coltype in COLUMNS:
            try:
                await db.execute(text(f"ALTER TABLE tasks ADD COLUMN IF NOT EXISTS {col} {coltype}"))
                await db.commit()
                print(f"+ {col} added")
            except Exception as e:
                await db.rollback()
                print(f"  {col} skipped: {e}")

        for idx, col in [("ix_tasks_channel", "channel"), ("ix_tasks_trace_id", "trace_id")]:
            try:
                await db.execute(text(f"CREATE INDEX IF NOT EXISTS {idx} ON tasks ({col})"))
                await db.commit()
                print(f"+ index {idx} created")
            except Exception as e:
                await db.rollback()
                print(f"  index {idx} skipped: {e}")

    print("Migration complete!")

asyncio.run(migrate())
