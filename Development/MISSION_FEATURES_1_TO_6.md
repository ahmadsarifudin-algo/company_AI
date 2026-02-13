# 🎯 MISSION: Features 1-6 Implementation

> **Created:** 2026-02-13  
> **Status:** IN PROGRESS  
> **Priority:** Complete all 6 features in order

---

## Progress Tracker

- [ ] **Feature 1:** Tampilkan Hasil AI di Dashboard
- [ ] **Feature 2:** System Prompt dari DB
- [ ] **Feature 3:** Tools Integration via ToolBroker
- [ ] **Feature 4:** Celery Auto-Execute Worker
- [ ] **Feature 5:** Task Detail Page
- [ ] **Feature 6:** Chat with Agent Page

---

## Feature 1: Tampilkan Hasil AI di Dashboard

**Effort:** 🟢 15 min  
**Goal:** Show `result_json.output` in task table + expandable detail

### Files to Modify
- `frontend/src/app/(admin)/tasks/page.tsx`
  - Add "Result" column showing first 100 chars of `result_json.output`
  - Add expandable row/modal to show full AI response
  - Style completed tasks green, failed red

---

## Feature 2: System Prompt dari DB

**Effort:** 🟢 15 min  
**Goal:** Use agent's `system_prompt` / `system_prompt_override` in executor

### Files to Modify
- `backend/app/agents/state.py` — Add `system_prompt: str` field to `AgentState`
- `backend/app/services/agent_executor.py` — Load `agent.system_prompt_override or agent.system_prompt` → inject into `initial_state`
- `backend/app/agents/supervisor.py` — Use `state["system_prompt"]` in `agent_executor_node` instead of generic prompt

---

## Feature 3: Tools Integration via ToolBroker

**Effort:** 🟡 30 min  
**Goal:** Agent can call tools (search, calculate, etc.) during execution

### Files to Modify
- `backend/app/agents/supervisor.py` — Modify `agent_executor_node`:
  1. Import `get_tool_broker` and `AgentContext`
  2. Get available tools via `broker.get_available_tools(role, department)`
  3. Pass tool definitions to Gemini/OpenAI (function calling format)
  4. Tool execution loop (max 5 iterations):
     - LLM responds with tool calls → execute via `broker.execute()` → re-call LLM
     - LLM responds with text → return as final result
  5. Track `tool_call_count` and `token_usage` in state

> **Reference:** Same pattern already in `TaskOrchestrator._execute()` (lines 426-598 of `task_orchestrator.py`)

---

## Feature 4: Celery Auto-Execute Worker

**Effort:** 🟡 30 min  
**Goal:** Background worker polls and auto-executes pending tasks

### Files to Create
- `backend/app/workers/__init__.py` — Empty init
- `backend/app/workers/celery_worker.py`:
  - Configure Celery app with Redis broker
  - Define `execute_pending_tasks` periodic task (every 60s)
  - Query DB for `status="pending"` + `assigned_agent_id IS NOT NULL`
  - Call `AgentExecutorService.execute_task()` for each

> **Note:** Requires Redis running. Uses existing `REDIS_URL` env var.

---

## Feature 5: Task Detail Page

**Effort:** 🟡 45 min  
**Goal:** Full page `/tasks/[id]` showing execution result + audit

### Files to Create
- `frontend/src/app/(admin)/tasks/[id]/page.tsx`:
  - Fetch task by ID
  - Display: metadata, full AI response (markdown), execution metrics, errors
  - Re-execute button

### Files to Modify
- `frontend/src/lib/api.ts` — Add `getTask(id)` method
- `frontend/src/app/(admin)/tasks/page.tsx` — Make task titles clickable → `/tasks/{id}`

---

## Feature 6: Chat with Agent

**Effort:** 🔴 1 jam  
**Goal:** Real-time chat UI with selected agent

### Backend
Already exists: `POST /api/v1/execution/chat` (accepts `{agent_id, message, thread_id}`)

### Files to Create
- `frontend/src/app/(admin)/chat/page.tsx`:
  - Agent selector dropdown
  - Message input + send button
  - Chat history (bubble style)
  - Thread persistence via `thread_id`
  - Typing indicator
  - Markdown rendering

### Files to Modify
- `frontend/src/lib/api.ts` — Add `ChatRequest`, `ChatResponse`, `chatWithAgent()` method
- `frontend/src/components/AdminSidebar.tsx` — Add "💬 Chat" menu item

---

## Execution Order

```
Feature 1 (Show Result) → Feature 2 (System Prompt) → Feature 3 (Tools)
    ↓                                                       ↓
Feature 5 (Detail Page)                              Feature 4 (Celery)
    ↓
Feature 6 (Chat Page)
```

## Verification Checklist

| # | Test | Status |
|---|------|--------|
| 1 | Execute task → result visible in table + expandable | ⬜ |
| 2 | Set system_prompt_override on agent → execute → verify prompt used | ⬜ |
| 3 | Execute task → verify tool calls in response + audit log | ⬜ |
| 4 | Start Celery worker → create pending task → auto-executed within 60s | ⬜ |
| 5 | Click task row → detail page loads with full result | ⬜ |
| 6 | Open /chat → select agent → send message → get response | ⬜ |
