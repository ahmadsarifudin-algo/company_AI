<#
.SYNOPSIS
    Start the Company AI development environment using Docker.

.DESCRIPTION
    Starts all services (DB, Redis, Backend, Frontend) via Docker Compose in WSL.
    Dependencies are bundled in Docker images — no local install needed.

.PARAMETER Build
    Force rebuild Docker images (use after dependency changes)

.PARAMETER Detach
    Run in detached mode (default). Use -Detach:$false for attached/log mode.
#>

param(
    [switch]$Build,
    [switch]$Logs,
    [switch]$DbOnly
)

$ErrorActionPreference = "Continue"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ComposeFile = "/mnt/c" + ($ProjectRoot -replace '\\', '/' -replace 'C:', '') + "/docker-compose.yml"

function Write-Step { param($msg) Write-Host "▶ $msg" -ForegroundColor Cyan }
function Write-Ok   { param($msg) Write-Host "✅ $msg" -ForegroundColor Green }
function Write-Err  { param($msg) Write-Host "❌ $msg" -ForegroundColor Red }

Write-Host ""
Write-Host "═══════════════════════════════════════════════" -ForegroundColor Magenta
Write-Host "  Company AI — Docker Dev Environment" -ForegroundColor Magenta
Write-Host "═══════════════════════════════════════════════" -ForegroundColor Magenta
Write-Host ""

# Determine services and flags
$services = if ($DbOnly) { "db redis" } else { "" }
$buildFlag = if ($Build) { "--build" } else { "" }

# Start containers
if ($DbOnly) {
    Write-Step "Starting database services only (Docker Compose via WSL)..."
} else {
    Write-Step "Starting all services (Docker Compose via WSL)..."
}

$cmd = "docker compose -f $ComposeFile up -d $buildFlag $services 2>&1"
Write-Step "Running: $cmd"
wsl -e bash -lc $cmd

if ($LASTEXITCODE -ne 0) {
    Write-Err "Docker Compose failed. Is Docker running in WSL?"
    Write-Host "  Try: wsl -e bash -lc 'sudo service docker start'" -ForegroundColor Gray
    exit 1
}

# Wait and check
Start-Sleep -Seconds 3
wsl -e bash -lc "docker compose -f $ComposeFile ps 2>&1"

Write-Host ""
Write-Host "═══════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  Services Started!" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════" -ForegroundColor Green
Write-Host ""

if (-not $DbOnly) {
    Write-Host "  🌐 Frontend:   http://localhost:3000" -ForegroundColor White
    Write-Host "  🔌 Backend:    http://localhost:8000" -ForegroundColor White
    Write-Host "  📚 API Docs:   http://localhost:8000/docs" -ForegroundColor White
}
Write-Host "  🐘 PostgreSQL: localhost:5432" -ForegroundColor Gray
Write-Host "  🔴 Redis:      localhost:6379" -ForegroundColor Gray
Write-Host ""
Write-Host "  View logs: .\scripts\dev-start.ps1 -Logs" -ForegroundColor Yellow
Write-Host "  Stop:      .\scripts\dev-stop.ps1" -ForegroundColor Yellow
Write-Host ""

if ($Logs) {
    Write-Step "Tailing logs (Ctrl+C to stop)..."
    wsl -e bash -lc "docker compose -f $ComposeFile logs -f 2>&1"
}
