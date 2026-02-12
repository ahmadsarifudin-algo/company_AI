"""Create database tables and fix bcrypt compatibility."""
import sys
sys.path.insert(0, ".")
import asyncio

async def setup():
    # Import all models to register them
    from app.models import Base
    from app.core.deps import engine
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    print("All tables created successfully!")
    
    # List tables
    from sqlalchemy import text
    async with engine.connect() as conn:
        result = await conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ))
        tables = [row[0] for row in result]
        print(f"Tables in database: {tables}")
    
    await engine.dispose()

asyncio.run(setup())
