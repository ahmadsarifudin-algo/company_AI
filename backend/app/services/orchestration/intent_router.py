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

    @classmethod
    def route(cls, content: str, sender_department: str = "") -> RoutingResult:
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

        # Phase 2: LLM classification (async — to be implemented)
        # For now, fallback to sender's department supervisor
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

        Calls LiteLLM proxy with a classification prompt.
        Falls back to keyword matching if LLM fails.
        """
        # TODO: Implement LLM-based classification via LiteLLM
        # For now, use keyword matching
        return cls.route(content)
