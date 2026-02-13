# 🚀 Local Deployment Guide — Company AI

Panduan lengkap untuk menjalankan **Multi-Agentic AI Enterprise OS** di lingkungan lokal (Windows + WSL2).

---

## Arsitektur Lokal

```mermaid
graph LR
    subgraph Windows
        FE["🖥️ Frontend<br>Next.js :3000"]
        BE["⚡ Backend<br>FastAPI :8000"]
    end
    subgraph "Docker / WSL2"
        DB["🗄️ PostgreSQL<br>pgvector :5432"]
        RD["🔴 Redis<br>:6379"]
    end
    FE -->|API calls| BE
    BE --> DB
    BE --> RD
```

> [!IMPORTANT]
> **Kenapa hybrid?** Docker di WSL2 tidak selalu mem-forward port 8000 ke Windows.
> PostgreSQL (5432) dan Redis (6379) bisa diakses, tetapi port aplikasi sering bermasalah.
> Solusi: jalankan **backend + frontend langsung di Windows**, DB + Redis tetap di Docker.

---

## Prerequisites

| Tool | Versi Minimum | Cek |
|------|---------------|-----|
| **Python** | 3.11+ | `python --version` |
| **Node.js** | 18+ | `node --version` |
| **WSL2** | Ubuntu 22.04+ | `wsl --list --verbose` |
| **Docker** (di WSL) | 24+ | `wsl -e docker --version` |
| **Docker Compose** (di WSL) | v2+ | `wsl -e docker compose version` |
| **Git** | 2.x | `git --version` |

---

## Step 1 — Clone Repository

```powershell
git clone https://github.com/ahmadsarifudin-algo/company_AI.git
cd company_AI
```

---

## Step 2 — Jalankan Database & Redis (Docker)

Buka **PowerShell** dan jalankan:

```powershell
wsl bash -c "cd /mnt/c/Users/$env:USERNAME/Documents/project_antigravity/company_AI && docker compose up -d db redis"
```

> [!NOTE]
> Kita hanya menjalankan service `db` dan `redis`, **bukan** `app` dan `worker`.
> Backend akan dijalankan langsung di Windows untuk menghindari masalah port forwarding WSL2.

### Verifikasi container berjalan:

```powershell
# Cek port PostgreSQL
Test-NetConnection -ComputerName localhost -Port 5432 | Select-Object TcpTestSucceeded

# Cek port Redis
Test-NetConnection -ComputerName localhost -Port 6379 | Select-Object TcpTestSucceeded
```

Kedua output harus menunjukkan `TcpTestSucceeded: True`.

---

## Step 3 — Setup Backend (Python)

### 3.1 Buat Virtual Environment

```powershell
cd backend
python -m venv .venv
```

### 3.2 Aktifkan Virtual Environment

```powershell
.venv\Scripts\activate
```

### 3.3 Install Dependencies

```powershell
pip install -e ".[dev]"
```

Atau install manual jika editable install bermasalah:

```powershell
pip install fastapi "uvicorn[standard]" python-multipart ^
    "python-jose[cryptography]" "passlib[bcrypt]" ^
    "sqlalchemy[asyncio]" asyncpg alembic pgvector ^
    redis "celery[redis]" ^
    langchain langgraph litellm langchain-openai langchain-anthropic ^
    langchain-google-genai google-generativeai ^
    pydantic-settings python-dotenv slowapi structlog httpx ^
    email-validator psycopg2-binary pytest-asyncio pyyaml
```

### 3.4 Konfigurasi Environment

```powershell
copy .env.example .env
```

Edit `backend/.env` — pastikan **hostname mengarah ke `localhost`**, bukan nama Docker service:

```env
# ── Database ─────────────────────────────────
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/company_ai

# ── Redis ────────────────────────────────────
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
```

> [!CAUTION]
> Jangan gunakan `db` atau `redis` sebagai hostname — itu hanya berlaku jika backend jalan di dalam Docker network yang sama.

Isi juga API key yang diperlukan:

```env
# ── LLM API Keys ────────────────────────────
GOOGLE_API_KEY=your-google-api-key
OPENAI_API_KEY=your-openai-api-key

# ── Telegram (opsional) ─────────────────────
TELEGRAM_BOT_TOKEN=your-bot-token
```

---

## Step 4 — Inisialisasi Database

Database akan otomatis diinisialisasi oleh `infrastructure/init.sql` saat container PostgreSQL pertama kali start. Untuk membuat user admin:

```powershell
# Pastikan venv aktif
.venv\Scripts\activate

# Buat admin user
python create_admin.py
```

Output yang diharapkan:
```
Admin created: admin@company.ai / admin123
```

