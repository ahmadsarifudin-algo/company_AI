"""
IntentRouter — LLM-based intent classification for incoming messages.

Analyzes user messages to determine:
1. Which department should handle it
2. Which specific agent to assign
3. What tools will likely be needed
4. Priority level

Uses the LiteLLM proxy for classification.
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from app.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


# ── Keyword-based routing rules (fast path) ──────────

ROUTING_RULES: list[dict[str, Any]] = [
    # Finance
    {"keywords": ["invoice", "faktur", "billing", "tagihan"], "department": "finance", "agent": "InvoicingAgent"},
    {"keywords": ["tax", "pajak", "pph", "ppn", "efiling"], "department": "finance", "agent": "TaxAgent"},
    {"keywords": ["report keuangan", "financial report", "p&l", "balance sheet", "laporan keuangan"],
     "department": "finance", "agent": "AccountingAgent"},
    {"keywords": ["budget", "anggaran", "rencana keuangan"], "department": "finance", "agent": "BudgetPlanningAgent"},
    {"keywords": ["forecast", "proyeksi", "prediksi"], "department": "finance", "agent": "ForecastingAgent"},
    {"keywords": ["treasury", "kas", "cash flow", "arus kas"], "department": "finance", "agent": "TreasuryAgent"},
    {"keywords": ["audit", "pemeriksaan"], "department": "finance", "agent": "AuditAgent"},
    {"keywords": ["reconcile", "rekonsiliasi"], "department": "finance", "agent": "AccountingAgent"},

    # HR
    {"keywords": ["recruit", "hiring", "cv", "resume", "interview", "wawancara", "lowongan"],
     "department": "hr", "agent": "RecruitmentAgent"},
    {"keywords": ["payroll", "gaji", "salary", "upah"], "department": "hr", "agent": "PayrollAgent"},
    {"keywords": ["onboard", "orientasi", "new hire"], "department": "hr", "agent": "OnboardingAgent"},
    {"keywords": ["performance", "kpi", "kinerja", "review"], "department": "hr", "agent": "PerformanceAgent"},
    {"keywords": ["benefit", "bpjs", "cuti", "leave", "tunjangan"], "department": "hr", "agent": "BenefitsAgent"},
    {"keywords": ["compliance", "kepatuhan", "uu ketenagakerjaan"], "department": "hr", "agent": "ComplianceAgent"},
    {"keywords": ["training", "pelatihan", "workshop"], "department": "hr", "agent": "TrainingAgent"},

    # Sales
    {"keywords": ["lead", "prospect", "prospek"], "department": "sales", "agent": "LeadScoringAgent"},
    {"keywords": ["deal", "pipeline", "penjualan", "sales"], "department": "sales", "agent": "DealIntelligenceAgent"},
    {"keywords": ["quote", "quotation", "penawaran", "harga"], "department": "sales", "agent": "PricingAgent"},
    {"keywords": ["contract", "kontrak", "perjanjian"], "department": "sales", "agent": "ContractReviewAgent"},
    {"keywords": ["sales forecast", "target penjualan"], "department": "sales", "agent": "SalesForecastingAgent"},

    # Tech
    {"keywords": ["bug", "error", "deploy", "ci/cd", "release"], "department": "tech", "agent": "DevOpsAgent"},
    {"keywords": ["test", "testing", "qa"], "department": "tech", "agent": "QAAgent"},
    {"keywords": ["security", "vulnerability", "cve", "keamanan"], "department": "tech", "agent": "SecurityAgent"},
    {"keywords": ["architecture", "design", "arsitektur"], "department": "tech", "agent": "ArchitectAgent"},
    {"keywords": ["log", "monitoring", "incident", "downtime"], "department": "tech", "agent": "SREAgent"},
    {"keywords": ["code", "backend", "api"], "department": "tech", "agent": "BackendEngineerAgent"},
    {"keywords": ["frontend", "ui", "component", "react"], "department": "tech", "agent": "FrontendEngineerAgent"},
    {"keywords": ["data", "etl", "warehouse", "pipeline data"], "department": "tech", "agent": "DataEngineerAgent"},
    {"keywords": ["docs", "documentation", "readme"], "department": "tech", "agent": "TechnicalWriterAgent"},

    # Shared actions
    {"keywords": ["email", "kirim email", "send email"], "department": "_shared", "agent": "_caller",
     "tools": ["send_email"]},
    {"keywords": ["whatsapp", "wa", "kirim wa"], "department": "_shared", "agent": "_caller",
     "tools": ["send_whatsapp"]},
    {"keywords": ["telegram", "tg", "kirim telegram"], "department": "_shared", "agent": "_caller",
     "tools": ["send_telegram"]},
    {"keywords": ["meeting", "schedule", "jadwal", "rapat"], "department": "_shared", "agent": "_caller",
     "tools": ["create_meeting"]},
    {"keywords": ["search", "cari", "find", "query"], "department": "_shared", "agent": "_caller",
     "tools": ["search_data"]},
]


@dataclass
class RoutingResult:
    """Result of intent classification."""

    department: str
    agent: str
    intent: str = ""
    tools_needed: list[str] = field(default_factory=list)
    priority: str = "normal"  # "low" | "normal" | "high" | "urgent"
    confidence: float = 0.0
    routing_method: str = "keyword"  # "keyword" | "llm"


class IntentRouter:
    """Classifies user messages and routes to the correct department/agent.

    Two-phase routing:
    1. Fast path: keyword matching (instant, no API call)
    2. Slow path: LLM classification (when keywords don't match)
    """

    # Departments and their representative agents for LLM-based routing
    _DEPARTMENT_AGENTS: dict[str, list[str]] = {
        "finance": [
            "InvoicingAgent", "TaxAgent", "AccountingAgent",
            "BudgetPlanningAgent", "ForecastingAgent", "TreasuryAgent", "AuditAgent",
        ],
        "hr": [
            "RecruitmentAgent", "PayrollAgent", "OnboardingAgent",
            "PerformanceAgent", "BenefitsAgent", "ComplianceAgent", "TrainingAgent",
        ],
        "sales": [
            "LeadScoringAgent", "DealIntelligenceAgent", "PricingAgent",
            "ContractReviewAgent", "SalesForecastingAgent",
        ],
        "tech": [
            "DevOpsAgent", "QAAgent", "SecurityAgent", "ArchitectAgent",
            "SREAgent", "BackendEngineerAgent", "FrontendEngineerAgent",
            "DataEngineerAgent", "TechnicalWriterAgent",
        ],
    }

    _CLASSIFICATION_PROMPT = """You are an intent classification engine for a multi-department enterprise.
Analyze the user message and return a JSON object with these fields:
- "department": one of "finance", "hr", "sales", "tech"
- "agent": the most appropriate agent name from the list below
- "intent": a short snake_case intent label (e.g. "create_invoice", "schedule_interview")
- "tools_needed": list of tool names that might be needed (can be empty)
- "priority": one of "low", "normal", "high", "urgent"
- "confidence": a float 0.0–1.0 indicating your confidence

Available agents by department:
{agent_list}

Respond ONLY with raw JSON, no markdown, no explanation.
"""

    @classmethod
    async def route(cls, content: str, sender_department: str = "") -> RoutingResult:
        """Route a message to the correct department and agent.

        Args:
            content: User message text.
            sender_department: User's department (for scoping).

        Returns:
            RoutingResult with department, agent, and tool suggestions.
        """
        # Phase 1: keyword matching (fast)
        result = cls._keyword_match(content)
        if result.confidence > 0:
            logger.info(
                "intent_routed_keyword",
                department=result.department,
                agent=result.agent,
                intent=result.intent,
                confidence=result.confidence,
            )
            return result

        # Phase 2: LLM classification (async)
        llm_result = await cls.route_with_llm(content)
        if llm_result.confidence > 0:
            return llm_result

        # Phase 3: Fallback to sender's department supervisor
        fallback = RoutingResult(
            department=sender_department or "tech",
            agent=f"{(sender_department or 'tech').capitalize()}Supervisor",
            intent="general_task",
            confidence=0.3,
            routing_method="fallback",
        )
        logger.info(
            "intent_routed_fallback",
            department=fallback.department,
            agent=fallback.agent,
        )
        return fallback

    @classmethod
    def _keyword_match(cls, content: str) -> RoutingResult:
        """Match message content against routing rules.

        Returns result with highest keyword match count.
        """
        content_lower = content.lower()
        best_match: RoutingResult | None = None
        best_score = 0

        for rule in ROUTING_RULES:
            score = sum(1 for kw in rule["keywords"] if kw in content_lower)
            if score > best_score:
                best_score = score
                best_match = RoutingResult(
                    department=rule["department"],
                    agent=rule["agent"],
                    intent="_".join(rule["keywords"][:2]),
                    tools_needed=rule.get("tools", []),
                    confidence=min(score * 0.3, 1.0),
                    routing_method="keyword",
                )

        return best_match or RoutingResult(
            department="",
            agent="",
            confidence=0.0,
        )

    @classmethod
    async def route_with_llm(cls, content: str) -> RoutingResult:
        """Classify intent using LLM (for complex/ambiguous messages).

        Calls the configured Gemini or OpenAI provider with a
        structured classification prompt and parses the JSON response.
        Falls back gracefully on any error.
        """
        import json
        import os

        import httpx

        # Build agent list for the prompt
        agent_lines = []
        for dept, agents in cls._DEPARTMENT_AGENTS.items():
            agent_lines.append(f"  {dept}: {', '.join(agents)}")
        agent_list = "\n".join(agent_lines)

        system_prompt = cls._CLASSIFICATION_PROMPT.format(agent_list=agent_list)

        # Determine provider + key (same logic as admin test_agent)
        provider = os.getenv("LLM_PROVIDER", "google")
        try:
            import aioredis
            r = await aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
            saved_provider = await r.get("settings:provider")
            if saved_provider:
                provider = saved_provider if isinstance(saved_provider, str) else saved_provider.decode()
            saved_key = await r.get(f"settings:{provider}_api_key")
            api_key = (saved_key if isinstance(saved_key, str) else saved_key.decode()) if saved_key else None
            await r.close()
        except Exception:
            api_key = None

        if not api_key:
            api_key = os.getenv("GEMINI_API_KEY") if provider == "google" else os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("intent_llm_no_api_key", provider=provider)
            return RoutingResult(department="", agent="", confidence=0.0)

        # Build the request
        try:
            if provider == "google":
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
                payload = {
                    "contents": [{"parts": [{"text": f"{system_prompt}\n\nUser message: {content}"}]}],
                    "generationConfig": {
                        "temperature": 0.1,
                        "maxOutputTokens": 300,
                        "responseMimeType": "application/json",
                    },
                }
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
            else:
                # OpenAI-compatible
                url = "https://api.openai.com/v1/chat/completions"
                payload = {
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": content},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 300,
                    "response_format": {"type": "json_object"},
                }
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.post(
                        url, json=payload,
                        headers={"Authorization": f"Bearer {api_key}"},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                raw_text = data["choices"][0]["message"]["content"]

            # Parse the JSON response
            parsed = json.loads(raw_text)
            result = RoutingResult(
                department=parsed.get("department", "tech"),
                agent=parsed.get("agent", "TechSupervisor"),
                intent=parsed.get("intent", "classified_task"),
                tools_needed=parsed.get("tools_needed", []),
                priority=parsed.get("priority", "normal"),
                confidence=float(parsed.get("confidence", 0.7)),
                routing_method="llm",
            )
            logger.info(
                "intent_routed_llm",
                department=result.department,
                agent=result.agent,
                intent=result.intent,
                confidence=result.confidence,
            )
            return result

        except Exception as e:
            logger.warning("intent_llm_classification_failed", error=str(e))
            return RoutingResult(department="", agent="", confidence=0.0)
