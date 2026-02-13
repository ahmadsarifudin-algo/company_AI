"""
Souls API — CRUD endpoints for per-user SOUL personality management.

Endpoints:
- GET  /souls/templates     — List available SOUL templates
- GET  /souls/my            — List current user's souls
- POST /souls/my            — Create a new soul (custom or from template)
- PUT  /souls/my/{soul_id}  — Update an existing soul
- POST /souls/my/{soul_id}/activate   — Activate a soul
- DELETE /souls/my/{soul_id}          — Delete a soul
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import structlog

logger = structlog.get_logger()

router = APIRouter(prefix="/souls", tags=["souls"])


# ── Request/Response Schemas ────────────────────────

class SoulTemplateResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    tone: str
    language_style: str
    personality: str
    boundaries: Optional[str] = None
    greeting: Optional[str] = None
    icon: Optional[str] = None


class UserSoulResponse(BaseModel):
    id: str
    name: str
    tone: str
    language_style: str
    personality: str
    boundaries: Optional[str] = None
    greeting: Optional[str] = None
    template_id: Optional[str] = None
    is_active: bool


class CreateSoulRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    tone: str = Field(default="friendly", max_length=50)
    language_style: str = Field(default="auto", max_length=50)
    personality: str = Field(..., min_length=10)
    boundaries: Optional[str] = None
    greeting: Optional[str] = Field(default=None, max_length=500)
    template_id: Optional[str] = Field(
        default=None,
        description="If provided, clone from this template",
    )


class UpdateSoulRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=100)
    tone: Optional[str] = Field(default=None, max_length=50)
    language_style: Optional[str] = Field(default=None, max_length=50)
    personality: Optional[str] = None
    boundaries: Optional[str] = None
    greeting: Optional[str] = Field(default=None, max_length=500)


# ── In-memory store (until full DB session integration) ──

_soul_templates: list[dict] = [
    {
        "id": "tpl-friendly-default",
        "name": "Ramah & Informatif",
        "description": "Hangat, sabar, selalu jelaskan dengan detail.",
        "tone": "friendly",
        "language_style": "auto",
        "personality": "Kamu adalah asisten AI yang ramah dan informatif. "
                       "Kamu selalu menjawab dengan sabar, hangat, dan memberikan "
                       "penjelasan yang mudah dipahami.",
        "boundaries": "Jangan mengarang data. Jangan output JSON kecuali diminta.",
        "greeting": "Halo! 😊 Ada yang bisa saya bantu?",
        "icon": "😊",
    },
    {
        "id": "tpl-formal-exec",
        "name": "Formal Executive",
        "description": "Ringkas, profesional, langsung ke inti.",
        "tone": "formal",
        "language_style": "auto",
        "personality": "Kamu adalah asisten AI profesional. Jawab dengan ringkas, "
                       "efisien, dan langsung ke inti masalah.",
        "boundaries": "Jangan mengarang data. Hindari emoji berlebihan.",
        "greeting": "Selamat datang. Ada yang perlu saya bantu?",
        "icon": "👔",
    },
    {
        "id": "tpl-casual",
        "name": "Casual Santai",
        "description": "Bahasa santai, sedikit humor.",
        "tone": "casual",
        "language_style": "auto",
        "personality": "Kamu adalah asisten AI yang santai dan asik. "
                       "Bicara seperti teman kerja yang pintar.",
        "boundaries": "Jangan mengarang data. Jangan terlalu kaku.",
        "greeting": "Yoo! Ada yang bisa dibantu? 🤙",
        "icon": "🤙",
    },
    {
        "id": "tpl-technical",
        "name": "Teknikal",
        "description": "Detail teknis, precise.",
        "tone": "technical",
        "language_style": "auto",
        "personality": "Kamu adalah asisten AI teknikal. Berikan jawaban detail, "
                       "akurat, dan teknis.",
        "boundaries": "Jangan mengarang data. Pastikan akurasi teknis.",
        "greeting": "Ready. What can I help you with?",
        "icon": "🔧",
    },
    {
        "id": "tpl-bilingual",
        "name": "Bilingual ID-EN",
        "description": "Campuran Indonesia-English natural.",
        "tone": "bilingual",
        "language_style": "bilingual",
        "personality": "Kamu adalah asisten AI bilingual. Bicara dengan campuran "
                       "bahasa Indonesia dan English secara natural.",
        "boundaries": "Jangan mengarang data. Keep it natural.",
        "greeting": "Hey! Mau tanya apa nih? Feel free to ask anything 🌏",
        "icon": "🌏",
    },
]

_user_souls: dict[str, list[dict]] = {}  # user_id → list of souls


# ── Endpoints ───────────────────────────────────────

@router.get("/templates", response_model=list[SoulTemplateResponse])
async def list_templates():
    """List all available SOUL templates."""
    return _soul_templates


@router.get("/my", response_model=list[UserSoulResponse])
async def list_my_souls(user_id: str = "default-user"):
    """List current user's souls."""
    return _user_souls.get(user_id, [])


