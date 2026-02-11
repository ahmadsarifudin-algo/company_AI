# Human-Agent Mapping — Organization Chart

## Overview

- **Total Agent Roles**: 63
- **Total Departments**: 7 + Enterprise
- **Minimum Humans Required**: 32 (Practical Minimum)
- **Mapping Strategy**: 1 Human supervises 1-6 agents based on role complexity

---

## Enterprise — 3 Agents → 1 Human

| Human | Agent(s) | Tier |
|-------|----------|------|
| CEO / COO | Global Supervisor, Scheduling Agent, Communication Agent | 🟠 Advanced, 💚 Nano, 💚 Nano |

---

## Tech Department — 11 Agents → 8 Humans

| Human | Agent(s) | Tier |
|-------|----------|------|
| CTO | Tech Supervisor | 🟠 Advanced |
| Product Manager | Product Analyst, Technical Writer | 💛 Standard, 💛 Standard |
| Lead Architect | Architect Agent | 🟠 Advanced |
| Sr. Backend Dev | Backend Engineer, DevOps Agent | 🔴 Specialist, 💛 Standard |
| Sr. Frontend Dev | Frontend Engineer Agent | 🔴 Specialist |
| QA Lead | QA Agent, Security Agent | 💛 Standard, 🟠 Advanced |
| SRE / Infra Lead | SRE Agent | 💛 Standard |
| Data Engineer | Data Engineer Agent | 💛 Standard |

---

## Finance Department — 9 Agents → 3 Humans

| Human | Agent(s) | Tier |
|-------|----------|------|
| CFO | Finance Supervisor, Treasury Agent | 🟠 Advanced, 💛 Standard |
| Sr. Accountant | Accounting Agent, Budget Planning, Forecasting, Invoicing Agent | 💛 Standard |
| Internal Auditor | Audit Agent, Risk & Compliance, Tax Agent | 🟠 Advanced |

---

## HR Department — 8 Agents → 3 Humans

| Human | Agent(s) | Tier |
|-------|----------|------|
| HR Head | HR Supervisor, HR Compliance, Performance Analytics, Training & Development | 🟠 Advanced, 💛 Standard |
| Recruiter | Recruitment Agent, Onboarding Agent, Payroll Validation | 💛 Standard, 💚 Nano |
| HR Admin | Benefits Administration Agent | 💚 Nano |

---

## Sales Department — 6 Agents → 1 Human

| Human | Agent(s) | Tier |
|-------|----------|------|
| Sales Head | Sales Supervisor, Lead Scoring, Deal Intelligence, Forecasting, Pricing Optimization, Contract Review | 🟠 Advanced, 💚 Nano, 💛 Standard |

---

## Digital Marketing Department — 8 Agents → 7 Humans

| Human | Agent(s) | Tier |
|-------|----------|------|
| Marketing Head | Marketing Supervisor | 🟠 Advanced |
| Content Strategist | Content Creator Agent | 💛 Standard |
| Content Producer | Content Maker & Editing Agent | 🔴 Specialist / 💚 Nano |
| Social Media Manager | Social Media Agent | 💚 Nano |
| CRM Specialist | Customer Relationship Agent | 💛 Standard |
| Account Manager | Customer Success Agent | 💛 Standard |
| Digital Analyst | Campaign Analytics Agent | 💛 Standard |
| SEO Specialist | SEO & SEM Agent | 💛 Standard |

> Note: Marketing Head also supervises SEO Specialist. **8 agents → 7 humans** (Marketing Head supervises 2).

---

## Legal Department — 7 Agents → 4 Humans

| Human | Agent(s) | Tier |
|-------|----------|------|
| Corporate Counsel / Legal Head | Legal Supervisor, IP Management Agent | 🟠 Advanced, 💚 Nano |
| Contract Specialist | Contract Drafting Agent, Contract Review Agent | 💛 Standard |
| Compliance Officer | Regulatory Compliance Agent, Data Protection Agent | 🟠 Advanced, 💛 Standard |
| Litigation Analyst | Litigation Support Agent | 💛 Standard |

---

## Strategic & Business Development — 7 Agents → 5 Humans

| Human | Agent(s) | Tier |
|-------|----------|------|
| BizDev Director / Head of Strategy | BizDev Supervisor, Business Modeling Agent | 🟠 Advanced, 💛 Standard |
| Market Analyst | Market Research Agent, Competitive Intelligence Agent | 💛 Standard, 💚 Nano |
| Business Dev Manager | Partnership Evaluation Agent, Go-to-Market Agent | 💛 Standard |
| Strategy Planner | Strategic Planning Agent | 🟠 Advanced |

> Note: BizDev Director supervises 2 agents. Market Analyst supervises 2. **7 agents → 4 humans**.

---

## Summary

| Department | Agents | Humans | Ratio |
|-----------|--------|--------|-------|
| Enterprise | 3 | 1 | 3:1 |
| Tech | 11 | 8 | 1.4:1 |
| Finance | 9 | 3 | 3:1 |
| HR | 8 | 3 | 2.7:1 |
| Sales | 6 | 1 | 6:1 |
| Marketing | 8 | 7 | 1.1:1 |
| Legal | 7 | 4 | 1.8:1 |
| BizDev | 7 | 4 | 1.8:1 |
| **Total** | **63** | **31** | **2:1 avg** |

> **Practical Minimum**: 31 humans to supervise 63 agents. Sales has highest agent density per human (6:1) — acceptable because Sales Head delegates operational tasks to agents while retaining strategic oversight.

---

## Cost by Human Responsibility

| Department | Agents | Monthly LLM Cost | Cost/Human/Month |
|-----------|--------|-----------------|-----------------|
| Enterprise | 3 | ~$45 | $45 |
| Tech | 11 | ~$350 | $44 |
| Finance | 9 | ~$220 | $73 |
| HR | 8 | ~$100 | $33 |
| Sales | 6 | ~$85 | $85 |
| Marketing | 8 | ~$170 | $24 |
| Legal | 7 | ~$145 | $36 |
| BizDev | 7 | ~$140 | $35 |
| **Total** | **63** | **~$1,255** | **$40 avg** |

> Note: Cost estimates based on MODEL_TIER_CLASSIFICATION usage assumptions. Actual costs may vary by ±20%.
