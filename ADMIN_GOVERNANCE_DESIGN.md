# Administrator Control & Governance Design

> **Updated Feb 2026**: Reflects implemented control plane (Modules 0-7). ABAC PolicyEngine, BudgetEnforcer, and ApprovalGate are now live.

This document outlines the "Admin Layer" for managing model orchestration, cost efficiency, user policies, and database integrations.

## 1. Core Component: Model Gateway (Efficiency Orchestrator)

The Model Gateway uses **LiteLLM Proxy** for dynamic model routing across **4 classified tiers** to optimize cost while maintaining quality.

> See [MODEL_TIER_CLASSIFICATION.md](file:///c:/Users/sarif/Documents/project_antigravity/company_AI/MODEL_TIER_CLASSIFICATION.md) for full agent-to-model mapping.

### **1.1 Model Tier Classification**

All 63 agents are assigned to one of 4 tiers based on task complexity:

| Tier | Model Options | Use Case | Cost/1M Tokens | Agents |
|------|--------------|----------|---------------|--------|
| 💚 **Nano** | GPT-4o-mini, Gemini 2.0 Flash, Claude Haiku | Intent parsing, routing, FAQ, simple classification | ~$0.10–0.25 | 9 (14%) |
| 💛 **Standard** | GPT-4o, Claude 3.5 Sonnet, Gemini 1.5 Pro | Reports, analysis, content writing, structured output | ~$2–5 | 33 (52%) |
| 🟠 **Advanced** | Claude Opus, GPT-o3, Gemini Ultra | Orchestration, strategy, legal, architecture | ~$10–15 | 15 (24%) |
| 🔴 **Specialist** | DeepSeek Coder, GPT-4V, DALL-E 3 | Code generation, vision, multimodal | Varies | 3 (5%) |

### **1.2 Admin Routing Controls**

*   **Per-Agent Model Assignment**:
    *   Admin can override the default tier for any agent from the dashboard.
    *   Example: Promote `recruitment_agent` from Standard → Advanced during hiring surge.

*   **Per-Department Model Default**:
    *   Set a department-wide default tier (e.g., Finance = Standard minimum).
    *   Individual agents within the department can be overridden higher but not lower.

*   **Dynamic Tier Switching**:
    *   `IF task.risk_level == "high"` → Auto-upgrade agent to Advanced for that request.
    *   `IF monthly_budget_remaining < 20%` → Auto-downgrade all Standard agents to Nano.
    *   `IF model.error_rate > 5%` → Auto-failover to fallback model.

*   **Fallback Chain**:
    ```
    Advanced → Standard → Nano (graceful degradation)
    Code → Standard (if DeepSeek unavailable)
    Vision → Standard (text-only fallback)
    ```

*   **Admin Interface**:
    *   Dropdown to set "Model Tier" per Agent.
    *   Dropdown to set "Default Tier" per Department.
    *   Slider to set "Max Cost per Request" (auto-blocks if exceeded).
    *   Toggle: "Allow Dynamic Tier Upgrade" [ON/OFF].
    *   Toggle: "Allow Auto-Downgrade on Budget Pressure" [ON/OFF].

---

## 2. Token Usage & Cost Monitoring

### **2.1 Department-Level Analytics**
A visual dashboard to track spend across Tech, Finance, HR, Sales, Marketing, Legal, and BizDev.

*   **Visualizations**:
    *   **Bar Chart**: Monthly Spend ($) by Department.
    *   **Stacked Bar**: Spend by Tier within each Department.
    *   **Line Chart**: Token Usage Trend (Daily) — color-coded by tier.
    *   **Table**: Top 10 Most Expensive Agents/Users.
    *   **Pie Chart**: Cost distribution by Model Tier.

*   **Data Structure**:
    ```json
    {
      "department_id": "finance",
      "agent_id": "accounting_agent",
      "model_tier": "standard",
      "model": "claude-3-5-sonnet",
      "tokens_input": 5000,
      "tokens_output": 1000,
      "cost_usd": 0.18,
      "was_upgraded": false,
      "was_downgraded": false,
      "timestamp": "2026-02-12T10:00:00Z"
    }
    ```

*   **Budget Controls**:
    *   Set **Monthly Budget Caps** per Department (e.g., Finance: $500/mo).
    *   Set **Monthly Budget Caps** per Tier (e.g., Advanced: $500/mo company-wide).
    *   **Alerts**: Email Admin when 80% of budget is reached.
    *   **Auto-Downgrade**: When budget exceeds 90%, auto-switch non-critical agents to lower tier.
    *   **Hard Stop**: Automatically block requests if budget exceeded (optional).

> **✅ Implemented**: `BudgetEnforcer` (`core/budget.py`) provides atomic budget reservation with Redis Lua scripts. Supports per-department and per-agent soft/hard limits. Budget check runs on every LLM call and tool execution via the Chokepoint Gateways.

### **2.2 Estimated Monthly Cost by Tier**

| Tier | Agents | Est. Monthly Cost | % of Total |
|------|--------|-------------------|------------|
| 💚 Nano | 9 | ~$20 | 1% |
| 💛 Standard | 33 | ~$693 | 50% |
| 🟠 Advanced | 15 | ~$540 | 39% |
| 🔴 Specialist | 3 | ~$135 | 10% |
| **Total** | **63** | **~$1,389/mo** | **100%** |

> **Savings**: 69% compared to running all agents on Advanced tier (~$4,536/mo).

---

## 3. General Policy & Governance

### **3.1 ABAC Policy Engine (Implemented ✅)**

The `PolicyEngine` (`core/policy_engine.py`) evaluates every action against YAML rules (`policies/default.yaml`). 8 rules are currently active:

| Rule | Condition | Decision |
|------|-----------|----------|
| PII Protection | resource sensitivity = PII | require_approval + data ticket |
| Finance Approval | action = transfer/payment > $100K | require_approval |
| After-Hours Block | time outside 06:00-22:00 | deny |
| High-Risk Tools | tool risk ≥ critical | require_approval |
| Legal Restrictions | department = legal, action = external_comm | require_approval |
| External Communications | action = send_email/post_public | require_approval |
| Payroll Access | resource = payroll/salary | require_approval |
| Write Audit | action = write | allow + log_full_payload |

Admins can add/edit rules by modifying `policies/default.yaml` — no code changes needed.

### **3.2 Global System Prompts & Guardrails**
Admins can define the "Constitution" that all agents must follow.

*   **Policy Editor**:
    *   "Global System Prompt": *You are an employee of Company AI. You must be polite and professional.*
    *   "Sensitive Data Redaction": Toggle [ON/OFF] to auto-mask PII (emails, SSNs) before sending to LLM.
    *   "Forbidden Topics": List of keywords to block.

### **3.3 User Administration**
*   **Role Management**:
    *   **Super Admin**: Full access to all settings.
    *   **Department Admin**: Can only view/edit their department's budget and agents.
    *   **Operator**: Can only use the "Claw" dashboard to run tasks.
*   **Audit Log**: SHA-256 hash chain audit trail — who changed what policy and when. Tamper-evident via `AuditService.verify_chain_integrity()`.

---

## 4. Database Integration Control

### **4.1 Connection Registry**
Instead of hardcoding DB credentials in agent code, Admins manage them centrally.

*   **Admin UI**:
    *   **Add New Data Source**: Form for (Postgres, Snowflake, MySQL).
    *   **Access Level**: Select `Read-Only` or `Read-Write`.
    *   **Assign to**: Select which Agents/Departments can access this DB.

*   **Security**:
    *   Credentials stored in **Vault** (e.g., AWS Secrets Manager / HashiCorp Vault).
    *   Agents request a temporary token or handle via the backend proxy.

---

## 5. Configuration Versioning & Rollback

### **5.1 Version Control for All Configs**
Every change to the following items is versioned with full history:
*   System Prompts (Global & per-department)
*   Model Routing Rules
*   Budget Caps & Thresholds
*   Policy Rules (PII redaction, forbidden topics)
*   Database Connection Registry

### **5.2 Change Log**
Each version records:
*   `who` — Admin user ID
*   `when` — ISO timestamp
*   `old_value` — Previous configuration
*   `new_value` — Updated configuration
*   `reason` — Optional note explaining the change

### **5.3 Rollback**
*   One-click rollback to any previous version from the Admin Dashboard.
*   Rollback triggers a notification to all admins.
*   Critical configs (e.g., security policies) require dual-admin approval to roll back.

---

## 6. Agent Evaluation & Quality Scoring

### **6.1 LLM-as-Judge**
A dedicated evaluator model scores agent outputs on:
*   **Accuracy**: Does the output match the expected result?
*   **Completeness**: Did the agent address all parts of the task?
*   **Safety**: Does the output contain PII, harmful content, or hallucinations?

### **6.2 Agent KPIs Dashboard**
Track per-agent performance metrics:
*   Task Success Rate (%)
*   Average Task Completion Time
*   Human Override Rate (how often humans reject agent output)
*   Hallucination Detection Rate
*   Cost per Successful Task

### **6.3 A/B Testing**
*   Test prompt variations against each other with real tasks.
*   Statistical significance tracking before promoting a new prompt to production.

---

## 7. UI Wireframe: Admin Dashboard

```
+-----------------------------------------------------------+
|  [Admin] Governance Dashboard         [User: Admin]       |
+-----------------------------------------------------------+
|  Overview | Model Tiers | Budgets | Integrations | Eval  |
+-----------------------------------------------------------+
|                                                           |
|  [$$ Cost Overview]              [Token Usage - 24h]      |
|  Total: $1,389 (This Month)      [Graph: by Tier]         |
|  Forecast: $1,500     Savings: 69% vs all-Advanced        |
|                                                           |
+-----------------------------------------------------------+
|  [Model Tier Assignments]                                 |
|  > Dept: Tech                                             |
|    Tech Supervisor   => [🟠 Advanced ▼] [Claude Opus ▼]   |
|    Backend Engineer  => [🔴 Specialist▼] [DeepSeek  ▼]    |
|    QA Agent          => [💛 Standard ▼] [Claude Sonnet▼]   |
|  > Dept: Finance                                          |
|    Finance Supervisor=> [🟠 Advanced ▼] [GPT-o3     ▼]    |
|    Accounting Agent  => [💛 Standard ▼] [GPT-4o     ▼]    |
|  > Dept: Marketing                                        |
|    Content Maker     => [🔴 Specialist▼] [GPT-4V    ▼]    |
|    Social Media      => [💚 Nano     ▼] [GPT-4o-mini▼]    |
|  [Override Agent Tier] [Reset to Default]                 |
+-----------------------------------------------------------+
|  [Budget by Tier]                                         |
|  💚 Nano:      $16  / $50   [========-----] 32%           |
|  💛 Standard:  $525 / $800  [==========---] 66%           |
|  🟠 Advanced:  $468 / $600  [===========--] 78% ⚠️        |
|  🔴 Specialist:$135 / $200  [=========----] 68%           |
+-----------------------------------------------------------+
|  [Dynamic Tier Controls]                                  |
|  [x] Allow Auto-Upgrade on High-Risk Tasks                |
|  [x] Allow Auto-Downgrade on Budget Pressure              |
|  [ ] Hard Stop on Budget Exceeded                         |
+-----------------------------------------------------------+
|  [Agent Performance]                                      |
|  > Global Supervisor: Success: 96% | Tier: Advanced       |
|  > Accounting Agent:  Success: 98% | Tier: Standard       |
|  > Social Media:      Success: 92% | Tier: Nano           |
|  > Backend Engineer:  Success: 94% | Tier: Specialist     |
+-----------------------------------------------------------+
```

## 8. Recommendation Summary

1.  **Use LiteLLM**: It acts as a proxy server that handles logic for Model Routing, Budget Tracking, and Token Counting out-of-the-box.
2.  **4-Tier Model Strategy**: Nano (14%), Standard (52%), Advanced (24%), Specialist (5%) — saves 69% vs all-Advanced.
3.  **Centralize Secrets**: Never give raw DB credentials to agents. Use the Connection Registry pattern.
4.  **Admin Override Per Agent**: Allow admins to promote/demote individual agents between tiers as workload demands change.
5.  **Dynamic Tier Switching**: Auto-upgrade on high-risk tasks, auto-downgrade on budget pressure.
6.  **Version Everything**: All config changes (including tier assignments) must be versioned with rollback capability.
7.  **Evaluate Continuously**: Use LLM-as-Judge to score agent outputs and track KPIs over time — correlate quality with model tier.
8.  **Budget Per Tier**: Set separate budget caps for each tier to prevent Advanced tier from consuming entire budget.

---

## 9. Implemented Control Plane (✅ Live)

The following governance components are fully implemented in the codebase:

| Component | File | Admin Use Case |
|-----------|------|--------------|
| **PolicyEngine** | `core/policy_engine.py` | Edit YAML rules → instant policy changes |
| **BudgetEnforcer** | `core/budget.py` | Set soft/hard limits per dept & agent |
| **ApprovalGate** | `core/approval_gate.py` | Auto-pause on high-risk → human approve/reject |
| **MetricsCollector** | `core/metrics.py` | Real-time cost/success dashboard |
| **AuditService** | `services/audit_service.py` | Tamper-evident hash chain audit trail |
| **CircuitBreaker** | `core/resilience.py` | Auto-failover on provider failures |
| **TraceContext** | `core/tracing.py` | End-to-end request tracing |
