# Rekomendasi Perbaikan: ABAC Policy Enforcement

**Tanggal:** 12 Februari 2026  
**Status:** ✅ Final — Siap Implementasi  
**Prioritas:** 🔴 Tinggi (Keamanan & Governance)  
**Dokumen pendukung:** [LANGKAH_IMPLEMENTASI_ABAC.md](file:///c:/Users/sarif/Documents/project_antigravity/company_AI/Development/LANGKAH_IMPLEMENTASI_ABAC.md)

---

## 1. Temuan (Gap Analysis)

### Kondisi Saat Ini

| Komponen | File | Status |
|----------|------|--------|
| PolicyEngine (ABAC) | `app/core/policy_engine.py` | ✅ Implemented |
| ToolBroker (Chokepoint) | `app/core/tool_broker.py` | ⚠️ Partial — tidak panggil PolicyEngine |
| ApprovalGate | `app/core/approval_gate.py` | ✅ Implemented |
| LLMClient (Chokepoint) | `app/core/llm_client.py` | ⚠️ Tidak ada policy check |

### Masalah Utama

**ToolBroker dan LLMClient tidak memanggil PolicyEngine.** Enforcement hanya manual di workflow.

```
Alur Aktual (Bermasalah):
  Agent → ToolBroker → [cek role statis saja] → Execute Tool
  Agent → LLMClient → [tidak ada policy check] → Call LLM
```

### Risiko

- ❌ Developer lupa memanggil PolicyEngine → tool/LLM call bypass kebijakan
- ❌ Job di queue dieksekusi tanpa re-check policy (queue-unsafe)
- ❌ ApprovalGate tidak otomatis terpicu
- ❌ Audit trail tidak mencatat keputusan policy
- ❌ Obligations (masking, encryption) tidak diterapkan

---

## 2. Prinsip Desain

### A. Control = Chokepoint Runtime (Bukan Workflow)

| Chokepoint | Fungsi | Status |
|------------|--------|--------|
| **ToolBroker** | Semua tool call (33 tools) | Perlu integrasi PolicyEngine |
| **LLMClient** | Semua LLM call | Perlu integrasi PolicyEngine |
| **DAL** (future) | Read/write DB | Opsional |

### B. Queue-Safe: Cek di Worker, Bukan Saat Enqueue

- ABAC dievaluasi **di sisi Worker/ToolBroker** saat eksekusi
- Bukan hanya di API layer saat job masuk queue
- Job bisa dieksekusi belakangan — context bisa berubah

### C. Orchestrator vs Pengaman

| Layer | Peran |
|-------|-------|
| Orchestrator/Supervisor | Menentukan langkah apa yang dikerjakan |
| Worker | Mengeksekusi langkah |
| **ToolBroker + PolicyEngine + ApprovalGate** | Pengaman yang **selalu aktif saat eksekusi** |

---

## 3. Alur Eksekusi Target

```
Agent → ToolBroker.execute()
           ├── Step 1:   Resolve tool dari registry
           ├── Step 2:   Cek role/department access (statis)
           ├── Step 2.5: PolicyEngine.evaluate() ← NON-BYPASSABLE
           │     ├── ALLOW → lanjut
           │     ├── DENY → emit policy_denied + tool_blocked → raise error
           │     └── REQUIRE_APPROVAL
           │           ├── ApprovalGate.check() → create record
           │           ├── emit approval_requested
           │           └── return ToolResult(status="needs_approval")
           │               ❌ handler TIDAK dipanggil
           ├── Step 2.6: Enforce Obligations (mask, encrypt, log level)
           ├── Step 3:   Cek network egress
           ├── Step 4:   Cek file sandbox
           ├── Step 5:   Emit policy_evaluated + tool_call_attempted
           ├── Step 6:   Execute handler
           └── Step 7:   Emit tool_result
```

### Audit Event Ordering (WAJIB)

```
policy_evaluated → [allow]    → tool_call_attempted → tool_called → tool_result
policy_evaluated → [deny]     → policy_denied + tool_blocked
policy_evaluated → [approval] → approval_requested [STOP]
```

---

## 4. Perubahan Konkret

### 4.1 AgentContext (Enrichment)

| Field Baru | Type | Default | Fungsi |
|------------|------|---------|--------|
| `ticket_id` | str | `""` | Referensi ticket untuk ABAC |
| `approval_chain` | list[str] | `[]` | Siapa yang sudah approve |
| `data_sensitivity` | str | `"internal"` | Klasifikasi resource |
| `risk_level` | str | `"low"` | Risk level task |

### 4.2 ToolMeta (Enrichment)

| Field Baru | Type | Default | Fungsi |
|------------|------|---------|--------|
| `data_sensitivity_default` | str | `"internal"` | Sensitivity baseline tool |
| `side_effect_level` | str | `"none"` | none / low / high |
| `arg_sensitivity_hints` | list[str] | `[]` | PII field names di args |

### 4.3 PolicyContextBuilder (FILE BARU)

- `for_tool_call(ctx, tool_meta, args)` → PolicyContext
  - Composite risk: `max(ctx.risk_level, tool_meta.risk_level)`
  - Composite sensitivity: `max(tool_meta.default, classify_args(args))`
  - Terminal tools: classify command → `read_only|write_repo|install|network|destructive`

- `for_llm_call(ctx, model_name)` → PolicyContext
  - `action="llm_call"`, `resource=f"model:{model_name}"`

### 4.4 Obligations Enforcement (3 Titik)

| Obligation | Log Args | Audit Payload | Artifact Store |
|------------|----------|---------------|----------------|
| `mask_fields` | ✅ Sanitize | ✅ Sanitize | — |
| `require_encryption` | — | — | ✅ Flag |
| `log_level` | ✅ Set severity | — | — |
| `notify_roles` | — | ✅ Include | — |

### 4.5 ApprovalGate (Non-Blocking Pattern)

Saat REQUIRE_APPROVAL:
1. Buat approval record (`approval_id`)
2. Emit `approval_requested`
3. Return `ToolResult(status="needs_approval", approval_id=...)`
4. **Jangan block thread** — workflow/orchestrator handle `needs_approval` state

### 4.6 LLMClient Policy Integration

- Build PolicyContext: `resource=f"model:{model_name}"`
- Evaluate sebelum HTTP call
- Emit `policy_evaluated`, `prompt_sent` (prompt_hash), `llm_call_completed`
- DENY → raise `LLMCallDenied`
- REQUIRE_APPROVAL → return `LLMResponse(status="needs_approval")`

---

## 5. Terminal Tools: Command Classification

Tools dengan side-effect tinggi yang perlu klasifikasi command:

| Kategori | Pattern | Risk |
|----------|---------|------|
| `read_only` | `git status`, `cat`, `ls` | low |
| `write_repo` | `git commit`, `git push` | high |
| `install` | `pip install`, `npm install` | high |
| `network` | `curl`, `wget` | medium |
| `destructive` | `rm`, `sudo`, `kill` | critical |

Wajib untuk tools terminal:
- Baseline risk lebih tinggi
- Require `ticket_id` untuk write/install/destructive
- Require approval untuk after-hours + prod
- Command allowlist

---

## 6. Acceptance Criteria

| # | Kriteria | Verifikasi |
|---|----------|------------|
| AC1 | **Non-bypassable** — setiap tool call punya event `policy_evaluated` sebelum `tool_called` | Audit log |
| AC2 | **Approval cannot be skipped** — handler tidak terpanggil sebelum `approval_granted` | Audit chain |
| AC3 | **Obligations enforced** — `mask_fields` berlaku di log + audit + artifact | Test masking |
| AC4 | **Queue-safe** — policy dicek di worker runtime, bukan saat enqueue | Integration test |
| AC5 | **Audit ordering** — urutan event konsisten sesuai spesifikasi | Test ordering |

---

## 7. Test Suite

| Test File | Jumlah | Skenario |
|-----------|--------|----------|
| `test_toolbroker_policy.py` | 5 | deny, approval, allow, after-hours, pii |
| `test_obligations.py` | 3 | log masking, audit masking, metadata |
| `test_policy_context_builder.py` | 4 | context, composite risk, terminal, pii args |
| `test_llmclient_policy.py` | 3 | deny, approval, prompt hash |
| **Total baru** | **15** | |
| **Existing** | **237** | Tidak boleh ada regresi |
| **Target** | **~252** | 0 failed |

---

## 8. Prioritas Implementasi

| Tahap | Item | Effort | Dampak |
|-------|------|--------|--------|
| **P0** | Enrich AgentContext + ToolMeta | Low | 🔴 Tinggi |
| **P0** | Buat PolicyContextBuilder + classifier | Medium | 🔴 Sangat Tinggi |
| **P0** | Integrasi PolicyEngine → ToolBroker | Medium | 🔴 Sangat Tinggi |
| **P1** | Obligations enforcement (3 titik) | Medium | 🟠 Tinggi |
| **P1** | ApprovalGate non-blocking di ToolBroker | Medium | 🟠 Tinggi |
| **P1** | Integrasi PolicyEngine → LLMClient | Medium | 🟠 Tinggi |
| **P1** | Audit event ordering | Low | 🟠 Tinggi |
| **P2** | DAL integration (future) | Medium | 🟡 Medium |
| **P2** | Queue-safe worker enforcement | Medium | 🟡 Medium |

---

## 9. Ringkasan Rekomendasi Final

1. **Pindahkan ABAC enforcement ke ToolBroker.execute() dan LLMClient.call()** — non-bypassable
2. **Approval async non-blocking** — return `needs_approval`, jangan block thread
3. **Obligations enforce di 3 titik** — log, audit, artifact (bukan hanya log)
4. **Audit event ordering eksplisit** — `policy_evaluated` selalu sebelum `tool_called`
5. **Queue-safe** — policy dicek di worker runtime
6. **Terminal command classification** — classify command untuk ABAC presisi
7. **PolicyContextBuilder tunggal** — konsisten di semua chokepoint
8. **Test suite 15 test baru** — 0 bypass, 0 regresi

---

*Dokumen ini sudah final setelah review 2 iterasi.*  
*Langkah implementasi detail: [LANGKAH_IMPLEMENTASI_ABAC.md](file:///c:/Users/sarif/Documents/project_antigravity/company_AI/Development/LANGKAH_IMPLEMENTASI_ABAC.md)*
