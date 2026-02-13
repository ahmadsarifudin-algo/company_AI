"""
TaskExtractor — Intelligent task classification and extraction from chat messages.

Uses LLM (Gemini Flash) to:
1. Classify: Is this a task/request, greeting, question, or slot answer?
2. Extract: Convert vague messages into detailed, structured tasks.
3. Session-aware: Uses conversation history to avoid misclassifying
   slot answers as new tasks.
"""

import json
import structlog
import httpx

from app.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()

# ── Classification + Extraction Prompt ─────────────────────
EXTRACT_PROMPT = """You are a task extraction AI for an enterprise system.

Analyze the user message IN CONTEXT of the recent conversation history.

CLASSIFICATION RULES:
- "task": A NEW work request, instruction, or action item (e.g., "deploy ke staging", "buatkan laporan", "kirim email ke client")
- "greeting": Casual greetings, pleasantries (e.g., "halo", "apa kabar")
- "question": Information questions without action needed (e.g., "berapa jumlah user?")
- "followup": Follow-up or acknowledgment without new task (e.g., "ok terima kasih", "baik")
- "slot_answer": User is answering a clarifying question from the assistant. If the assistant just asked a question (format? department? period?) and the user replies with an answer, this is a slot_answer, NOT a new task.
- "confirmation": User is confirming or rejecting a summary (e.g., "ya", "ok lanjut", "tidak", "batal")

CRITICAL RULES:
1. If the assistant's last message contains a QUESTION, the user's reply is almost certainly "slot_answer" or "confirmation" — NOT a new "task"
2. Short replies like "PDF", "teknologi", "minggu ini", "ya", "ok" after a question = "slot_answer" or "confirmation"
3. Only classify as "task" if the message is a GENUINELY NEW request unrelated to the ongoing conversation
4. "ready_to_create" should be true ONLY when you have enough info to create a task (title, description, department). If the user hasn't confirmed yet, set to false.

EXTRACTION RULES (only for "task" type):
- Create a clear, specific title (max 100 chars)
- Expand vague instructions into comprehensive description with actionable steps
- Infer priority: P0=urgent/critical, P1=high/today, P2=normal, P3=low/whenever
- Use the sender's department context to add relevant details
- If the task is complex and NEEDS more info (format, period, etc), set "needs_clarification" to true

Respond in JSON only:
{
  "type": "task" | "greeting" | "question" | "followup" | "slot_answer" | "confirmation",
  "title": "Clear task title (only if type=task)",
  "description": "Detailed task description (only if type=task)",
  "priority": "P0|P1|P2|P3 (only if type=task, default P2)",
  "needs_clarification": true/false,
  "ready_to_create": true/false,
  "detected_slots": {"key": "value"}
}

IMPORTANT: Respond with ONLY the JSON object, no markdown, no explanation."""

# ── Known greetings for fast-path (skip LLM) ──────────────
GREETING_PATTERNS = {
    "halo", "hai", "hi", "hello", "hey", "selamat pagi", "selamat siang",
    "selamat sore", "selamat malam", "apa kabar", "pagi", "siang", "sore",
    "malam", "terima kasih", "makasih", "thanks",
    "thank you", "good morning", "good afternoon",
}

# Short affirmations — only greeting if NO active conversation
AFFIRMATION_PATTERNS = {
    "ok", "oke", "baik", "sip", "siap",
}

# ── Confirmation patterns (fast-path when conversation is active) ──
# These words confirm/reject a summary or proposal — never new tasks
CONFIRMATION_PATTERNS = {
    "ya", "iya", "iyaa", "benar", "betul", "ya benar", "ya betul",
    "lanjut", "ok lanjut", "oke lanjut", "setuju", "acc",
    "ya sudah", "ya oke", "ya ok", "oke gas", "gas", "jalan",
    "tidak", "batal", "cancel", "gak jadi", "nggak", "ngga",
    "bukan", "salah", "ulangi", "ganti",
}

# ── Post-task followup/acknowledgment patterns ──
FOLLOWUP_PATTERNS = {
    "oke", "ok", "baik", "sip", "siap", "noted", "terima kasih",
    "makasih", "thanks", "mantap", "oke terima kasih", "oke makasih",
    "ok thanks", "ok makasih", "baik terima kasih",
}


