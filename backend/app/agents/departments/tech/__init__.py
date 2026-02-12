"""
Tech Department — 11 specialist agents + supervisor.

Agents:
    - TechSupervisor: Plan decomposition and task assignment
    - ProductAnalyst: PRD generation, acceptance criteria
    - Architect: HLD/LLD, API contracts
    - BackendEngineer: Code generation, unit tests
    - FrontendEngineer: UI code generation
    - QAAgent: Test plans, acceptance validation
    - DevOpsAgent: CI config, deployment prep
    - SREAgent: Monitoring, incident postmortem
    - SecurityAgent: CVE scan, dependency audit
    - DataEngineer: ETL pipeline design
    - TechnicalWriter: API docs, changelogs
"""

from app.agents.departments.tech.supervisor import TechSupervisor
from app.agents.departments.tech.product_analyst import ProductAnalystAgent
from app.agents.departments.tech.architect import ArchitectAgent
from app.agents.departments.tech.backend_engineer import BackendEngineerAgent
from app.agents.departments.tech.frontend_engineer import FrontendEngineerAgent
from app.agents.departments.tech.qa import QAAgent
from app.agents.departments.tech.devops import DevOpsAgent
from app.agents.departments.tech.sre import SREAgent
from app.agents.departments.tech.security import SecurityAgent
from app.agents.departments.tech.data_engineer import DataEngineerAgent
from app.agents.departments.tech.technical_writer import TechnicalWriterAgent

TECH_AGENTS = [
    TechSupervisor,
    ProductAnalystAgent,
    ArchitectAgent,
    BackendEngineerAgent,
    FrontendEngineerAgent,
    QAAgent,
    DevOpsAgent,
    SREAgent,
    SecurityAgent,
    DataEngineerAgent,
    TechnicalWriterAgent,
]

__all__ = [
    "TechSupervisor",
    "ProductAnalystAgent",
    "ArchitectAgent",
    "BackendEngineerAgent",
    "FrontendEngineerAgent",
    "QAAgent",
    "DevOpsAgent",
    "SREAgent",
    "SecurityAgent",
    "DataEngineerAgent",
    "TechnicalWriterAgent",
    "TECH_AGENTS",
]
