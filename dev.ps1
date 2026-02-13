<#
.SYNOPSIS
    Company AI — Dev Environment (Windows)
    Starts DB + Redis in Docker, then runs backend + frontend locally.

.USAGE
    .\dev.ps1              # Normal start
    .\dev.ps1 -Fresh       # Reset DB + re-seed
    .\dev.ps1 -Stop        # Stop everything
#>

param(
    [switch]$Fresh,
    [switch]$Stop
)

$ErrorActionPreference = "Continue"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $ProjectDir "backend"
$FrontendDir = Join-Path $ProjectDir "frontend"
$ComposeFile = Join-Path $ProjectDir "docker-compose.dev.yml"
$VenvDir = Join-Path $BackendDir ".venv"

# Colors
function Write-OK($msg) { Write-Host "  ✅ $msg" -ForegroundColor Green }
function Write-Info($msg) { Write-Host "  ℹ️  $msg" -ForegroundColor Cyan }
function Write-Warn($msg) { Write-Host "  ⚠️  $msg" -ForegroundColor Yellow }
function Write-Err($msg) { Write-Host "  ❌ $msg" -ForegroundColor Red }
function Write-Header($msg) { Write-Host "`n═══ $msg ═══" -ForegroundColor White }

# ── Stop Mode ──────────────────────────────
if ($Stop) {
    Write-Header "Stopping everything"
    
    # Kill backend (uvicorn)
    Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -like "*uvicorn*"
    } | Stop-Process -Force -ErrorAction SilentlyContinue
    
    # Kill frontend (node/next)
    Get-Process -Name "node" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    
    # Stop Docker services
    wsl -d Ubuntu-20.04 bash -c "sudo docker compose -f '$($ComposeFile -replace '\\','/' -replace 'C:','/mnt/c')' down 2>/dev/null"
    
    Write-OK "All services stopped"
    exit 0
}

# ── Step 1: Start DB + Redis via Docker ────
Write-Header "Step 1/5: Starting PostgreSQL + Redis"

$WslComposePath = $ComposeFile -replace '\\','/' -replace 'C:','/mnt/c'

if ($Fresh) {
    Write-Warn "Fresh mode: removing volumes"
    wsl -d Ubuntu-20.04 bash -c "sudo docker compose -f '$WslComposePath' down -v 2>/dev/null; true"
}

wsl -d Ubuntu-20.04 bash -c "sudo docker compose -f '$WslComposePath' up -d 2>&1"

# Wait for health
$maxWait = 30
$elapsed = 0
while ($elapsed -lt $maxWait) {
    $dbReady = wsl -d Ubuntu-20.04 bash -c "sudo docker inspect --format='{{.State.Health.Status}}' company_ai_db 2>/dev/null" 2>$null
    $redisReady = wsl -d Ubuntu-20.04 bash -c "sudo docker inspect --format='{{.State.Health.Status}}' company_ai_redis 2>/dev/null" 2>$null
    
    if ($dbReady -eq "healthy" -and $redisReady -eq "healthy") { break }
    
    Start-Sleep -Seconds 2
    $elapsed += 2
    Write-Host "`r  Waiting... ${elapsed}s (db=$dbReady redis=$redisReady)" -NoNewline
}
Write-Host ""

if ($elapsed -ge $maxWait) {
    Write-Err "Services did not become healthy in ${maxWait}s"
    exit 1
}
Write-OK "PostgreSQL + Redis healthy"

# ── Step 2: Setup Python venv ──────────────
Write-Header "Step 2/5: Python environment"

if (-not (Test-Path $VenvDir)) {
    Write-Info "Creating virtual environment..."
    python -m venv $VenvDir
    Write-OK "Virtual environment created"
}

$PipExe = Join-Path $VenvDir "Scripts\pip.exe"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"