class TaskExtractor:
    """Classifies and extracts tasks from chat messages using LLM."""

    @classmethod
    async def classify_and_extract(
        cls,
        message_content: str,
        sender_name: str = "",
        department: str = "",
        session_history: list[dict] | None = None,
    ) -> dict:
        """Classify a message and extract task details if applicable.

        Args:
            message_content: The user's message text.
            sender_name: Name of the sender.
            department: Sender's department.
            session_history: Recent conversation history for context.

        Returns:
            dict with keys: type, title, description, priority,
                           needs_clarification, ready_to_create, detected_slots
        """
        if not message_content or not message_content.strip():
            return {"type": "greeting"}

        content = message_content.strip()
        normalized = content.lower().strip("!?.,")

        # ── Fast-path: pure greetings (skip LLM) ────
        if normalized in GREETING_PATTERNS:
            logger.info("task_extractor_fast_greeting", content=content[:50])
            return {"type": "greeting"}

        # ── Short affirmations: only greeting if no conversation context ──
        has_active_conversation = bool(session_history and len(session_history) > 1)
        if normalized in AFFIRMATION_PATTERNS and not has_active_conversation:
            logger.info("task_extractor_fast_greeting", content=content[:50])
            return {"type": "greeting"}

        # ── Confirmation fast-path: if conversation active + user confirms ──
        if has_active_conversation and normalized in CONFIRMATION_PATTERNS:
            logger.info("task_extractor_fast_confirmation", content=content[:50])
            return {
                "type": "confirmation",
                "needs_clarification": False,
                "ready_to_create": False,
            }

        # ── Followup fast-path: post-task acknowledgment ──
        if has_active_conversation and normalized in FOLLOWUP_PATTERNS:
            logger.info("task_extractor_fast_followup", content=content[:50])
            return {
                "type": "followup",
                "needs_clarification": False,
                "ready_to_create": False,
            }

        # ── LLM classification + extraction ───────────────
        try:
            return await cls._llm_extract(content, sender_name, department, session_history)
        except Exception as e:
            logger.error("task_extractor_llm_failed", error=str(e))
            # Fallback: treat as task but DO NOT auto-create (needs review)
            return {
                "type": "task",
                "title": content[:100],
                "description": content,
                "priority": "P2",
                "needs_clarification": True,
                "ready_to_create": False,
            }

    @classmethod
    async def _llm_extract(
        cls,
        content: str,
        sender_name: str,
        department: str,
        session_history: list[dict] | None = None,
    ) -> dict:
        """Call LLM to classify and extract task from message."""

        # Build context with conversation history
        history_text = ""
        if session_history:
            recent = session_history[-6:]  # last 6 messages for context
            history_lines = []
            for msg in recent:
                role = msg.get("role", "user")
                text = msg.get("content", "")[:200]  # truncate long messages
                history_lines.append(f"  {role}: {text}")
            history_text = "\nRecent conversation:\n" + "\n".join(history_lines)

        user_prompt = f"""Sender: {sender_name or 'Unknown'} (dept: {department or 'unknown'}){history_text}

Current message: {content}"""

        # Use Gemini Flash for speed and cost efficiency
        api_key = settings.GOOGLE_API_KEY
        if not api_key:
            logger.warning("task_extractor_no_api_key", fallback="raw_content")
            return {
                "type": "task",
                "title": content[:100],
                "description": content,
                "priority": "P2",
                "needs_clarification": True,
                "ready_to_create": False,
            }

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": EXTRACT_PROMPT + "\n\n" + user_prompt}]}
            ],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 500,
                "responseMimeType": "application/json",
            },
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()

        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]

        # Parse JSON response
        result = json.loads(text.strip())

        logger.info(
            "task_extractor_result",
            message_type=result.get("type"),
            title=result.get("title", "")[:50],
            needs_clarification=result.get("needs_clarification", False),
            ready_to_create=result.get("ready_to_create", False),
            content_preview=content[:50],
        )

        return {
            "type": result.get("type", "task"),
            "title": result.get("title", content[:100]),
            "description": result.get("description", content),
            "priority": result.get("priority", "P2"),
            "needs_clarification": result.get("needs_clarification", False),
            "ready_to_create": result.get("ready_to_create", False),
            "detected_slots": result.get("detected_slots", {}),
        }
