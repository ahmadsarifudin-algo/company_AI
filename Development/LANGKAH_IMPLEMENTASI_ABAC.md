# Langkah-Langkah Implementasi ABAC Policy Enforcement

**Tanggal:** 12 Februari 2026  
**Urutan:** Setiap langkah harus dikerjakan secara berurutan — output langkah sebelumnya menjadi input langkah berikutnya.

---

## Fase 1: Foundation (Data Model)

> Tujuan: Memperkaya data model agar PolicyEngine punya informasi lengkap untuk evaluasi.

### Langkah 1 — Enrich `AgentContext` (`llm_client.py`)

**Apa:** Tambah 4 field baru ke dataclass `AgentContext`.  
**Kenapa:** Tanpa field ini, PolicyEngine tidak bisa evaluasi ticket, approval chain, sensitivity, dan risk level.

| Field | Type | Default |
|-------|------|---------|
| `ticket_id` | str | `""` |
| `approval_chain` | list[str] | `[]` |
| `data_sensitivity` | str | `"internal"` |
| `risk_level` | str | `"low"` |

**Jangan lupa:** Update method `new_span()` agar propagate semua field baru.

**Cek selesai:** `AgentContext(agent_id="x", agent_name="y", department="z", ticket_id="TIX-001")` — instantiate tanpa error.

---

### Langkah 2 — Enrich `ToolMeta` (`tool_registry.py`)

**Apa:** Tambah 3 field baru ke dataclass `ToolMeta`.  
**Kenapa:** Setiap tool perlu metadata sensitivity dan side-effect agar PolicyEngine bisa evaluasi lebih presisi.

| Field | Type | Default |
|-------|------|---------|
| `data_sensitivity_default` | str | `"internal"` |
| `side_effect_level` | str | `"none"` |
| `arg_sensitivity_hints` | list[str] | `[]` |

**Jangan lupa:** Update `register_shared_tool()` agar menerima field baru ini.

**Cek selesai:** existing `ToolRegistry.register()` dan `register_shared_tool()` tetap berfungsi (backward compatible karena ada default value).

---

## Fase 2: Builder & Classifier (Logic Layer)

> Tujuan: Buat satu builder tunggal yang konsisten membangun PolicyContext untuk semua chokepoint.

### Langkah 3 — Buat `PolicyContextBuilder` (`policy_context.py`) — FILE BARU

**Apa:** Buat file baru `app/core/policy_context.py` dengan class `PolicyContextBuilder`.  
**Kenapa:** Supaya ToolBroker, LLMClient, dan (future) DAL pakai builder yang sama — tidak copy-paste.

**Isi file:**

**A. Risk level ordering**  
Definisikan urutan: `low < medium < high < critical`  
Buat fungsi `_max_risk(a, b)` yang return risk tertinggi.

**B. Arg classifier**  
Fungsi `classify_args(args, hints)` → return sensitivity level:
- Cek apakah key di `args` match dengan `arg_sensitivity_hints` dari ToolMeta
- Jika ada match → return `"pii"`
- Jika tidak → return `"internal"`

**C. Terminal command classifier**  
Fungsi `classify_terminal_command(cmd)` → return kategori:

| Kategori | Pattern |
|----------|---------|
| `read_only` | `git status`, `git diff`, `cat`, `ls`, `echo`, `pwd` |
| `write_repo` | `git add`, `git commit`, `git push`, `git apply` |
| `install` | `pip install`, `npm install`, `yarn add`, `apt install` |
| `network` | `curl`, `wget`, `ssh`, `scp` |
| `destructive` | `rm`, `chmod`, `sudo`, `kill`, `mkfs` |

Default: `"unknown"`

**D. Builder methods**

