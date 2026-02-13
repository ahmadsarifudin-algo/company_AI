# Channel Integration — Development Walkthrough

> **Historical log** — each session is appended, never overwritten.

---

## Session 1 — 2026-02-12 (OpenClaw Research)

### Goal
Research OpenClaw (open-source AI assistant, 506 contributors, 40 releases, 21 channels) to learn best patterns for Telegram, WhatsApp, and Email channel integration.

### Research Findings

| Area | OpenClaw Pattern | Our Approach |
|------|-----------------|--------------|
| **Telegram** | grammY + long polling (no webhook URL needed) | Adopted: `getUpdates` polling |
| **WhatsApp** | Baileys (free WhatsApp Web) | Kept Twilio for enterprise safety |
| **Email** | Gmail Pub/Sub + history-based detection | Simpler: IMAP polling |
| **Routing** | Bindings map channel/peer → agent (6 priority levels) | Adopted: binding rules in orchestrator |
| **Sessions** | Keys: `agent:<id>:<channel>:dm:<peer>`, daily/idle reset | Adopted: identical pattern |
| **Queue** | Per-session FIFO, collect/steer/followup modes | Adopted: collect mode + debounce |
| **Agent Loop** | Async RPC `{runId}`, streaming, reply shaping, compaction | Learned: will adopt incrementally |
| **Access** | DM policies: pairing/allowlist/open/disabled | Planned for Phase 5 |

### Documentation Read
- `docs.openclaw.ai/channels/telegram` — grammY, long polling, draft streaming, chat commands
- `docs.openclaw.ai/channels/whatsapp` — Baileys, QR pairing, ack reactions, text chunking
- `docs.openclaw.ai/channels/email` — Gmail Pub/Sub, history-based detection
- `docs.openclaw.ai/channels/channel-routing` — bindings, session keys, reply context
- `docs.openclaw.ai/concepts/architecture` — gateway daemon, typed WebSocket API
- `docs.openclaw.ai/concepts/agent-loop` — async RPC, streaming, compaction
- `docs.openclaw.ai/concepts/session` — session keys, pruning, memory flush
- `docs.openclaw.ai/concepts/queue` — per-session FIFO, collect mode, debounce

---

## Session 2 — 2026-02-12 (Phase 1: Telegram Long Polling)

### Goal
Replace webhook-based Telegram with long-polling worker.

### Files Created/Modified

#### [NEW] `backend/app/services/channels/telegram_poller.py`
- `getUpdates` long-polling loop with 30s timeout
- Offset tracking (never reprocess same message)
- Typing indicators (`sendChatAction`) while LLM processes
- Chat commands: `/status`, `/help`, `/reset`
- Error recovery with exponential backoff (1s → 2s → 4s → ... → 30s)
- Auto-deletes any existing webhook on start

#### [MODIFIED] `backend/app/main.py`
- Added `telegram_poller.start()` in lifespan startup
- Added `telegram_poller.stop()` in lifespan shutdown

### Verification
```
✅ Docker rebuilt — no import errors
✅ Logs: "telegram_webhook_deleted" — old webhook cleared
✅ Logs: "telegram_poller_started" — polling loop active
```

---

## Session 3 — 2026-02-12 (Phase 2: Channel Orchestration)

### Goal
Build session management, message queuing, and routing bindings — inspired by OpenClaw.

### Files Created/Modified

#### [NEW] `backend/app/services/channels/session_manager.py`
- Session key format: `agent:<name>:<channel>:dm:<peerId>` / `agent:<name>:<channel>:group:<groupId>`
- Sliding-window conversation history (max 20 messages)
- Daily reset at 4:00 AM UTC
- Idle timeout reset after 2 hours
- Manual `/reset` command support
- Cross-channel identity linking (e.g., same user on Telegram + WhatsApp shares context)

#### [NEW] `backend/app/services/channels/message_queue.py`
- Per-session FIFO queue with **collect mode** (coalesces rapid messages into single LLM turn)
- 1 second debounce timer
- 20 message cap with oldest-drop overflow
- Global concurrency limit of 4 concurrent LLM calls

