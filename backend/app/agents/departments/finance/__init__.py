"""
Finance Department — 9 specialist agents + supervisor.

Agents:
    - FinanceSupervisor: Workflow routing and task assignment
    - AccountingAgent: Ledger reconciliation
    - BudgetPlanningAgent: Budget proposals
    - ForecastingAgent: Cashflow projection
    - AuditAgent: Internal audit simulation
    - RiskComplianceAgent: Regulatory checks
    - TreasuryAgent: Cash position monitoring
    - InvoicingAgent: Invoice generation, AR/AP
    - TaxAgent: Tax calculation, filing prep
"""

from app.agents.departments.finance.supervisor import FinanceSupervisor
from app.agents.departments.finance.accounting import AccountingAgent
from app.agents.departments.finance.budget_planning import BudgetPlanningAgent
from app.agents.departments.finance.forecasting import ForecastingAgent
from app.agents.departments.finance.audit import AuditAgent
from app.agents.departments.finance.risk_compliance import RiskComplianceAgent
from app.agents.departments.finance.treasury import TreasuryAgent
from app.agents.departments.finance.invoicing import InvoicingAgent
from app.agents.departments.finance.tax import TaxAgent

FINANCE_AGENTS = [
    FinanceSupervisor,
    AccountingAgent,
    BudgetPlanningAgent,
    ForecastingAgent,
    AuditAgent,
    RiskComplianceAgent,
    TreasuryAgent,
    InvoicingAgent,
    TaxAgent,
]

__all__ = [
    "FinanceSupervisor",
    "AccountingAgent",
    "BudgetPlanningAgent",
    "ForecastingAgent",
    "AuditAgent",
    "RiskComplianceAgent",
    "TreasuryAgent",
    "InvoicingAgent",
    "TaxAgent",
    "FINANCE_AGENTS",
]
