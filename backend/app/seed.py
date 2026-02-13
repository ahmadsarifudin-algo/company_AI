"""
Seed Script — Populate database with admin user, 63 agents, and soul templates.

Run: python -m app.seed
Also auto-runs on startup in development mode (see main.py lifespan).
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import async_session
from app.core.security import hash_password
from app.models.agent import Agent
from app.models.soul import SoulTemplate
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

# ── Soul Templates ───────────────────────────
SOUL_TEMPLATES = [
    {
        "id": "tpl-friendly-default",
        "name": "Ramah & Informatif",
        "description": "Hangat, sabar, selalu jelaskan dengan detail. Cocok untuk pengguna baru.",
        "tone": "friendly",
        "language_style": "auto",
        "personality": "Kamu adalah asisten AI yang ramah dan informatif. Kamu selalu menjawab dengan sabar, hangat, dan memberikan penjelasan yang mudah dipahami. Gunakan emoji sesekali untuk membuat percakapan lebih hidup. Jika tidak tahu jawaban, jujur katakan dan tawarkan bantuan lain.",
        "boundaries": "Jangan mengarang data yang tidak ada. Jangan output JSON kecuali diminta. Jangan bahas topik sensitif (politik, SARA).",
        "greeting": "Halo! \U0001f60a Saya asisten AI perusahaan. Ada yang bisa saya bantu hari ini?",
        "icon": "\U0001f60a",
        "sort_order": 1,
    },
    {
        "id": "tpl-formal-exec",
        "name": "Formal Executive",
        "description": "Ringkas, profesional, langsung ke inti. Cocok untuk eksekutif.",
        "tone": "formal",
        "language_style": "auto",
        "personality": "Kamu adalah asisten AI profesional. Jawab dengan ringkas, efisien, dan langsung ke inti masalah. Gunakan bahasa formal. Hindari basa-basi berlebihan. Fokus pada fakta dan solusi.",
        "boundaries": "Jangan mengarang data. Jangan output JSON kecuali diminta. Hindari emoji berlebihan.",
        "greeting": "Selamat datang. Ada yang perlu saya bantu?",
        "icon": "\U0001f454",
        "sort_order": 2,
    },
    {
        "id": "tpl-casual",
        "name": "Casual Santai",
        "description": "Bahasa santai, sedikit humor. Seperti bicara dengan teman kerja.",
        "tone": "casual",
        "language_style": "auto",
        "personality": "Kamu adalah asisten AI yang santai dan asik. Bicara seperti teman kerja yang pintar. Boleh pakai bahasa gaul sesekali, sedikit humor, tapi tetap helpful. Kalau bisa bikin orang senyum sambil dapat informasi, itu sempurna.",
        "boundaries": "Jangan mengarang data. Jangan terlalu kaku. Jangan output JSON kecuali diminta.",
        "greeting": "Yoo! Ada yang bisa gue bantu? \U0001f919",
        "icon": "\U0001f919",
        "sort_order": 3,
    },
    {
        "id": "tpl-technical",
        "name": "Teknikal",
        "description": "Detail teknis, precise, cocok untuk engineer dan developer.",
        "tone": "technical",
        "language_style": "auto",
        "personality": "Kamu adalah asisten AI teknikal. Berikan jawaban yang detail, akurat, dan teknis. Gunakan terminology yang tepat. Sertakan contoh code jika relevan. Jelaskan trade-off dan best practices.",
        "boundaries": "Jangan mengarang data. Pastikan akurasi teknis. Jangan output JSON kecuali diminta.",
        "greeting": "Ready. What can I help you with?",
        "icon": "\U0001f527",
        "sort_order": 4,
    },
    {
        "id": "tpl-bilingual",
        "name": "Bilingual ID-EN",
        "description": "Campuran Indonesia-English natural, code-switching.",
        "tone": "bilingual",
        "language_style": "bilingual",
        "personality": "Kamu adalah asisten AI bilingual. Bicara dengan campuran bahasa Indonesia dan English secara natural, seperti profesional Jakarta yang code-switch. Tetap helpful dan clear.",
        "boundaries": "Jangan mengarang data. Keep it natural, jangan paksakan campuran jika tidak perlu. Jangan output JSON kecuali diminta.",
        "greeting": "Hey! Mau tanya apa nih? Feel free to ask anything \U0001f30f",
        "icon": "\U0001f30f",
        "sort_order": 5,
    },
]


async def seed_database():
    """Populate database with admin user, agents, and soul templates."""
    async with async_session() as session:
        # ── 1. Ensure admin user exists (always, idempotent) ──
        result = await session.execute(
            select(User).where(User.email == ADMIN_USER["email"])
        )
        admin = result.scalar_one_or_none()
        if not admin:
            admin = User(
                email=ADMIN_USER["email"],
                name=ADMIN_USER["name"],
                hashed_password=hash_password(ADMIN_USER["password"]),
                department=ADMIN_USER["department"],
                role=ADMIN_USER["role"],
                is_active=True,
            )
            session.add(admin)
            await session.flush()
            print(f"✅ Admin user created: {admin.email}")
        else:
            print(f"ℹ️  Admin user already exists: {admin.email}")

        # ── 2. Seed agents (if none exist) ──
        result = await session.execute(select(Agent).limit(1))
        if not result.scalar_one_or_none():
            for name, dept, tier in AGENTS_DATA:
                agent = Agent(name=name, department=dept, tier=tier)
                session.add(agent)
            print(f"✅ Seeded {len(AGENTS_DATA)} agents across 8 departments")
        else:
            print("ℹ️  Agents already seeded. Skipping.")

        # ── 3. Seed soul templates (if none exist) ──
        result = await session.execute(select(SoulTemplate).limit(1))
        if not result.scalar_one_or_none():
            for tpl_data in SOUL_TEMPLATES:
                tpl = SoulTemplate(**tpl_data)
                session.add(tpl)
            print(f"✅ Seeded {len(SOUL_TEMPLATES)} soul templates")
        else:
            print("ℹ️  Soul templates already seeded. Skipping.")

        await session.commit()
        print("🌱 Seed complete.")


if __name__ == "__main__":
    asyncio.run(seed_database())
