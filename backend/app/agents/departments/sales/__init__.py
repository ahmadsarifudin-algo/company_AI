"""
Sales/Marketing Department — 6 specialist agents + supervisor.

Agents:
    - SalesSupervisor: Pipeline routing
    - LeadScoringAgent: Lead qualification
    - DealIntelligenceAgent: Competitive analysis
    - SalesForecastingAgent: Revenue forecasting
    - PricingAgent: Dynamic pricing
    - ContractReviewAgent: Legal review
"""

from app.agents.departments.sales.supervisor import SalesSupervisor
from app.agents.departments.sales.lead_scoring import LeadScoringAgent
from app.agents.departments.sales.deal_intelligence import DealIntelligenceAgent
from app.agents.departments.sales.sales_forecasting import SalesForecastingAgent
from app.agents.departments.sales.pricing import PricingAgent
from app.agents.departments.sales.contract_review import ContractReviewAgent

SALES_AGENTS = [SalesSupervisor, LeadScoringAgent, DealIntelligenceAgent,
                SalesForecastingAgent, PricingAgent, ContractReviewAgent]

__all__ = ["SalesSupervisor", "LeadScoringAgent", "DealIntelligenceAgent",
           "SalesForecastingAgent", "PricingAgent", "ContractReviewAgent",
           "SALES_AGENTS"]
