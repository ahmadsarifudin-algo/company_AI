"""Create an admin user for testing — uses the app's own hash_password."""
import asyncio
from app.core.deps import get_db
from app.core.security import hash_password
from app.models.user import User
from sqlalchemy import select


async def main():
    async for db in get_db():
        result = await db.execute(select(User).where(User.email == "admin@company.ai"))
        user = result.scalar_one_or_none()
        if user:
            print(f"Admin exists: {user.email} role={user.role} active={user.is_active}")
            # Re-hash password using passlib to fix compat
            user.hashed_password = hash_password("admin123")
            user.is_active = True
            await db.commit()
            print("Password re-hashed with passlib")
        else:
            new_user = User(
                email="admin@company.ai",
                name="Admin",
                department="tech",
                role="admin",
                hashed_password=hash_password("admin123"),
                is_active=True,
            )
            db.add(new_user)
            await db.commit()
            print("Admin created: admin@company.ai / admin123")


asyncio.run(main())
