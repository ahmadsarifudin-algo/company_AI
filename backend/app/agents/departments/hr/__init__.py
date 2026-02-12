"""
HR Department — 8 specialist agents + supervisor.

Agents:
    - HRSupervisor: Workflow routing
    - RecruitmentAgent: CV screening, ranking
    - OnboardingAgent: Checklist, contract drafts
    - PayrollAgent: Anomaly detection
    - PerformanceAgent: KPI aggregation
    - ComplianceAgent: Labor law checks
    - TrainingAgent: Skill gap analysis
    - BenefitsAgent: Eligibility lookup
"""

from app.agents.departments.hr.supervisor import HRSupervisor
from app.agents.departments.hr.recruitment import RecruitmentAgent
from app.agents.departments.hr.onboarding import OnboardingAgent
from app.agents.departments.hr.payroll import PayrollAgent
from app.agents.departments.hr.performance import PerformanceAgent
from app.agents.departments.hr.compliance import ComplianceAgent
from app.agents.departments.hr.training import TrainingAgent
from app.agents.departments.hr.benefits import BenefitsAgent

HR_AGENTS = [HRSupervisor, RecruitmentAgent, OnboardingAgent, PayrollAgent,
             PerformanceAgent, ComplianceAgent, TrainingAgent, BenefitsAgent]

__all__ = ["HRSupervisor", "RecruitmentAgent", "OnboardingAgent", "PayrollAgent",
           "PerformanceAgent", "ComplianceAgent", "TrainingAgent", "BenefitsAgent",
           "HR_AGENTS"]
