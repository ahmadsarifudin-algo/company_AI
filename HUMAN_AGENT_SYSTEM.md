# Human-Agent Pairing System — Recommendation Design

## 1. Core Concept: 1 Agent ↔ 1 Human

Every AI Agent is a **personal assistant** to a specific human employee. The human is always the **supervisor** — agents propose, humans approve. Agents handle execution, coordination, and reporting while humans maintain full control.

> **Minimum 32 humans** are needed to supervise all 63 agents across 7 departments + enterprise. See [HUMAN_AGENT_MAPPING.md](file:///c:/Users/sarif/Documents/project_antigravity/company_AI/HUMAN_AGENT_MAPPING.md) for the full org chart and staffing plan.

```mermaid
graph LR
    subgraph "Finance Department"
        H1([Ahmad - CFO]) <--> A1[Finance Supervisor Agent]
        H2([Budi - Accountant]) <--> A2[Accounting Agent]
        H3([Citra - Auditor]) <--> A3[Audit Agent]
    end
    
    subgraph "Tech Department"
        H4([Doni - CTO]) <--> A4[Tech Supervisor Agent]
        H5([Eka - Backend Dev]) <--> A5[Backend Engineer Agent]
        H6([Fajar - QA]) <--> A6[QA Agent]
    end
    
    subgraph "HR Department"
        H7([Gita - HR Head]) <--> A7[HR Supervisor Agent]
        H8([Hana - Recruiter]) <--> A8[Recruitment Agent]
    end
    
    subgraph "Sales Department"
        H9([Ivan - Sales Head]) <--> A9[Sales Supervisor Agent]
        H10([Joko - Account Exec]) <--> A10[Deal Intelligence Agent]
    end

    subgraph "Marketing Department"
        H11([Karin - Marketing Head]) <--> A11[Marketing Supervisor Agent]
        H12([Lina - Content Strategist]) <--> A12[Content Creator Agent]
    end

    subgraph "Legal Department"
        H13([Maya - Corporate Counsel]) <--> A13[Legal Supervisor Agent]
        H14([Nanda - Contract Specialist]) <--> A14[Contract Drafting Agent]
    end

    subgraph "BizDev Department"
        H15([Omar - BizDev Director]) <--> A15[BizDev Supervisor Agent]
        H16([Putri - Market Analyst]) <--> A16[Market Research Agent]
    end
    
    A1 <-.->|Agent Coordination| A4
    A1 <-.->|Agent Coordination| A7
    A4 <-.->|Agent Coordination| A9
    A13 <-.->|Legal Advisory| A1 & A7 & A9
    A15 <-.->|Strategy Sync| A9 & A11
```

---

## 2. Multi-Channel Communication

Humans interact with their agent through **WhatsApp, Email, or Dashboard** — whichever is most convenient.

### **2.1 Channel Architecture**

```mermaid
graph TD
    Human([Human Employee]) -->|Chat| WA[WhatsApp Business API]
    Human -->|Email| Email[Email Service - Gmail/Outlook]
    Human -->|Web| Dashboard[Claw Dashboard]
    
    WA --> Router[Message Router Service]
    Email --> Router
    Dashboard --> Router
    
    Router --> NLU[Intent Parser - LLM]
    NLU --> AgentGateway[Agent Gateway]
    
    AgentGateway --> PairedAgent[Paired Agent]
    
    PairedAgent -->|Reply| Router
    Router -->|Same Channel| Human
```

### **2.2 Supported Interactions per Channel**

| Action | WhatsApp | Email | Dashboard |
|--------|----------|-------|-----------|
| Ask a task | ✅ Chat | ✅ Email subject | ✅ Form |
| Get status update | ✅ "Status?" | ✅ Auto digest | ✅ Real-time |
| Receive report | ✅ PDF attachment | ✅ PDF + inline | ✅ Artifact browser |
| Approve / Reject | ✅ Reply "Approve" / "Reject" | ✅ Click button in email | ✅ Approve Queue |
| Schedule meeting | ✅ "Schedule meeting with CTO" | ✅ Email request | ✅ Calendar widget |
| Urgent alert | ✅ Push message | ✅ Flagged email | ✅ Toast notification |

### **2.3 Technology Stack**

| Component | Technology |
|-----------|------------|
| WhatsApp | **WhatsApp Business API** (via Twilio or Meta Cloud API) |
| Email | **Gmail API** / **Microsoft Graph API** + **Nodemailer** |
| Intent Parsing | **LLM** (parse natural language → structured action) |
| Message Queue | **Redis Pub/Sub** (route messages to correct agent) |

---

## 3. Task Request Flow

A human can ask their agent to do tasks at any time via any channel.

### **3.1 Flow Diagram**

```mermaid
sequenceDiagram
    participant H as Human (Budi)
    participant WA as WhatsApp
    participant R as Message Router
    participant A as Budi's Agent
    participant S as Agent System

    H->>WA: "Tolong buatkan laporan keuangan Q1"
    WA->>R: Forward message
    R->>R: Parse intent → {action: "create_report", type: "finance_Q1"}
    R->>A: Route to Budi's Agent
    A->>S: Execute task (query DB, generate report)
    S-->>A: Report artifact ready
    A->>WA: "Laporan Q1 sudah selesai ✅" + PDF attachment
    WA->>H: Receive report
```

### **3.2 Intent Parser Examples**

| Human Message (Any Language) | Parsed Intent |
|------------------------------|---------------|
| "Buatkan laporan penjualan bulan ini" | `{action: "create_report", type: "sales_monthly"}` |
| "Status task deploy kemarin?" | `{action: "check_status", task_ref: "latest_deploy"}` |
| "Approve" | `{action: "approve", context: "pending_approval"}` |
| "Schedule meeting with HR head tomorrow 2pm" | `{action: "schedule_meeting", with: "HR_head", time: "tomorrow 14:00"}` |
| "Reject, need more data" | `{action: "reject", feedback: "need more data"}` |

---

## 4. Report Delivery System

Agents proactively send reports or respond to report requests via the human's preferred channel.

### **4.1 Report Types**

| Report | Trigger | Format |
|--------|---------|--------|
| Daily Digest | Automated (every morning) | WhatsApp summary + Email PDF |
| Task Completion | On task finish | WhatsApp notification + Email full report |
| Weekly Summary | Automated (every Monday) | Email PDF with charts |
| Ad-hoc Report | Human request | Reply on same channel |
| Budget Alert | Threshold exceeded | WhatsApp urgent + Email |

### **4.2 Report Template**

```
📊 Daily Report — Finance Department
Date: 2026-02-12

✅ Completed Tasks (3):
  1. Reconciliation Q1 → Done
  2. Invoice processing → 47 invoices processed
  3. Budget variance analysis → Report attached

⏳ In Progress (1):
  1. Annual audit preparation → 60% complete

⚠️ Needs Your Approval (1):
  1. Transfer $15,000 to vendor → [Approve] [Reject]

💰 Budget Usage: $340 / $500 (68%)
```

---

## 5. Approval System (Multi-Channel)

Humans approve or reject agent actions through whichever channel they prefer.

### **5.1 Approval Flow**

```mermaid
sequenceDiagram
    participant A as Agent
    participant S as System
    participant WA as WhatsApp
    participant EM as Email
    participant H as Human

    A->>S: Request approval (e.g., "Deploy to production")
    S->>WA: "🔔 Approval needed: Deploy v2.1 to production. Risk: HIGH. Reply 'Approve' or 'Reject'"
    S->>EM: HTML email with [Approve] [Reject] buttons + context
    
    alt Human replies via WhatsApp
        H->>WA: "Approve"
        WA->>S: Parse → {action: "approve"}
    else Human clicks email button
        H->>EM: Click [Approve]
        EM->>S: Webhook → {action: "approve"}
    end
    
    S->>A: Resume execution with approval
    A->>WA: "✅ Deploy v2.1 completed successfully"
```

### **5.2 Escalation Rules**

| Risk Level | Wait Time | Escalation |
|------------|-----------|------------|
| Low | 4 hours | Remind human via WhatsApp |
| Medium | 2 hours | Remind + CC Department Head |
| High | 30 minutes | Remind + Escalate to Executive |
| Critical | 10 minutes | Phone call + All channels |

---

## 6. Meeting Scheduling System

Humans can ask their agent to schedule meetings. The agent coordinates with other agents to find availability and creates calendar events.

### **6.1 Scheduling Flow**

```mermaid
sequenceDiagram
    participant H1 as Human A (CFO)
    participant A1 as CFO's Agent
    participant SYS as Scheduling Service
    participant A2 as CTO's Agent
    participant H2 as Human B (CTO)

    H1->>A1: "Schedule meeting with CTO tomorrow to discuss budget"
    A1->>SYS: Request meeting {with: "CTO", topic: "budget", preferred: "tomorrow"}
    SYS->>SYS: Check Google Calendar for both H1 & H2
    SYS->>SYS: Find available slot → Tomorrow 14:00-15:00
    SYS->>SYS: Create Zoom link
    SYS->>A2: Notify CTO's Agent about meeting request
    A2->>H2: 📅 "Meeting request from CFO: Budget Discussion. Tomorrow 14:00. [Accept] [Propose New Time]"
    H2->>A2: "Accept"
    A2->>SYS: Confirmed
    SYS->>SYS: Create Google Calendar event for both
    SYS->>A1: Meeting confirmed
    A1->>H1: "✅ Meeting with CTO confirmed. Tomorrow 14:00-15:00. Zoom link: https://zoom.us/..."
```

### **6.2 Technology Integration**

| Service | API | Purpose |
|---------|-----|---------|
| Google Calendar | **Google Calendar API v3** | Check availability, create events |
| Zoom | **Zoom API** | Generate meeting links |
| Microsoft Teams | **Microsoft Graph API** (optional) | Alternative to Zoom |
| WhatsApp | **WhatsApp Business API** | Send invitations & reminders |
| Email | **Gmail / SMTP** | Send calendar invites (.ics) |

### **6.3 Smart Scheduling Features**

- **Auto-detect timezone**: Based on human's profile.
- **Conflict resolution**: If no slot available, propose 3 alternatives.
- **Recurring meetings**: "Schedule weekly standup every Monday 9am".
- **Reminder**: Send WhatsApp reminder 15 minutes before meeting.
- **Meeting prep**: Agent prepares agenda and relevant documents before the meeting.

---

## 7. Agent-to-Agent Coordination

When a task requires cross-department cooperation, agents coordinate automatically and keep their humans informed.

### **7.1 Coordination Flow**

```mermaid
sequenceDiagram
    participant H1 as Budi (Accountant)
    participant A1 as Budi's Agent
    participant GS as Global Supervisor
    participant A2 as Eka's Agent (Backend Dev)
    participant H2 as Eka (Backend Dev)

    H1->>A1: "The payment API is returning errors since yesterday"
    A1->>A1: Detect: This requires Tech department
    A1->>GS: Cross-department request → Tech
    GS->>A2: Route to Eka's Agent (Backend)
    A2->>H2: 📢 "Request from Finance: Payment API errors since yesterday. Investigating..."
    A2->>A2: Investigate → Check logs, find bug
    A2->>H2: "Found bug in payment handler. Fix ready. Approve deploy?"
    H2->>A2: "Approve"
    A2->>A2: Deploy fix
    A2->>GS: Task complete → Notify Finance
    GS->>A1: Fix deployed
    A1->>H1: "✅ Payment API issue resolved. Eka deployed a fix 10 minutes ago. Tested & working."
```

### **7.2 Coordination Rules**

| Scenario | Agent Behavior |
|----------|---------------|
| Simple info request | Agent-to-Agent direct. No human approval needed. |
| Task execution | Agent asks its human for approval before acting. |
| Cross-department task | Route via Global Supervisor. Both humans are informed. |
| Meeting scheduling | Agent-to-Agent coordination. Both humans confirm. |
| Conflicting priorities | Escalate to department heads via their agents. |

---

## 8. Human Profile & Preferences Registry

Each human has a profile that their paired agent uses to personalize interactions.

```json
{
  "human_id": "budi_001",
  "name": "Budi Santoso",
  "role": "Senior Accountant",
  "department": "finance",
  "paired_agent": "accounting_agent_01",
  "communication": {
    "preferred_channel": "whatsapp",
    "whatsapp_number": "+62812XXXXXXX",
    "email": "budi@company.com",
    "language": "id",
    "timezone": "Asia/Jakarta",
    "quiet_hours": {"start": "21:00", "end": "07:00"}
  },
  "notifications": {
    "daily_digest": true,
    "digest_time": "08:00",
    "urgent_override_quiet": true,
    "approval_reminder_minutes": 30
  },
  "calendar": {
    "google_calendar_id": "budi@company.com",
    "default_meeting_duration": 30,
    "preferred_meeting_hours": {"start": "09:00", "end": "17:00"}
  },
  "permissions": {
    "auto_approve_below_usd": 100,
    "max_task_budget_usd": 50
  }
}
```

---

## 9. Complete System Architecture

```mermaid
graph TD
    subgraph "Human Layer"
        H1([Human 1]) & H2([Human 2]) & H3([Human N])
    end

    subgraph "Communication Layer"
        WA[WhatsApp Business API]
        Email[Email Service]
        Dash[Claw Dashboard]
        Cal[Google Calendar API]
        Zoom[Zoom API]
    end

    subgraph "Routing Layer"
        Router[Message Router]
        NLU[Intent Parser - LLM]
        PairMap[(Human-Agent Pair Registry)]
    end

    subgraph "Agent Layer"
        GS[Global Supervisor]
        A1[Agent 1] & A2[Agent 2] & A3[Agent N]
    end

    subgraph "Execution Layer"
        ModelGW[Model Gateway - LiteLLM]
        Tools[Tool Sandbox]
        RAG[(Knowledge Base)]
    end

    subgraph "Data Layer"
        DB[(PostgreSQL + RLS)]
        Audit[(Audit Log)]
        Artifacts[(S3 Artifacts)]
    end

    H1 & H2 & H3 <--> WA & Email & Dash
    WA & Email & Dash --> Router
    Router --> NLU
    NLU --> PairMap
    PairMap --> A1 & A2 & A3

    A1 & A2 & A3 <--> GS
    A1 & A2 & A3 <--> ModelGW & Tools & RAG
    A1 & A2 & A3 --> Cal & Zoom
    A1 & A2 & A3 --> DB & Audit & Artifacts

    A1 & A2 & A3 -->|Reply| Router
    Router -->|Same Channel| WA & Email & Dash
```

---

## 10. Implementation Roadmap

| Phase | Weeks | Deliverables |
|-------|-------|-------------|
| **Phase 1**: Core Pairing | 1-2 | Human-Agent Registry, Message Router, Dashboard chat |
| **Phase 2**: WhatsApp Integration | 3-4 | WhatsApp Business API, Intent Parser, 2-way messaging |
| **Phase 3**: Email Integration | 5-6 | Gmail/Outlook API, Report delivery, Email approval buttons |
| **Phase 4**: Calendar & Meetings | 7-8 | Google Calendar API, Zoom API, Cross-agent scheduling |
| **Phase 5**: Agent Coordination | 9-10 | Cross-department routing, Agent-to-Agent protocol |
| **Phase 6**: Intelligence | 11-12 | Smart scheduling, Meeting prep, Proactive insights |

---

## 11. Recommendation Summary

1. **WhatsApp First**: Most Indonesians are on WhatsApp. Make it the primary channel for quick tasks and approvals.
2. **Email for Records**: Use email for formal reports, audit trails, and official approvals.
3. **Dashboard for Power Users**: The Claw Dashboard is for admins and users who need deep visibility.
4. **Smart Intent Parsing**: Use LLM to parse natural language in any language (Bahasa Indonesia, English) into structured actions.
5. **Respect Human Time**: Quiet hours, timezone awareness, and smart notification batching to avoid alert fatigue.
6. **Agent Coordinates, Human Decides**: Agents handle all the back-and-forth coordination. Humans only see the final result or approval request.
7. **Calendar Intelligence**: Auto-detect conflicts, suggest times, and prepare meeting agenda automatically.
