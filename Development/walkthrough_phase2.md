# Walkthrough — Plan Perbaikan Agent System v2

> Dokumen ini di-append per fase. TIDAK di-overwrite.

---

## Phase 0 — "Make it Reply" (Closed-loop Telegram)

**Tanggal**: 2026-02-12  
**Status**: ✅ Selesai

### Tujuan

Telegram inbound → LLM → outbound reply. Setiap pesan harus dapat jawaban.

### Analisis

Setelah tracing seluruh flow (gateway → orchestrator → LLM → dispatcher → Telegram API), ditemukan:

| Path | Status Sebelumnya |
|------|------------------|
| **TelegramPoller** (long-polling) | ✅ Sudah bekerja end-to-end |
| **Gateway webhook** (`POST /api/v1/gateway/telegram`) | ⚠️ Blocking — await full LLM pipeline, risiko timeout |

**Flow yang sudah terwiring**:
```
gateway.py → TaskOrchestrator.submit()
  → IntentRouter.route()
  → DepartmentGuard.enforce()
  → SessionManager.get_or_create()
  → _execute() → SoulResolver + LLM call + ResponseShaper
  → _dispatch_reply() → NotificationDispatcher._send_telegram()
  → Telegram sendMessage API
```

### Perubahan

#### [MODIFY] `backend/app/api/v1/gateway.py`

**Problem**: Webhook handler `await TaskOrchestrator.submit(message)` — sinkron, butuh 5-30 detik (LLM latency). Telegram akan retry webhook jika tidak ACK dalam ~60s.

**Fix**: 
- ACK Telegram **segera** (`200 OK` < 100ms)
- Proses LLM via `asyncio.create_task()` di background
- Tambah `_process_telegram_message()` helper dengan error handling + fallback reply

```diff
- task = await TaskOrchestrator.submit(message)
- return JSONResponse(content={"status": "received", "task_id": task.task_id, ...})
+ asyncio.create_task(_process_telegram_message(message))
+ return JSONResponse(content={"status": "accepted"}, status_code=200)
```

**Error handling**: Jika LLM gagal total, user tetap terima pesan error via `NotificationDispatcher.send()`.

### Yang Sudah Bekerja (tanpa perubahan)

- `TelegramPoller` → `TaskOrchestrator.submit()` → reply ✅
- `_execute()` → fallback error reply on exception ✅  
- `NotificationDispatcher._send_telegram()` → chunking + HTML fallback ✅
- `CredentialVault` → auto-load dari env var/DB ✅
- `SessionManager` → context persistence per agent+channel+peer ✅

### Test

- [x] Webhook endpoint returns 200 immediately
- [x] Background task calls orchestrator → dispatches reply
- [x] Error in background → fallback error reply sent

---

## Phase 1 — Standardize Runtime Contract

**Tanggal**: 2026-02-12  
**Status**: ✅ Selesai

### Tujuan

Semua modul "bicara" dalam format yang sama — `ResponseEnvelope` sebagai output standar orchestrator.

### Perubahan

#### [MODIFY] `backend/app/services/orchestration/task_orchestrator.py`

**Ditambahkan `ResponseEnvelope` dataclass:**
```python
@dataclass
class ResponseEnvelope:
    trace_id: str
    run_id: str
    reply_text: str
    artifacts: list[dict] = field(default_factory=list)
    control: dict = field(default_factory=dict)    # stop_reason, needs_approval
    telemetry: dict = field(default_factory=dict)   # latency_ms, provider, model
```

**Perubahan pada `_execute()`:**
- Setelah LLM response dan ResponseShaper selesai, membangun `ResponseEnvelope` dengan latency tracking
- `task.response_envelope` di-set sebelum `_dispatch_reply()`

**Perubahan pada `_dispatch_reply()`:**
- Gunakan `envelope.reply_text` jika ada, fallback ke `task.agent_response`
- Tambah logging `dispatch_reply_sent` dengan trace correlation

#### [MODIFY] `backend/app/services/orchestration/message_gateway.py`

- Updated `UnifiedMessage.channel` docs: tambah "telegram" ke channel list

### Test

- [x] ResponseEnvelope schema valid — dataclass dengan default factories
- [x] `_execute()` builds envelope with latency telemetry
- [x] `_dispatch_reply()` consumes envelope, falls back gracefully
- [x] trace_id propagated through entire flow

---

## Phase 2 — Real Execution Path

**Tanggal**: 2026-02-12  
**Status**: ✅ Selesai

### Tujuan

Wire `TaskOrchestrator._execute()` ke `AgentExecutorService.chat_with_agent()` — full LangGraph pipeline dengan RAG, memory, audit.

### Perubahan

#### [MODIFY] `backend/app/services/orchestration/task_orchestrator.py`

**Strategi: Try Agent Executor → Fallback Direct LLM**

```python
# _execute() sekarang:
agent_result = await cls._try_agent_executor(task)
if agent_result is not None:
    # Build envelope + dispatch reply + return
    return
# Fallback: direct LLM call (existing behavior)
```

**`_try_agent_executor()` method:**
1. Import `async_session` dari `app.core.deps`
2. Lookup `Agent` dari DB by `name` + `department`
3. Call `AgentExecutorService(db).chat_with_agent(agent_id, message, trace_id)`
4. Return response text, atau `None` untuk trigger fallback

**Safety:**
- `ImportError` → fallback (agent executor belum available)
- Agent not in DB → fallback (direct LLM)
- Executor returns `"failed"` → fallback

### Test

- [x] `_try_agent_executor()` resolves agent from DB
- [x] Falls back gracefully when DB/agent unavailable
- [x] ResponseEnvelope built with `execution_path: agent_executor`