`for_tool_call(ctx, tool_meta, args)` → `PolicyContext`:
- `risk_level` = `_max_risk(ctx.risk_level, tool_meta.risk_level.value)`
- `data_sensitivity` = max(tool default, classify_args result)
- `has_ticket_id` = `bool(ctx.ticket_id)`
- `approval_chain` = `ctx.approval_chain`
- `metadata` = `{"task_id": ctx.task_id, "trace_id": ctx.trace_id, "side_effect_level": tool_meta.side_effect_level}`
- Jika tool_name mengandung "terminal": tambah `metadata["command_category"]` = classify result

`for_llm_call(ctx, model_name)` → `PolicyContext`:
- `action` = `"llm_call"`
- `resource` = `f"model:{model_name}"`
- `risk_level` = `ctx.risk_level`

**Cek selesai:** Unit test builder menghasilkan PolicyContext yang lengkap, composite risk benar, PII args terdeteksi.

---

## Fase 3: ToolBroker Integration (Enforcement Layer)

> Tujuan: Jadikan PolicyEngine non-bypassable di setiap tool call.

### Langkah 4 — Update `ToolResult` schema (`tool_broker.py`)

**Apa:** Tambah field baru ke dataclass `ToolResult`.

| Field | Type | Default |
|-------|------|---------|
| `status` | str | `"success"` |
| `approval_id` | str \| None | `None` |
| `policy_decision` | str | `""` |
| `obligations` | dict \| None | `None` |

**Cek selesai:** Existing code yang bikin `ToolResult` tetap berfungsi (backward compatible).

---

### Langkah 5 — Tambah Step 2.5: Policy Evaluation di `ToolBroker.execute()`

**Apa:** Sisipkan evaluasi PolicyEngine antara Step 2 (role check) dan Step 3 (egress check).

**Urutan eksekusi:**

```
1. Build PolicyContext via PolicyContextBuilder.for_tool_call(ctx, tool_meta, args)
2. Evaluate: decision = policy_engine.evaluate(policy_ctx)
3. Emit audit log: "policy_evaluated" (SELALU, apapun hasilnya)
4. Jika DENY:
   - Emit "policy_denied" + "tool_blocked"
   - Raise ToolCallDenied
5. Jika REQUIRE_APPROVAL:
   - Call ApprovalGate.check() → mendapat approval_id
   - Emit "approval_requested"
   - Return ToolResult(status="needs_approval", approval_id=..., policy_decision="require_approval")
   - JANGAN panggil handler
6. Jika ALLOW:
   - Set policy_decision di ToolResult → "allow"
   - Lanjut ke Step 2.6
```

**Audit event ordering (WAJIB dipatuhi):**
```
policy_evaluated → [allow]  → tool_call_attempted → tool_called → tool_result
policy_evaluated → [deny]   → policy_denied + tool_blocked
policy_evaluated → [approval] → approval_requested [STOP, jangan panggil handler]
```

**Cek selesai:** Tool call dengan deny rule → handler TIDAK terpanggil. Tool call dengan require_approval → handler TIDAK terpanggil, approval_id ada.

---

### Langkah 6 — Tambah Step 2.6: Obligations Enforcement di `ToolBroker.execute()`

**Apa:** Jika policy decision menyertakan obligations, enforce di 3 titik.

**Titik enforcement:**

| Obligation | Di mana enforce |
|-----------|----------------|
| `mask_fields` | 1) Sanitize args sebelum logging, 2) Sanitize audit event payload |
| `require_encryption` | 3) Pass flag ke artifact store metadata |
| `log_level` | 1) Set severity logging untuk call ini |
| `notify_roles` | 2) Include di audit + ToolResult metadata |

**Buat helper function** `_sanitize_args(args, mask_fields)`:
- Untuk setiap key di args yang match mask_fields → ganti value dengan `"***MASKED***"`
- Return sanitized copy (jangan mutasi original)

**Cek selesai:** Jika policy punya `mask_fields: ["email", "phone"]` dan args mengandung `{"email": "test@x.com"}` → log args menampilkan `{"email": "***MASKED***"}`.

---

## Fase 4: LLMClient Integration

