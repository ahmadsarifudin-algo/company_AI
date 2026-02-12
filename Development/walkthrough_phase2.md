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
