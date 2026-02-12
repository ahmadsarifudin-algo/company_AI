"""
Output Schemas — Pydantic models for validating agent LLM output.

Each agent type has a strict output schema. LLM responses are parsed
and validated against these schemas. Invalid output → fail fast (no raw leak).

Organized by department: Tech → Finance → HR → Sales.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════
#  SUPERVISOR OUTPUTS (all departments share similar plan shape)
# ═══════════════════════════════════════════════════════════════

class TaskAssignment(BaseModel):
    task_id: str = ""
    description: str = ""
    assigned_to: str = ""
    priority: str = "medium"
    depends_on: list[str] = Field(default_factory=list)


class SupervisorPlanOutput(BaseModel):
    """Shared plan output for all department supervisors."""
    tasks: list[TaskAssignment] = Field(default_factory=list)
    summary: str = ""
    estimated_steps: int = 0


# Aliases per department
TechPlanOutput = SupervisorPlanOutput
FinancePlanOutput = SupervisorPlanOutput
HRPlanOutput = SupervisorPlanOutput
SalesPlanOutput = SupervisorPlanOutput


# ═══════════════════════════════════════════════════════════════
#  TECH DEPARTMENT
# ═══════════════════════════════════════════════════════════════

class ProductAnalysisOutput(BaseModel):
    prd: dict = Field(default_factory=dict)
    acceptance_criteria: list[dict] = Field(default_factory=list)
    kpis: list[dict] = Field(default_factory=list)
    risks: list[dict] = Field(default_factory=list)
    summary: str = ""


class ArchitectureDesign(BaseModel):
    components: list[dict] = Field(default_factory=list)
    interfaces: list[dict] = Field(default_factory=list)
    data_flow: list[dict] = Field(default_factory=list)


class ArchitectureOutput(BaseModel):
    hld: ArchitectureDesign = Field(default_factory=ArchitectureDesign)
    lld: ArchitectureDesign = Field(default_factory=ArchitectureDesign)
    api_contracts: list[dict] = Field(default_factory=list)
    threat_model: dict = Field(default_factory=dict)
    summary: str = ""


class BackendCodeOutput(BaseModel):
    files: list[dict] = Field(default_factory=list)
    tests: list[dict] = Field(default_factory=list)
    pr_description: str = ""
    summary: str = ""


class FrontendCodeOutput(BaseModel):
    components: list[dict] = Field(default_factory=list)
    tests: list[dict] = Field(default_factory=list)
    pr_description: str = ""
    summary: str = ""


class QAOutput(BaseModel):
    test_plan: dict = Field(default_factory=dict)
    test_cases: list[dict] = Field(default_factory=list)
    coverage_analysis: dict = Field(default_factory=dict)
    release_recommendation: str = ""
    summary: str = ""


class DevOpsOutput(BaseModel):
    ci_config: dict = Field(default_factory=dict)
    dockerfile: str = ""
    deployment_manifest: dict = Field(default_factory=dict)
    rollback_plan: dict = Field(default_factory=dict)
    summary: str = ""


class SREOutput(BaseModel):
    monitoring_rules: list[dict] = Field(default_factory=list)
    alerts: list[dict] = Field(default_factory=list)
    runbook: dict = Field(default_factory=dict)
    postmortem: dict = Field(default_factory=dict)
    summary: str = ""


class SecurityOutput(BaseModel):
    vulnerabilities: list[dict] = Field(default_factory=list)
    dependency_audit: dict = Field(default_factory=dict)
    secrets_scan: dict = Field(default_factory=dict)
    owasp_review: dict = Field(default_factory=dict)
    summary: str = ""


class DataEngineerOutput(BaseModel):
    pipeline: dict = Field(default_factory=dict)
    schema_design: dict = Field(default_factory=dict)
    quality_rules: list[dict] = Field(default_factory=list)
    migration_plan: dict = Field(default_factory=dict)
    summary: str = ""


class TechnicalWriterOutput(BaseModel):
    api_docs: dict = Field(default_factory=dict)
    changelog: list[dict] = Field(default_factory=list)
    adr: dict = Field(default_factory=dict)
    readme_updates: list[str] = Field(default_factory=list)
    summary: str = ""


# ═══════════════════════════════════════════════════════════════
#  FINANCE DEPARTMENT
# ═══════════════════════════════════════════════════════════════

class Reconciliation(BaseModel):
    accounts: list[dict] = Field(default_factory=list)
    discrepancies: list[dict] = Field(default_factory=list)
    journal_entries: list[dict] = Field(default_factory=list)
    status: str = "balanced"


class AccountingOutput(BaseModel):
    reconciliation: Reconciliation = Field(default_factory=Reconciliation)
    financial_statements: dict = Field(default_factory=dict)
    summary: str = ""


class BudgetPlanningOutput(BaseModel):
    budget_proposal: dict = Field(default_factory=dict)
    variance_analysis: dict = Field(default_factory=dict)
    recommendations: list[dict] = Field(default_factory=list)
    summary: str = ""


class ForecastingOutput(BaseModel):
    cashflow_projection: dict = Field(default_factory=dict)
    revenue_scenarios: list[dict] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    summary: str = ""


class AuditOutput(BaseModel):
    findings: list[dict] = Field(default_factory=list)
    control_tests: list[dict] = Field(default_factory=list)
    compliance_gaps: list[dict] = Field(default_factory=list)
    risk_rating: str = "low"
    summary: str = ""


class RiskComplianceOutput(BaseModel):
    regulatory_status: list[dict] = Field(default_factory=list)
    risk_assessment: dict = Field(default_factory=dict)
    action_items: list[dict] = Field(default_factory=list)
    summary: str = ""


class TreasuryOutput(BaseModel):
    cash_position: dict = Field(default_factory=dict)
    liquidity_analysis: dict = Field(default_factory=dict)
    fx_exposure: list[dict] = Field(default_factory=list)
    summary: str = ""


class InvoicingOutput(BaseModel):
    invoices: list[dict] = Field(default_factory=list)
    ar_summary: dict = Field(default_factory=dict)
    ap_summary: dict = Field(default_factory=dict)
    aging_report: dict = Field(default_factory=dict)
    summary: str = ""


class TaxOutput(BaseModel):
    calculations: dict = Field(default_factory=dict)
    filing_summary: dict = Field(default_factory=dict)
    tax_planning: list[dict] = Field(default_factory=list)
    compliance_status: str = "compliant"
    summary: str = ""


# ═══════════════════════════════════════════════════════════════
#  HR DEPARTMENT
# ═══════════════════════════════════════════════════════════════

class RecruitmentOutput(BaseModel):
    candidates: list[dict] = Field(default_factory=list)
    interview_questions: list[str] = Field(default_factory=list)
    pipeline_summary: dict = Field(default_factory=dict)
    summary: str = ""


class OnboardingOutput(BaseModel):
    checklist: list[dict] = Field(default_factory=list)
    contract_draft: dict = Field(default_factory=dict)
    orientation_schedule: list[dict] = Field(default_factory=list)
    summary: str = ""


class PayrollOutput(BaseModel):
    validation: dict = Field(default_factory=dict)
    anomalies: list[dict] = Field(default_factory=list)
    compliance_status: str = "compliant"
    summary: str = ""


class PerformanceOutput(BaseModel):
    kpi_summary: dict = Field(default_factory=dict)
    performance_reviews: list[dict] = Field(default_factory=list)
    talent_grid: dict = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)
    summary: str = ""


class ComplianceOutput(BaseModel):
    compliance_check: dict = Field(default_factory=dict)
    risk_level: str = "low"
    action_items: list[dict] = Field(default_factory=list)
    summary: str = ""


class TrainingOutput(BaseModel):
    skill_gaps: list[dict] = Field(default_factory=list)
    learning_path: list[dict] = Field(default_factory=list)
    training_roi: dict = Field(default_factory=dict)
    summary: str = ""


class BenefitsOutput(BaseModel):
    eligibility: list[dict] = Field(default_factory=list)
    enrollment_status: dict = Field(default_factory=dict)
    cost_summary: dict = Field(default_factory=dict)
    summary: str = ""


# ═══════════════════════════════════════════════════════════════
#  SALES DEPARTMENT
# ═══════════════════════════════════════════════════════════════

class LeadScoringOutput(BaseModel):
    leads: list[dict] = Field(default_factory=list)
    pipeline_summary: dict = Field(default_factory=dict)
    summary: str = ""


class DealIntelligenceOutput(BaseModel):
    competitive_analysis: dict = Field(default_factory=dict)
    battle_card: dict = Field(default_factory=dict)
    deal_strategy: dict = Field(default_factory=dict)
    summary: str = ""


class SalesForecastingOutput(BaseModel):
    forecast: dict = Field(default_factory=dict)
    quota_tracking: list[dict] = Field(default_factory=list)
    pipeline_health: dict = Field(default_factory=dict)
    summary: str = ""


class PricingOutput(BaseModel):
    pricing: dict = Field(default_factory=dict)
    approval_required: bool = False
    summary: str = ""


class ContractReviewOutput(BaseModel):
    review: dict = Field(default_factory=dict)
    renewal_tracking: dict = Field(default_factory=dict)
    summary: str = ""
