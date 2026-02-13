# Walkthrough: SOUL Profiling + Dual-Output + Department Guard

**Date:** 2026-02-12  
**Status:** Implemented, pending Docker rebuild & test

---

## Overview

Tiga sistem baru yang saling terintegrasi:

| Sistem | Fungsi |
|--------|--------|
| **DepartmentGuard** | Known user → hanya agent dept-nya. Unknown → Marketing Digital |
| **SoulResolver** | User → SOUL personality → system prompt |
| **ResponseShaper** | 1 LLM call → human_reply (chat) + agent_json (internal) |

## Architecture

```
Message → Identity Linker → DepartmentGuard → SoulResolver → LLM (dual-output)
                                                                    ↓
                                                          ResponseShaper
                                                         ↙            ↘
                                                human_reply      agent_json
                                              (→ Telegram)      (→ DB/logs)
```

## New Files

| File | Purpose |
|------|---------|
| `infrastructure/migrations/add_soul_tables.sql` | DB migration + 5 template seeds |
| `backend/app/models/soul.py` | `SoulTemplate` + `UserSoul` SQLAlchemy models |
| `backend/app/services/channels/department_guard.py` | Dept isolation enforcement |
| `backend/app/services/channels/soul_resolver.py` | User → SOUL prompt compilation |
| `backend/app/services/channels/response_shaper.py` | Dual-output parser (`---INTENT---` separator) |
| `backend/app/agents/departments/marketing/__init__.py` | Marketing package |
| `backend/app/agents/departments/marketing/digital.py` | `MarketingDigitalAgent` for unknown users |
| `backend/app/api/v1/souls.py` | CRUD API (6 endpoints) |

## Modified Files

| File | Change |
|------|--------|
| `backend/app/models/user.py` | Added `active_soul_id` FK column |
| `backend/app/models/__init__.py` | Registered `SoulTemplate`, `UserSoul` |
| `backend/app/services/orchestration/task_orchestrator.py` | Integrated DepartmentGuard + SoulResolver + ResponseShaper |
| `backend/app/api/v1/router.py` | Added souls router |

## Department Guard Policy

| User | Routing |
|------|---------|
| Known, dept=Finance | Finance agents only |
| Known, dept=Tech | Tech agents only |
| Known, tanya di luar dept | Redirect ke Supervisor dept user |
| Unknown | → MarketingDigitalAgent |
| Dashboard/API | Tidak terpengaruh |

## SOUL Templates (5 Default)

| Icon | Name | Tone |
|------|------|------|
| 😊 | Ramah & Informatif | friendly |
| 👔 | Formal Executive | formal |
| 🤙 | Casual Santai | casual |
| 🔧 | Teknikal | technical |
| 🌏 | Bilingual ID-EN | bilingual |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/souls/templates` | List templates |
| `GET` | `/api/v1/souls/my` | List user's souls |
| `POST` | `/api/v1/souls/my` | Create soul |
| `PUT` | `/api/v1/souls/my/{id}` | Update soul |
| `POST` | `/api/v1/souls/my/{id}/activate` | Activate soul |
| `DELETE` | `/api/v1/souls/my/{id}` | Delete soul |

## Dual-Output Example

```
User via Telegram: "berapa budget Q2?"

LLM Output:
  Budget Q2 masih dalam review Pak Ahmad. Mau saya cek detail breakdown-nya?
  ---INTENT---
  {"intent":"query","department":"finance","action":"check_budget",
   "needs_agent":true,"suggested_agent":"accounting","confidence":0.85}

→ human_reply dikirim ke Telegram
→ agent_json disimpan di log + bisa trigger background agent
```

## Deploy Steps

```bash
# 1. Rebuild Docker
docker-compose up --build -d

# 2. Apply migration
docker exec -i company_ai-db-1 psql -U postgres -d company_ai \
  < infrastructure/migrations/add_soul_tables.sql

# 3. Test via Telegram
```
