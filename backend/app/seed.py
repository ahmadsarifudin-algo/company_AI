"""
Seed Script — Populate database with initial 63 agents across 7 departments.

Run: python -m app.seed
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import async_session
from app.core.security import hash_password
from app.models.agent import Agent
from app.models.user import User

# ── All 63 Agents ────────────────────────────
AGENTS_DATA = [
    # Enterprise (3)
    ("Global Supervisor", "enterprise", "advanced"),
    ("Scheduling Agent", "enterprise", "standard"),
    ("Communication Agent", "enterprise", "standard"),
    # Tech (11)
    ("Tech Supervisor", "tech", "advanced"),
    ("Product Analyst Agent", "tech", "standard"),
    ("Architect Agent", "tech", "advanced"),
    ("Backend Engineer Agent", "tech", "code"),
    ("Frontend Engineer Agent", "tech", "code"),
    ("QA Agent", "tech", "standard"),
    ("DevOps Agent", "tech", "standard"),
    ("SRE Agent", "tech", "standard"),
    ("Security Agent", "tech", "standard"),
    ("Data Engineer Agent", "tech", "standard"),
    ("Technical Writer Agent", "tech", "nano"),
    # Finance (9)
    ("Finance Supervisor", "finance", "advanced"),
    ("Accounting Agent", "finance", "standard"),
    ("Budget Planning Agent", "finance", "standard"),
    ("Forecasting Agent", "finance", "advanced"),
    ("Audit Agent", "finance", "standard"),
    ("Risk & Compliance Agent", "finance", "advanced"),
    ("Treasury Agent", "finance", "standard"),
    ("Invoicing Agent", "finance", "nano"),
    ("Tax Agent", "finance", "standard"),
    # HR (8)
    ("HR Supervisor", "hr", "advanced"),
    ("Recruitment Agent", "hr", "standard"),
    ("Onboarding Agent", "hr", "nano"),
    ("Payroll Validation Agent", "hr", "standard"),
    ("Performance Analytics Agent", "hr", "standard"),
    ("HR Compliance Agent", "hr", "standard"),
    ("Training & Development Agent", "hr", "standard"),
    ("Benefits Administration Agent", "hr", "nano"),
    # Sales (6)
    ("Sales Supervisor", "sales", "advanced"),
    ("Lead Scoring Agent", "sales", "standard"),
    ("Deal Intelligence Agent", "sales", "standard"),
    ("Sales Forecasting Agent", "sales", "standard"),
    ("Pricing Optimization Agent", "sales", "advanced"),
    ("Contract Review Agent", "sales", "standard"),
    # Marketing (8)
    ("Marketing Supervisor", "marketing", "advanced"),
    ("Content Creator Agent", "marketing", "standard"),
    ("Content Maker & Editing Agent", "marketing", "vision"),
    ("Social Media Agent", "marketing", "standard"),
    ("Customer Relationship Agent", "marketing", "standard"),
    ("Customer Success Agent", "marketing", "standard"),
    ("Campaign Analytics Agent", "marketing", "standard"),
    ("SEO & SEM Agent", "marketing", "standard"),
    # Legal (7)
    ("Legal Supervisor", "legal", "advanced"),
    ("Contract Drafting Agent", "legal", "standard"),
    ("Contract Review Agent", "legal", "advanced"),
    ("Regulatory Compliance Agent", "legal", "standard"),
    ("Data Protection Agent", "legal", "standard"),
    ("IP Management Agent", "legal", "nano"),
    ("Litigation Support Agent", "legal", "standard"),
    # BizDev (7)
    ("BizDev Supervisor", "bizdev", "advanced"),
    ("Market Research Agent", "bizdev", "standard"),
    ("Competitive Intelligence Agent", "bizdev", "standard"),
    ("Partnership Evaluation Agent", "bizdev", "standard"),
    ("Go-to-Market Agent", "bizdev", "standard"),
    ("Business Modeling Agent", "bizdev", "advanced"),
    ("Strategic Planning Agent", "bizdev", "advanced"),
]

# ── Default Admin User ───────────────────────
ADMIN_USER = {
    "email": "admin@company.ai",
    "name": "System Admin",
    "password": "admin123",
    "department": "enterprise",
    "role": "admin",
}


async def seed_database():
    """Populate database with agents and admin user."""
    async with async_session() as session:
        # Check if already seeded
        result = await session.execute(select(Agent).limit(1))
        if result.scalar_one_or_none():
            print("⚠️  Database already seeded. Skipping.")
            return

        # Create admin user
        admin = User(
            email=ADMIN_USER["email"],
            name=ADMIN_USER["name"],
            hashed_password=hash_password(ADMIN_USER["password"]),
            department=ADMIN_USER["department"],
            role=ADMIN_USER["role"],
        )
        session.add(admin)
        await session.flush()
        print(f"✅ Admin user created: {admin.email}")

        # Create all 63 agents
        for name, dept, tier in AGENTS_DATA:
            agent = Agent(name=name, department=dept, tier=tier)
            session.add(agent)

        await session.commit()
        print(f"✅ Seeded {len(AGENTS_DATA)} agents across 7 departments + enterprise")
        print("   Departments: enterprise(3), tech(11), finance(9), hr(8), sales(6), marketing(8), legal(7), bizdev(7)")


if __name__ == "__main__":
    asyncio.run(seed_database())