---

## Step 5 — Jalankan Backend

```powershell
cd backend
.venv\Scripts\activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Output yang diharapkan:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
📡 Telegram poller started (long-polling mode)
```

### Verifikasi:

- Buka browser: [http://localhost:8000/docs](http://localhost:8000/docs) → Swagger UI
- Atau cek port: `Test-NetConnection localhost -Port 8000 | Select-Object TcpTestSucceeded`

---

## Step 6 — Setup Frontend (Next.js)

Buka terminal **baru** (biarkan backend tetap berjalan):

### 6.1 Install Dependencies

```powershell
cd frontend
npm install
```

### 6.2 Konfigurasi API URL (Opsional)

Buat file `frontend/.env.local` jika API URL perlu dikustomisasi:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

> [!NOTE]
> Default sudah mengarah ke `http://localhost:8000/api/v1`, jadi file ini opsional.

### 6.3 Jalankan Frontend

```powershell
npm run dev
```

Output:
```
▲ Next.js 14.2.35
- Local: http://localhost:3000
✓ Starting...
```

---

## Step 7 — Login ke Dashboard

1. Buka [http://localhost:3000](http://localhost:3000)
2. Login dengan credential admin:
   - **Email:** `admin@company.ai`
   - **Password:** `admin123`

---

## Celery Worker (Opsional)

Jika memerlukan background task processing, buka terminal ketiga:

```powershell
cd backend
.venv\Scripts\activate
celery -A app.worker worker --loglevel=info --concurrency=4
```

---

## Menjalankan Tests

```powershell
cd backend
.venv\Scripts\activate
pytest tests/ -v --tb=short
```

Atau jalankan di dalam Docker (jika full stack Docker berjalan):

```powershell
wsl bash -c "cd /mnt/c/Users/$env:USERNAME/Documents/project_antigravity/company_AI && docker compose exec app pytest tests/ -v --tb=short"
```

---

## Ringkasan Terminal yang Dibutuhkan

| Terminal | Perintah | Keterangan |
|----------|----------|------------|
| **T1** | `wsl ... docker compose up -d db redis` | Database & Redis |
| **T2** | `python -m uvicorn app.main:app ...` | FastAPI Backend |
| **T3** | `npm run dev` | Next.js Frontend |
| **T4** *(opsional)* | `celery -A app.worker worker ...` | Background Tasks |

---

## Troubleshooting

### ❌ Port 8000 tidak bisa diakses

**Gejala:** Dashboard menampilkan `NetworkError when attempting to fetch resource`

**Penyebab:** Backend jalan di Docker/WSL tapi port tidak ter-forward ke Windows.

**Solusi:** Jalankan backend **langsung di Windows** (Step 5 di atas), bukan di Docker.

---

### ❌ Port 5432/6379 tidak bisa diakses

**Gejala:** Backend error `connection refused` ke database/Redis.

**Solusi:**
```powershell
# Cek apakah Docker container berjalan
wsl -e docker ps

# Restart jika perlu
wsl bash -c "cd /mnt/c/... && docker compose restart db redis"

# Verifikasi koneksi
Test-NetConnection localhost -Port 5432 | Select-Object TcpTestSucceeded
Test-NetConnection localhost -Port 6379 | Select-Object TcpTestSucceeded
```

---

### ❌ `ModuleNotFoundError` saat menjalankan backend

**Penyebab:** Virtual environment belum aktif atau dependency belum terinstall.

**Solusi:**
```powershell
.venv\Scripts\activate
pip install -e ".[dev]"
```

---

### ❌ Database belum terinisialisasi

**Gejala:** Error table tidak ditemukan.

**Solusi:** Hapus volume dan buat ulang:
```powershell
wsl bash -c "cd /mnt/c/... && docker compose down -v && docker compose up -d db redis"
# Tunggu 10 detik hingga DB healthy, lalu buat admin:
cd backend && .venv\Scripts\activate && python create_admin.py
```

---

## Mode Deployment Alternatif: Full Docker

Jika port forwarding WSL2 berfungsi dengan baik, bisa jalankan seluruh stack di Docker:

```powershell
wsl bash -c "cd /mnt/c/Users/$env:USERNAME/Documents/project_antigravity/company_AI && docker compose up -d --build"
```

> [!WARNING]
> Pada beberapa konfigurasi Windows + WSL2, port 8000 mungkin tidak ter-forward.
> Gunakan `Test-NetConnection localhost -Port 8000` untuk memverifikasi sebelum menggunakan mode ini.

Jika full Docker berhasil, **ubah `backend/.env`** kembali ke hostname Docker:
```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/company_ai
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2
```