@router.post("/my", response_model=UserSoulResponse, status_code=201)
async def create_soul(body: CreateSoulRequest, user_id: str = "default-user"):
    """Create a new soul (custom or cloned from template)."""
    # If template_id provided, clone from template
    if body.template_id:
        template = next(
            (t for t in _soul_templates if t["id"] == body.template_id), None,
        )
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

    soul = {
        "id": f"soul_{uuid4().hex[:12]}",
        "name": body.name,
        "tone": body.tone,
        "language_style": body.language_style,
        "personality": body.personality,
        "boundaries": body.boundaries,
        "greeting": body.greeting,
        "template_id": body.template_id,
        "is_active": False,
    }

    if user_id not in _user_souls:
        _user_souls[user_id] = []
    _user_souls[user_id].append(soul)

    logger.info("soul_created", user_id=user_id, soul_id=soul["id"], name=soul["name"])
    return soul


@router.put("/my/{soul_id}", response_model=UserSoulResponse)
async def update_soul(soul_id: str, body: UpdateSoulRequest, user_id: str = "default-user"):
    """Update an existing soul."""
    souls = _user_souls.get(user_id, [])
    soul = next((s for s in souls if s["id"] == soul_id), None)
    if not soul:
        raise HTTPException(status_code=404, detail="Soul not found")

    if body.name is not None:
        soul["name"] = body.name
    if body.tone is not None:
        soul["tone"] = body.tone
    if body.language_style is not None:
        soul["language_style"] = body.language_style
    if body.personality is not None:
        soul["personality"] = body.personality
    if body.boundaries is not None:
        soul["boundaries"] = body.boundaries
    if body.greeting is not None:
        soul["greeting"] = body.greeting

    logger.info("soul_updated", user_id=user_id, soul_id=soul_id)
    return soul


@router.post("/my/{soul_id}/activate", response_model=UserSoulResponse)
async def activate_soul(soul_id: str, user_id: str = "default-user"):
    """Activate a soul (deactivates all others)."""
    souls = _user_souls.get(user_id, [])
    target = None

    for s in souls:
        if s["id"] == soul_id:
            s["is_active"] = True
            target = s
        else:
            s["is_active"] = False

    if not target:
        raise HTTPException(status_code=404, detail="Soul not found")

    logger.info("soul_activated", user_id=user_id, soul_id=soul_id, name=target["name"])
    return target


@router.delete("/my/{soul_id}", status_code=204)
async def delete_soul(soul_id: str, user_id: str = "default-user"):
    """Delete a soul."""
    souls = _user_souls.get(user_id, [])
    soul = next((s for s in souls if s["id"] == soul_id), None)
    if not soul:
        raise HTTPException(status_code=404, detail="Soul not found")

    souls.remove(soul)
    logger.info("soul_deleted", user_id=user_id, soul_id=soul_id)
