# 🤖 Multi-Agentic AI Enterprise Operating System

> A comprehensive AI-powered enterprise operating system that automates business operations across 7 departments using 63 AI agents supervised by 31+ human employees.

![System](https://img.shields.io/badge/Agents-63-blue)
![Departments](https://img.shields.io/badge/Departments-7-green)
![Humans](https://img.shields.io/badge/Humans-31-orange)
![Status](https://img.shields.io/badge/Status-Phase%20A%20Complete-brightgreen)
![LLM Cost](https://img.shields.io/badge/LLM%20Cost-~%241%2C389%2Fmo-purple)

---

## 📋 Overview

This system establishes a **unified enterprise-grade AI operating model** with centralized governance, strict RBAC, auditability, compliance controls, and cross-department orchestration. Every AI agent is paired 1:1 with a human supervisor — agents propose, humans approve.

```mermaid
graph TD
    User([Human Employees — 31]) <-->|WhatsApp / Email / Dashboard| Gateway[API Gateway]
    Gateway --> GS[Global Supervisor]
    
    GS --> Tech[Tech Supervisor — 11 agents]
    GS --> Fin[Finance Supervisor — 9 agents]
    GS --> HR[HR Supervisor — 8 agents]
    GS --> Sales[Sales Supervisor — 6 agents]
    GS --> Mkt[Marketing Supervisor — 8 agents]
    GS --> Legal[Legal Supervisor — 7 agents]
    GS --> BizDev[BizDev Supervisor — 7 agents]
    
    Tech & Fin & HR & Sales & Mkt & Legal & BizDev --> Tools[Tool Sandbox]
    Tools --> Store[(Artifact Store + Audit Ledger)]
```

---

## 🚀 Development Progress

| Phase | Status | What's Built |
|-------|--------|-------------|
| **Foundation** | ✅ Done | FastAPI + SQLAlchemy + JWT auth, Docker compose, hot-swap DB |
| **Agent Runtime** | ✅ Done | BaseAgent, PolicyEngine, ApprovalGate, Telemetry, 34 agent classes |
| **Dashboard UI** | ✅ Done | Next.js 14 admin dashboard — 7 pages (Overview, Agents, Traces, Approvals, Playground, Users, Settings) |
| **User Registration** | ✅ Done | Admin-driven invite flow, SHA-256 hashed tokens, role hierarchy (admin/manager/lead/contributor) |
| **LLM Integration** | ✅ Done | Gemini direct (gemini-2.0-flash), settings page for model config |
| **Login & RBAC** | 🔲 Next | Login page, AuthContext, role-based UI filtering |
| **HITL Approval** | 🔲 Next | Human identity in approval chain, department scoping |

---

## 🏗️ Departments & Agents

| Department | Agents | Supervisor | Key Functions |
|-----------|--------|-----------|---------------|
| **🖥️ Tech** | 11 | Tech Supervisor | Architecture, coding, QA, DevOps, SRE, security |
| **💰 Finance** | 9 | Finance Supervisor | Accounting, budgeting, audit, tax, invoicing |
| **👥 HR** | 8 | HR Supervisor | Recruitment, onboarding, payroll, compliance |
| **📈 Sales** | 6 | Sales Supervisor | Lead scoring, deals, forecasting, pricing |
| **📣 Marketing** | 8 | Marketing Supervisor | Content, social media, SEO, campaigns, CRM |
| **⚖️ Legal** | 7 | Legal Supervisor | Contracts, compliance, IP, data protection |
| **🚀 BizDev** | 7 | BizDev Supervisor | Market research, partnerships, strategy |
| **🌐 Enterprise** | 3 | Global Supervisor | Scheduling, communication, orchestration |

**Total: 63 agents | 7 departments | 31 humans**

---

## 🧠 Technology Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.11+, FastAPI, LangGraph, LangChain |
| **Model Gateway** | LiteLLM Proxy (multi-model routing) |
| **Database** | PostgreSQL + pgvector (RLS + RAG) |
| **Cache/Queue** | Redis + Celery |
| **Storage** | AWS S3 / MinIO |
| **Frontend** | Next.js 14, Tailwind CSS, Shadcn/UI |
| **Messaging** | WhatsApp Business API, Email (Gmail/Outlook) |
| **Security** | Vault, PII Masking, Schema Isolation |
| **Monitoring** | Prometheus + Grafana, LangSmith |
| **CI/CD** | GitHub Actions, Docker, Kubernetes |

---

## 💸 4-Tier Model Strategy

Cost-efficient multi-model routing saves **69%** compared to running all agents on advanced models:

| Tier | Models | Agents | Monthly Cost |
|------|--------|--------|-------------|
| 💚 **Nano** | GPT-4o-mini, Gemini Flash, Haiku | 9 (14%) | ~$20 |
| 💛 **Standard** | GPT-4o, Claude Sonnet, Gemini Pro | 33 (52%) | ~$693 |
| 🟠 **Advanced** | Claude Opus, GPT-o3, Gemini Ultra | 15 (24%) | ~$540 |
| 🔴 **Specialist** | DeepSeek Coder, GPT-4V, DALL-E 3 | 3 (5%) | ~$135 |
| | **Total** | **63** | **~$1,389/mo** |

---

## 📁 Project Structure

```
company_AI/
├── backend/
│   ├── app/
│   │   ├── main.py                   # FastAPI app entry
│   │   ├── worker.py                 # Celery worker
│   │   ├── core/                     # Config, security, deps, policy engine
│   │   ├── models/                   # SQLAlchemy models (User, Agent, AuditEvent)
│   │   ├── schemas/                  # Pydantic schemas
│   │   ├── api/v1/                   # API routers (admin, auth, tasks, playground)
│   │   └── agents/                   # 34 agent classes across 7 departments
│   │       └── departments/          # finance/, hr/, tech/, sales/, etc.
│   ├── docker-compose.yml
│   └── Dockerfile
│
├── frontend/
│   ├── src/app/
│   │   ├── (admin)/                  # Dashboard pages (Overview, Agents, Traces,
│   │   │                             #   Approvals, Playground, Users, Settings)
│   │   └── invite/                   # Public invite page
│   └── src/lib/api.ts                # API client
│
├── Design Documents (19 docs)
│   ├── ENTERPRISE_AGENTS_MANUAL.md   # Governance framework
│   ├── TECHNICAL_ARCHITECTURE.md     # Tech stack & architecture
│   ├── IMPLEMENTATION_ROADMAP.md     # 24-week plan
│   └── ...                           # Model tiers, RBAC, workflows, etc.
│
└── Evaluasi/                         # System analysis & cost reports
```

---

## 📊 Implementation Roadmap

| Phase | Weeks | Deliverable |
|-------|-------|------------|
| **1. Foundation** | 1-2 | PostgreSQL + FastAPI + LiteLLM + Auth |
| **2. Agent Runtime** | 3-4 | LangGraph supervisors + BaseAgent + task queue |
| **3. Intelligence** | 5-6 | RAG pipeline + agent memory (pgvector) |
| **4a. Core Depts** | 7-10 | Tech, Finance, HR, Sales modules |
| **4b. Extended Depts** | 11-13 | Marketing, Legal, BizDev modules |
| **5. Dashboard** | 14-16 | Mission Control + Approval Queue + Notifications |
| **6. Admin** | 17-18 | Cost analytics + policy engine + model routing |
| **7. Testing** | 19-20 | Staging + security audit + penetration testing |
| **8. Go Live** | 21-24 | WhatsApp/Email integration + pilot rollout 🚀 |

> Full details: [IMPLEMENTATION_ROADMAP.md](./IMPLEMENTATION_ROADMAP.md)

---

## 💰 Cost Estimate

| Category | Amount |
|----------|--------|
| **CAPEX** (one-time) | $34,500 – $58,500 |
| **OPEX** (monthly) | $9,774 – $17,714 |
| **Year 1 Total** | $151,788 – $271,068 |
| **Break-even** | 12-18 months |

> Full details: [COST_ANALYSIS_CAPEX_OPEX.md](./Evaluasi/COST_ANALYSIS_CAPEX_OPEX.md)

---

## 🔒 Security

- **Row-Level Security (RLS)** — Department data isolation
- **Schema Isolation** — Each department in its own DB schema
- **PII Masking** — Before any LLM submission (HR & Finance)
- **Vault Integration** — Secrets management (HashiCorp/AWS)
- **Immutable Audit Logs** — Every agent action is logged
- **Sandboxed Tools** — Agents can only access authorized tools
- **Human-in-the-Loop** — All high-risk actions require human approval

---

## 🤝 Core Principles

1. **Human-in-the-Loop** — Agents propose, humans approve
2. **Artifact-Driven** — Every output is a versioned artifact
3. **Department Isolation** — Data doesn't leak across departments
4. **Budget-Aware** — Model routing optimized for cost
5. **Immutable Audit** — Full traceability of all actions
6. **Privacy-First** — PII masking for employee and financial data

---

## 📚 Documentation Index

| Document | Description |
|----------|------------|
| [Enterprise Manual](./ENTERPRISE_AGENTS_MANUAL.md) | Governance, RBAC, compliance gates |
| [Technical Architecture](./TECHNICAL_ARCHITECTURE.md) | Stack, diagrams, security, deployment |
| [Implementation Roadmap](./IMPLEMENTATION_ROADMAP.md) | 24-week plan with 120+ tasks |
| [Model Tiers](./MODEL_TIER_CLASSIFICATION.md) | 4-tier cost strategy + LiteLLM config |
| [Admin Governance](./ADMIN_GOVERNANCE_DESIGN.md) | Budget control, policy engine |
| [Human-Agent System](./HUMAN_AGENT_SYSTEM.md) | Pairing model, communication flows |
| [Human Mapping](./HUMAN_AGENT_MAPPING.md) | 31 humans ↔ 63 agents org chart |
| [Interface Design](./HUMAN_INTERFACE_DESIGN.md) | Dashboard wireframes |
| [Workflows](./AGENT_WORKFLOWS.md) | 8 Mermaid sequence diagrams |
| [Cost Analysis](./Evaluasi/COST_ANALYSIS_CAPEX_OPEX.md) | CAPEX $35-58K, OPEX $10-18K/mo |
| [System Analysis](./Evaluasi/PROFESSIONAL_SYSTEM_ANALYSIS.md) | Score: 7.4/10 |

---

## 📄 License

This project is proprietary and confidential. All rights reserved.

---

<p align="center">
  <b>Built with 🧠 by Project Antigravity</b><br>
  <i>Automating enterprise operations, one agent at a time.</i>
</p>
