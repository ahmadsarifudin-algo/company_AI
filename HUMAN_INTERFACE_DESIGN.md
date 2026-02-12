# Human Interface Channel - The "Claw" Dashboard Design

> **Updated Feb 2026**: Reflects implemented `ApprovalGate`, `PolicyEngine`, `BudgetEnforcer`, and `TraceContext` modules.

## 1. Concept: Mission Control

The "Claw" Dashboard serves as the central command post for human operators to interact with the autonomous agent fleet. It provides visibility into agent thought processes, control over high-stakes decisions, and a structured interface for task submission.

---

## 2. Core Features

### **2.1 Task Input (The Launchpad)**
- **Interface**: A structured form or natural language chat interface.
- **Workflow**:
  1.  User enters a high-level goal (e.g., "Analyze Q3 sales data").
  2.  System generates a **Plan JSON** proposal.
  3.  User reviews and **Approves** the plan to start execution.
- **Technology**: Next.js Form + Shadcn/UI -> FastAPI `/submit-plan` -> LangGraph Supervisor.

### **2.2 Mission Monitor (Live Feed)**
- **Interface**: A real-time stream of agent activities.
- **Data Points**:
  - **Agent Name**: Which specialist is acting?
  - **Status**: Thinking, Calling Tool, Executing, Waiting.
  - **Thought Process**: The "inner monologue" (Chain-of-Thought).
  - **Tool Usage**: Which tool was called and its output (e.g., `git status`, `python script.py`).
- **Technology**:
  - Backend: LangGraph `astream_events` -> Redis Pub/Sub.
  - Frontend: WebSocket -> React `useSWRSubscription` or custom hook -> Terminal-like UI.

### **2.3 Human Approval Queue (The "Claw" Mechanism)**
- **Concept**: A "Pause & Resume" capability for critical actions.
- **Backend**: `ApprovalGate` (`core/approval_gate.py`) state machine + `PolicyEngine` (`core/policy_engine.py`) trigger. ✅ Implemented.
- **Workflow**:
  1.  Agent calls `LLMClient`/`ToolBroker`/`DataAccessLayer` (Chokepoint Gateway).
  2.  Gateway checks `PolicyEngine` → returns `REQUIRE_APPROVAL` for high-risk actions.
  3.  `ApprovalGate.check()` creates a pending approval with full context.
  4.  Dashboard shows a "Blocked" task with Plan, Proposed Action, Risk Level, and `trace_id`.
  5.  Human operator clicks **Approve** or **Reject** (with feedback).
  6.  `ApprovalGate.approve()/reject()` updates state. `IdempotencyGuard` prevents duplicate side-effects.
  7.  Execution **Resumes** with the human's decision.
- **Technology**: `ApprovalGate` state machine + LangGraph Checkpoints (`interrupt_before=["tool_call"]`) + FastAPI `/approve/{thread_id}`.

### **2.4 Artifact Browser**
- **Interface**: A file explorer view of generated outputs.
- **Features**:
  - Live preview of Markdown, Code, and JSON files.
  - Diff viewer for code changes.
  - Download/Export capability.

---

## 3. UI Wireframe Concepts

### **Dashboard Layout**
```
+-------------------------------------------------------+
|  [Logo] Company AI - Mission Control                  |
+-------------------------------------------------------+
|  Active Tasks (3) |  Waiting Approval (1) |  Agents   |
+-------------------+-----------------------+-----------+
|                   |                       |           |
|  > Task #123      |  > Task #125          | [Lawyer]  |
|    "Refactor DB"  |    "Deploy v2"        |  Idle     |
|    [Running...]   |    [BLOCKED]          |           |
|                   |                       | [Coder]   |
|  > Task #124      |  Reason: Prod Deploy  |  Working  |
|    "Audit Logs"   |  Risk: High           |           |
|    [Thinking...]  |                       | [SRE]     |
|                   |  [APPROVE] [REJECT]   |  Sleeping |
|                   |                       |           |
+-------------------+-----------------------+-----------+
|  Terminal / Logs                                      |
|  > [Coder] Reading file utils.py...                   |
|  > [Coder] Found syntax error on line 42...           |
|  > [System] Checkpoint reached. Waiting for human...  |
+-------------------------------------------------------+
```

---

## 4. Technical Implementation Strategy

### **Backend (FastAPI + LangGraph)**
1.  **State Persistence**: Use `AsyncPgSaver` (Postgres) to store graph state.
2.  **Streaming Endpoint**: `/stream/{thread_id}` using `Server-Sent Events (SSE)` or WebSockets to push graph updates.
3.  **Approval Endpoint**:
    ```python
    @app.post("/runs/{thread_id}/resume")
    async def resume_run(thread_id: str, feedback: str):
        # Update state with human input
        graph.update_state(thread_id, {"human_feedback": feedback})
        # Resume execution
        graph.stream(None, thread_id=thread_id)
    ```

### **Frontend (Next.js)**
1.  **Real-time Hook**: Custom `useAgentStream` hook to handle SSE parsing.
2.  **Components**:
    - `TaskCard`: Shows task metadata and status status.
    - `ApprovalModal`: Pops up when a `interrupt` event is received.
    - `LogTerminal`: Renders ansi-colored logs from the agent.

---

## 5. Security & Control Plane Integration

- **ABAC PolicyEngine** (✅ Implemented): `PolicyEngine` evaluates every action. Dashboard queries show which rules triggered an approval requirement.
- **Audit Logging** (✅ Implemented): `AuditService.emit()` creates SHA-256 hash chain entries. Every "Approve" click logs `user_id`, `timestamp`, `decision`, `trace_id`, and `span_id` to the tamper-evident ledger.
- **Budget Visibility** (✅ Implemented): `MetricsCollector.get_dashboard()` provides real-time cost/token/success metrics per department and agent. Dashboard can display `BudgetEnforcer` soft/hard limit status.
- **Tracing** (✅ Implemented): `TraceContext` provides `trace_id` per request. Dashboard can link any task back to the full trace of audit events via `AuditService.verify_chain_integrity(trace_id)`.
- **Sanitization**: All user input in the "Reject" feedback field is sanitized before being passed back to the agent.

---

## 6. Notification & Escalation System

### **6.1 Push Notifications**
When a task enters the Approval Queue, the system immediately sends notifications via:
- **Slack**: Webhook message to a configured channel (e.g., `#agent-approvals`) with task context and approve/reject buttons.
- **Email**: HTML email via Nodemailer with task summary, risk level, and a direct link to the dashboard.
- **Browser Push**: Web Push API notification if the user has the dashboard open.

### **6.2 Escalation Timer**
If a task is not approved within the SLA window, it auto-escalates:
- **Low Risk**: 4 hours → Escalate to Department Admin.
- **Medium Risk**: 2 hours → Escalate to Department Admin.
- **High Risk**: 30 minutes → Escalate to Enterprise Supervisor + email Executive.

### **6.3 Notification Preferences**
- Admin can configure per-user notification preferences (Slack only, Email only, All).
- Quiet hours: Suppress non-critical notifications outside work hours.

