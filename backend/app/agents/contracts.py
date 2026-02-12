"""
Agent Contracts — Rigid input/output schemas for agent execution.

Enforces:
- Structured task input with explicit constraints (budget, deadline, permissions)
- Structured output with mandatory artifacts, audit trail, and cost tracking
- Server-derived risk level (agents cannot set their own risk)
- PII handling classification
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """Risk classification for agent actions.

    Determines the approval chain requirements:
    - LOW:      auto-approve, no human in the loop
    - MEDIUM:   notify human, continue execution
    - HIGH:     require 1 approval (dept_lead)
    - CRITICAL: require 2 approvals (dept_lead + cfo/cto/legal_lead)
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PIIHandling(str, Enum):
    """How PII data should be handled in this task.

    - NONE:      no PII involved
    - MASKED:    PII present but masked in output/logs
    - ENCRYPTED: PII stored encrypted at rest
    - REDACTED:  PII completely removed from output
    """

    NONE = "none"
    MASKED = "masked"
    ENCRYPTED = "encrypted"
    REDACTED = "redacted"


class ArtifactRef(BaseModel):
    """Reference to a generated artifact."""

    artifact_id: str
    artifact_type: str = "document"   # "document" | "code" | "report" | "email" | "invoice"
    path: str = ""
    description: str = ""
    size_bytes: int = 0


class AgentInputSchema(BaseModel):
    """Rigid input contract for agent execution.

    Note: risk_level is NOT in this schema — it is server-derived
    via RiskDeriver based on the action + department + amount.
    """

    task_id: str = Field(..., description="Unique task identifier")
    description: str = Field(..., description="Human-readable task description")
    department: str = Field(..., description="Originating department")
    requester_id: str = Field(..., description="User who created this task")
    tool_permissions: list[str] = Field(
        default_factory=list,
        description="Resolved from ToolRegistry — tools this agent may use"
    )
    max_cost_usd: float = Field(
        default=10.0,
        description="Maximum budget for this task in USD",
        ge=0,
    )
    deadline: datetime | None = Field(
        default=None,
        description="Optional deadline for task completion"
    )
    priority: int = Field(
        default=5,
        description="Priority 1 (highest) to 10 (lowest)",
        ge=1,
        le=10,
    )
    context: dict = Field(
        default_factory=dict,
        description="Additional context (key-value) for the agent"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "task-001",
                "description": "Generate monthly financial report",
                "department": "finance",
                "requester_id": "user-cfo",
                "tool_permissions": ["calculator", "spreadsheet_generator"],
                "max_cost_usd": 5.0,
                "priority": 3,
            }
        }


class AgentOutputSchema(BaseModel):
    """Rigid output contract for agent execution.

    Every agent execution MUST produce output conforming to this schema.
    Ensures auditability, cost tracking, and artifact management.
    """

    task_id: str = Field(default="", description="Matching the input task_id")
    status: str = Field(
        ...,
        description="Final status: completed | failed | needs_approval | timeout"
    )
    summary: str = Field(
        ...,
        description="Human-readable summary of what was done"
    )
    artifacts: list[ArtifactRef] = Field(
        default_factory=list,
        description="Generated artifacts (documents, code, reports)"
    )
    cost_actual_usd: float = Field(
        default=0.0,
        description="Actual cost incurred (from LLMClient cost tracking)",
        ge=0,
    )
    risk_assessment: RiskLevel = Field(
        default=RiskLevel.LOW,
        description="Server-derived risk level for this execution"
    )
    pii_handling: PIIHandling = Field(
        default=PIIHandling.NONE,
        description="How PII was handled in this task"
    )
    token_usage: int = Field(
        default=0,
        description="Total tokens consumed"
    )
    tool_calls: int = Field(
        default=0,
        description="Number of tool calls made"
    )
    execution_time_ms: float = Field(
        default=0.0,
        description="Total execution time in milliseconds"
    )
    audit_trail_ids: list[str] = Field(
        default_factory=list,
        description="Audit event IDs linked to this execution"
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Any errors encountered"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "task-001",
                "status": "completed",
                "summary": "Generated monthly financial report for January 2026",
                "artifacts": [{"artifact_id": "art-001", "artifact_type": "report"}],
                "cost_actual_usd": 0.035,
                "risk_assessment": "low",
                "token_usage": 2450,
                "tool_calls": 1,
                "execution_time_ms": 5200.0,
            }
        }


class RiskDeriver:
    """Server-side risk level computation.

    Agents CANNOT set their own risk level. It is computed based on:
    - Action type
    - Department
    - Monetary amount (if applicable)
    - Data sensitivity
    """

    @staticmethod
    def compute(
        action: str,
        department: str,
        amount_usd: float = 0.0,
        data_sensitivity: str = "public",
    ) -> RiskLevel:
        """Compute risk level from action attributes.

        Args:
            action: Type of action being performed.
            department: Department context.
            amount_usd: Monetary value involved.
            data_sensitivity: Data classification level.

        Returns:
            Computed RiskLevel.
        """
        # PII access is always at least HIGH risk
        if data_sensitivity == "pii":
            return RiskLevel.HIGH

        # Confidential data is MEDIUM
        if data_sensitivity == "confidential":
            return RiskLevel.MEDIUM

        # Finance high-value thresholds
        if department == "finance":
            if amount_usd >= 100_000:
                return RiskLevel.CRITICAL
            if amount_usd >= 10_000:
                return RiskLevel.HIGH
            if amount_usd >= 1_000:
                return RiskLevel.MEDIUM

        # Legal actions are at least MEDIUM
        if department == "legal":
            return RiskLevel.MEDIUM

        # External communications
        if action in ("send_email", "send_whatsapp", "publish"):
            return RiskLevel.MEDIUM

        # Default
        return RiskLevel.LOW
