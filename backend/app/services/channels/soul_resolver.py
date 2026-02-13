"""
SoulResolver — Resolve the correct SOUL prompt for a user.

Flow:
1. Identity Linker: channel+peer_id → User record
2. Soul Resolver: User → active_soul → compiled system prompt
3. Default SOUL for unknown users or users without active soul
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger()

# Default SOUL for unknown users / users without custom soul
DEFAULT_SOUL_PERSONALITY = (
    "Kamu adalah asisten AI perusahaan yang ramah dan informatif. "
    "Kamu selalu menjawab dengan sabar, hangat, dan memberikan "
    "penjelasan yang mudah dipahami. Gunakan emoji sesekali. "
    "Jika tidak tahu jawaban, jujur katakan."
)
DEFAULT_SOUL_BOUNDARIES = (
    "Jangan mengarang data yang tidak ada. "
    "Jangan output JSON atau structured data kecuali diminta eksplisit. "
    "Jangan bahas topik sensitif (politik, SARA)."
)
DEFAULT_GREETING = "Halo! 😊 Ada yang bisa saya bantu?"

# ── Task Creation Rules (injected into system prompt) ──────
TASK_CREATION_RULES = """
TASK CREATION RULES:
- JANGAN langsung membuat task. Kumpulkan informasi dulu.
- Tanya SATU pertanyaan per pesan untuk mengumpulkan detail yang kurang.
- Jika departemen user sudah diketahui, JANGAN tanya ulang.
- Jika user menjawab pertanyaan kamu (format, periode, detail), itu BUKAN task baru — itu jawaban slot.
- Setelah semua info terkumpul, KONFIRMASI rangkuman sebelum eksekusi.
- Hanya eksekusi setelah user mengkonfirmasi (misalnya "ya", "ok", "lanjut").
- Jika user belum terdaftar (unknown), jawab sopan bahwa mereka perlu didaftarkan dulu.
- User HANYA bisa membuat task untuk departemennya sendiri.
"""


class SoulResolver:
    """Resolve SOUL system prompt for a given user context."""

    @classmethod
    def resolve(
        cls,
        user: "User | None",
        channel: str,
    ) -> str:
        """Build the complete SOUL-based system prompt.

        Args:
            user: User record or None if unknown.
            channel: Channel name (telegram, whatsapp, etc).

        Returns:
            Compiled system prompt string with SOUL personality.
        """
        channel_name = channel.capitalize()

        # Get SOUL personality
        soul_text = DEFAULT_SOUL_PERSONALITY
        soul_boundaries = DEFAULT_SOUL_BOUNDARIES
        user_name = None
        department = None

        if user is not None:
            user_name = user.name
            department = user.department

            # Try to load active soul
            active_soul = cls._get_active_soul(user)
            if active_soul:
                soul_text = active_soul.get("personality", DEFAULT_SOUL_PERSONALITY)
                soul_boundaries = active_soul.get("boundaries", DEFAULT_SOUL_BOUNDARIES)
                logger.info(
                    "soul_resolved_custom",
                    user=user_name,
                    soul_name=active_soul.get("name", "custom"),
                )
            else:
                logger.info("soul_resolved_default", user=user_name)
        else:
            logger.info("soul_resolved_unknown_user", channel=channel)

        # Build system prompt
        return cls._compile_prompt(
            soul_text=soul_text,
            soul_boundaries=soul_boundaries,
            user_name=user_name,
            department=department,
            channel_name=channel_name,
        )

    @classmethod
    def _get_active_soul(cls, user) -> dict | None:
        """Get user's active soul as a dict.

        Uses the active_soul_id from user record to load
        the soul configuration. For now, checks in-memory;
        DB integration will be added when session is available.
        """
        # Check if user has active_soul_id attribute
        active_soul_id = getattr(user, "active_soul_id", None)
        if not active_soul_id:
            return None

        # The soul data will be loaded by the orchestrator
        # via SQLAlchemy relationship or direct query.
        # For now, return None to use default.
        # This will be enhanced when the full DB integration is ready.
        return None

    @classmethod
    def _compile_prompt(
        cls,
        soul_text: str,
        soul_boundaries: str,
        user_name: str | None,
        department: str | None,
        channel_name: str,
    ) -> str:
        """Compile SOUL fields into a complete system prompt."""
        lines = [
            "PERSONALITY:",
            soul_text,
            "",
            "RULES:",
            "- Respond in the SAME LANGUAGE the user writes in",
            f"- Keep responses concise and conversational (this is {channel_name} chat)",
            "- Do NOT output JSON, task plans, or structured data unless explicitly asked",
            "- Be friendly, direct, and helpful",
            "- If you don't know something, say so honestly",
            "- Use simple formatting appropriate for chat",
        ]

        if user_name:
            lines.append(f"- Address the user as {user_name}")
        if department:
            lines.append(f"- The user is from the {department} department")
            lines.append(f"- User HANYA bisa membuat task untuk departemen {department}")

        if soul_boundaries:
            lines.append("")
            lines.append("BOUNDARIES:")
            lines.append(soul_boundaries)

        # Add task creation rules for chat channels
        if channel_name.lower() in ("telegram", "whatsapp"):
            lines.append("")
            lines.append(TASK_CREATION_RULES)

        return "\n".join(lines)