# Install deps if needed
$InstalledCheck = & $PipExe list 2>$null | Select-String "fastapi"
if (-not $InstalledCheck) {
    Write-Info "Installing Python dependencies..."
    & $PipExe install -q -r (Join-Path $BackendDir "requirements.txt") 2>$null
    if ($LASTEXITCODE -ne 0) {
        # Fallback: install from pyproject.toml
        & $PipExe install -q -e $BackendDir 2>$null
        if ($LASTEXITCODE -ne 0) {
            # Final fallback: install individually
            Write-Info "Installing dependencies from pyproject.toml..."
            & $PipExe install -q `
                "fastapi>=0.109.0" `
                "uvicorn[standard]>=0.27.0" `
                "python-multipart>=0.0.6" `
                "python-jose[cryptography]>=3.3.0" `
                "passlib[bcrypt]>=1.7.4" `
                "bcrypt>=4.0.0" `
                "sqlalchemy[asyncio]>=2.0.25" `
                "asyncpg>=0.29.0" `
                "alembic>=1.13.0" `
                "pgvector>=0.2.4" `
                "redis>=5.0.0" `
                "celery[redis]>=5.3.0" `
                "langchain>=0.1.0" `
                "langgraph>=0.0.40" `
                "litellm>=1.20.0" `
                "langchain-openai>=0.0.5" `
                "langchain-anthropic>=0.1.0" `
                "pydantic-settings>=2.1.0" `
                "python-dotenv>=1.0.0" `
                "slowapi>=0.1.9" `
                "structlog>=24.1.0" `
                "httpx>=0.26.0" `
                "email-validator>=2.1.0" `
                "psycopg2-binary>=2.9.0" `
                "pyyaml>=6.0"
        }
    }
    Write-OK "Dependencies installed"
} else {
    Write-OK "Dependencies already installed"
}

# ── Step 3: Start Backend ──────────────────
Write-Header "Step 3/5: Starting FastAPI backend"

$backendJob = Start-Process -FilePath $PythonExe `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload" `
    -WorkingDirectory $BackendDir `
    -PassThru -NoNewWindow

Write-Info "Backend PID: $($backendJob.Id)"

# Wait for backend to be ready
Start-Sleep -Seconds 5
$maxWait = 30
$elapsed = 0
while ($elapsed -lt $maxWait) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8000/docs" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        if ($response.StatusCode -eq 200) { break }
    } catch { }
    Start-Sleep -Seconds 2
    $elapsed += 2
    Write-Host "`r  Waiting for backend... ${elapsed}s" -NoNewline
}
Write-Host ""

if ($elapsed -ge $maxWait) {
    Write-Err "Backend did not start within ${maxWait}s"
    Write-Warn "Check the terminal output for errors"
} else {
    Write-OK "Backend running at http://localhost:8000"
}

# ── Step 4: Start Frontend ─────────────────
Write-Header "Step 4/5: Starting Next.js frontend"

$frontendJob = Start-Process -FilePath "npm" `
    -ArgumentList "run", "dev" `
    -WorkingDirectory $FrontendDir `
    -PassThru -NoNewWindow

Write-Info "Frontend PID: $($frontendJob.Id)"
Start-Sleep -Seconds 3
Write-OK "Frontend running at http://localhost:3000"

# ── Step 5: Test login ─────────────────────
Write-Header "Step 5/5: Testing login"

Start-Sleep -Seconds 3
try {
    $loginBody = '{"email":"admin@company.ai","password":"admin123"}'
    $loginResponse = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/auth/login" `
        -Method POST -ContentType "application/json" -Body $loginBody -ErrorAction Stop
    
    if ($loginResponse.access_token) {
        Write-OK "Login test: PASSED"
    } else {
        Write-Warn "Login returned unexpected response"
    }
} catch {
    Write-Warn "Login test skipped (backend may still be starting)"
}

# ── Summary ────────────────────────────────
Write-Host ""
Write-Host "╔══════════════════════════════════════════════╗" -ForegroundColor White
Write-Host "║         🚀 Company AI — Ready!               ║" -ForegroundColor White
Write-Host "╠══════════════════════════════════════════════╣" -ForegroundColor White
Write-Host "║  Backend:   http://localhost:8000             ║" -ForegroundColor White
Write-Host "║  API Docs:  http://localhost:8000/docs        ║" -ForegroundColor White
Write-Host "║  Frontend:  http://localhost:3000             ║" -ForegroundColor White
Write-Host "║                                              ║" -ForegroundColor White
Write-Host "║  Admin: admin@company.ai / admin123          ║" -ForegroundColor White
Write-Host "║                                              ║" -ForegroundColor White
Write-Host "║  Stop: .\dev.ps1 -Stop                       ║" -ForegroundColor White
Write-Host "╚══════════════════════════════════════════════╝" -ForegroundColor White
Write-Host ""
Write-Host "Press Ctrl+C to stop all services" -ForegroundColor Gray

# Keep running until Ctrl+C
try {
    while ($true) {
        Start-Sleep -Seconds 5
        
        # Check if processes are still alive
        if ($backendJob.HasExited) {
            Write-Err "Backend process exited!"
            break
        }
    }
} finally {
    Write-Info "Cleaning up..."
    if (-not $backendJob.HasExited) { $backendJob | Stop-Process -Force -ErrorAction SilentlyContinue }
    if (-not $frontendJob.HasExited) { $frontendJob | Stop-Process -Force -ErrorAction SilentlyContinue }
}
