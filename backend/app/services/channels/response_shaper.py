"""
ResponseShaper — Parse dual-output LLM responses.

Splits LLM output into:
1. human_reply — Natural language sent to user
2. agent_json — Structured JSON stored internally for orchestration

Uses ---INTENT--- separator to split the two sections.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger()

INTENT_SEPARATOR = "---INTENT---"


@dataclass
class ShapedResponse:
    """Result of shaping an LLM response."""

    human_reply: str
    agent_intent: dict = field(default_factory=dict)
    raw_output: str = ""
    parse_success: bool = False


class ResponseShaper:
    """Parse dual-output LLM responses into human reply + agent JSON."""

    @classmethod
    def shape(cls, raw_llm_output: str) -> ShapedResponse:
        """Parse LLM output that contains two sections.

        Expected format:
            Natural language reply here...
            ---INTENT---
            {"intent": "query", "department": "finance", ...}

        Args:
            raw_llm_output: Raw text from LLM.

        Returns:
            ShapedResponse with human_reply and agent_intent.
        """
        if not raw_llm_output:
            return ShapedResponse(
                human_reply="Maaf, saya tidak bisa memproses permintaan ini.",
                raw_output="",
            )

        # Try to split by separator
        if INTENT_SEPARATOR in raw_llm_output:
            parts = raw_llm_output.split(INTENT_SEPARATOR, 1)
            human_reply = parts[0].strip()
            intent_raw = parts[1].strip() if len(parts) > 1 else ""

            # Parse JSON intent
            agent_intent = cls._parse_intent_json(intent_raw)

            return ShapedResponse(
                human_reply=human_reply,
                agent_intent=agent_intent,
                raw_output=raw_llm_output,
                parse_success=bool(agent_intent),
            )

        # No separator found — treat entire output as human reply
        # Try to detect if output is pure JSON (old behavior)
        stripped = raw_llm_output.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            # LLM output pure JSON — convert to human-readable
            logger.warning("response_shaper_raw_json_detected")
            try:
                data = json.loads(stripped)
                summary = data.get("summary", "")
                if summary:
                    return ShapedResponse(
                        human_reply=summary,
                        agent_intent=data,
                        raw_output=raw_llm_output,
                        parse_success=True,
                    )
            except json.JSONDecodeError:
                pass

        # Fallback: entire output is the human reply
        return ShapedResponse(
            human_reply=raw_llm_output.strip(),
            agent_intent=cls._build_default_intent(),
            raw_output=raw_llm_output,
            parse_success=False,
        )

    @classmethod
    def _parse_intent_json(cls, raw: str) -> dict:
        """Parse the intent JSON section."""
        if not raw:
            return cls._build_default_intent()

        # Strip markdown code fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            # Remove first and last lines (code fences)
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()

        try:
            data = json.loads(cleaned)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            logger.warning("response_shaper_intent_parse_failed", raw=raw[:200])

        return cls._build_default_intent()

    @classmethod
    def _build_default_intent(cls) -> dict:
        """Build a default intent when parsing fails."""
        return {
            "intent": "unknown",
            "department": "general",
            "action": "conversation",
            "needs_agent": False,
            "suggested_agent": None,
            "confidence": 0.0,
            "entities": {},
        }

    @classmethod
    def build_dual_output_instruction(cls) -> str:
        """Return the instruction appended to system prompt for dual output."""
        return (
            "\n\n---\n"
            "RESPONSE FORMAT INSTRUCTION:\n"
            "You MUST respond with exactly TWO sections separated by the marker '---INTENT---'.\n\n"
            "SECTION 1 (before ---INTENT---):\n"
            "Your natural language reply to the user. Follow the personality above.\n"
            "Keep it conversational and helpful.\n\n"
            "SECTION 2 (after ---INTENT---):\n"
            "A single JSON object classifying this interaction:\n"
            "{\n"
            '  "intent": "query|command|greeting|complaint|unknown",\n'
            '  "department": "tech|finance|hr|sales|marketing|general",\n'
            '  "action": "brief description of what user wants",\n'
            '  "needs_agent": true or false,\n'
            '  "suggested_agent": "agent_name or null",\n'
            '  "confidence": 0.0 to 1.0,\n'
            '  "entities": {}\n'
            "}\n\n"
            "Example:\n"
            "Halo! Saya bisa bantu. Sebentar ya...\n"
            "---INTENT---\n"
            '{"intent":"query","department":"finance","action":"check_balance",'
            '"needs_agent":true,"suggested_agent":"accounting","confidence":0.85,"entities":{}}\n'
        )