#### [MODIFIED] `backend/app/services/orchestration/task_orchestrator.py`
- Added `ROUTING_BINDINGS` list — explicit channel/peer → agent mappings checked before IntentRouter
- Added `_resolve_binding()` method — priority: exact peer match > channel match
- `submit()` now creates/retrieves session via `SessionManager`
- `submit()` adds user message to session history
- `_execute()` now sends conversation history to LLM (both Gemini and OpenAI)
- After LLM response, saves assistant message to session for multi-turn continuity

### Verification
```
✅ Docker rebuilt — all modules imported cleanly
✅ Session manager loaded (in-memory store)
✅ Routing bindings active (empty by default, ready for config)
```

---

## Session 4 — 2026-02-12 (Phase 3-4: WhatsApp/Telegram Chunking + Email IMAP)

### Goal
Add text chunking for WhatsApp/Telegram and IMAP email polling.

### Files Created/Modified

#### [MODIFIED] `backend/app/services/orchestration/notification_dispatcher.py`
- Added `_chunk_text()` static method — splits long text at paragraph → newline → space boundaries
- **WhatsApp** (`_send_whatsapp`): chunks at 4000 chars, sends sequentially via Twilio
- **Telegram** (`_send_telegram`): chunks at 4000 chars, tries HTML parse mode first, falls back to plain text on error

#### [NEW] `backend/app/services/channels/email_poller.py`
- IMAP polling loop (every 60 seconds)
- Searches for `UNSEEN` emails only
- Parses headers (From, Subject, Message-ID) with encoded-word decoding
- Extracts plain text body from multipart messages
- Routes through `MessageGateway.from_email()` → `TaskOrchestrator.submit()`
- Configurable via CredentialVault: `imap_host`, `imap_port`, `imap_user`, `imap_password`
- Auto-skips when IMAP not configured

#### [MODIFIED] `backend/app/main.py`
- Added `email_poller.start()` in lifespan startup
- Added `email_poller.stop()` in lifespan shutdown

### Verification
```
✅ Docker rebuilt — no import errors
✅ Telegram poller: running (long-polling mode)
✅ Email poller: correctly skipped (IMAP not configured)
✅ Text chunking: integrated into WA + TG dispatchers
```

---

## Architecture Overview

```
┌─────────────────────────────────────────────────┐
│                    Channels                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │ Telegram │  │ WhatsApp │  │  Email   │      │
│  │ (Poller) │  │ (Twilio) │  │ (IMAP)  │      │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘      │
│       │              │              │            │
│       ▼              ▼              ▼            │
│  ┌──────────────────────────────────────┐       │
│  │         MessageGateway               │       │
│  │   from_telegram / from_whatsapp /    │       │
│  │   from_email / from_dashboard        │       │
│  └──────────────┬───────────────────────┘       │
│                 │ UnifiedMessage                 │
│                 ▼                                │
│  ┌──────────────────────────────────────┐       │
│  │        TaskOrchestrator              │       │
│  │  1. Check routing bindings           │       │
│  │  2. IntentRouter (keyword → LLM)     │       │
│  │  3. SessionManager (get/create)      │       │
│  │  4. Call LLM (with history)          │       │
│  │  5. Save response to session         │       │
│  └──────────────┬───────────────────────┘       │
│                 │                                │
│                 ▼                                │
│  ┌──────────────────────────────────────┐       │
│  │      NotificationDispatcher          │       │
│  │  _chunk_text → _send_telegram /      │       │
│  │  _send_whatsapp / _send_email        │       │
│  └──────────────────────────────────────┘       │
└─────────────────────────────────────────────────┘
```

## Remaining Phases
- **Phase 5**: Access control (`channel_access.py` — open/allowlist/disabled per channel)
- **Phase 6**: Message formatting + reply shaping (NO_REPLY suppression)