> Tujuan: Perluas enforcement ke LLM call chokepoint.

### Langkah 7 — Tambah Policy Evaluation di `LLMClient.call()`

**Apa:** Sisipkan evaluasi PolicyEngine sebelum HTTP call ke LiteLLM.

**Tambahkan class exception baru:**
- `LLMCallDenied(Exception)` — raised jika policy deny

**Tambahkan field ke `LLMResponse`:**
- `status: str = "success"` — "success" / "needs_approval"
- `approval_id: str | None = None`

**Urutan di dalam `call()`:**

```
1. Resolve model name (sudah ada)
2. Compute prompt hash (sudah ada)
3. Build PolicyContext via PolicyContextBuilder.for_llm_call(ctx, model_name)
4. Evaluate: decision = policy_engine.evaluate(policy_ctx)
5. Emit "policy_evaluated"
6. Jika DENY: raise LLMCallDenied
7. Jika REQUIRE_APPROVAL: return LLMResponse(status="needs_approval")
8. Jika ALLOW: lanjut ke HTTP call (existing code)
```

**Cek selesai:** LLM call dengan deny policy → raise exception. LLM call allow → berfungsi normal.

---

## Fase 5: Tests

> Tujuan: Pastikan semua enforcement berfungsi dan tidak ada bypass.

### Langkah 8 — Buat `test_policy_context_builder.py`

4 test cases:
1. `test_for_tool_call_builds_complete_context` — semua field populated
2. `test_composite_risk_uses_max` — `max("low", "high")` = `"high"`
3. `test_terminal_command_classification` — `"git status"` → `"read_only"`, `"rm -rf"` → `"destructive"`
4. `test_arg_sensitivity_detects_pii` — args `{"email_personal": "x"}` dengan hints `["email_personal"]` → sensitivity = `"pii"`

---

### Langkah 9 — Buat `test_toolbroker_policy.py`

5 test cases:
1. `test_tool_call_denied_by_policy` — mock PolicyEngine return DENY → handler tidak terpanggil, raise ToolCallDenied
2. `test_tool_call_requires_approval` — mock return REQUIRE_APPROVAL → handler tidak terpanggil, ToolResult.status = "needs_approval"
3. `test_tool_call_allowed_by_policy` — mock return ALLOW → handler terpanggil, result.success = True
4. `test_critical_tool_blocked_after_hours` — time=after_hours + risk=critical → DENY
5. `test_pii_tool_requires_ticket` — sensitivity=pii tanpa ticket → REQUIRE_APPROVAL

---

### Langkah 10 — Buat `test_obligations.py`

3 test cases:
1. `test_mask_fields_sanitizes_log_args` — args dengan PII field → log menampilkan "***MASKED***"
2. `test_mask_fields_sanitizes_audit_payload` — audit event tidak mengandung raw PII
3. `test_obligations_metadata_in_result` — ToolResult.obligations berisi obligations dict

---

### Langkah 11 — Buat `test_llmclient_policy.py`

3 test cases:
1. `test_denied_llm_call_blocked` — raises LLMCallDenied, HTTP call TIDAK terjadi
2. `test_require_approval_returns_pending` — LLMResponse.status = "needs_approval", HTTP call TIDAK terjadi
3. `test_allowed_llm_call_works` — normal call berfungsi

---

## Fase 6: Verification & Finalize

### Langkah 12 — Jalankan Full Test Suite

```bash
docker compose up -d --build app
docker exec company_ai_app python -m pytest tests/ --tb=short -q
```

**Target:** 237 existing + ~15 new = ~252 tests, **0 failed**.

---

### Langkah 13 — Update Dokumentasi

- Update `REKOMENDASI_ABAC_POLICY.md` → mark sebagai "Implemented"
- Update walkthrough

---

### Langkah 14 — Push ke GitHub

Ikuti workflow `/implementation-update`:
1. Checkout branch `feature/abac-enforcement`
2. Stage + commit
3. Push + merge ke master
