<#
.SYNOPSIS
    Stop the Company AI Docker development environment.

.PARAMETER Destroy
    Stop containers AND delete volumes (wipes database data)
#>

param(
    [switch]$Destroy
)

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ComposeFile = "/mnt/c" + ($ProjectRoot -replace '\\', '/' -replace 'C:', '') + "/docker-compose.yml"

Write-Host ""
Write-Host "═══════════════════════════════════════════════" -ForegroundColor Yellow
Write-Host "  Company AI — Stopping Dev Environment" -ForegroundColor Yellow
Write-Host "═══════════════════════════════════════════════" -ForegroundColor Yellow
Write-Host ""

if ($Destroy) {
    Write-Host "▶ Stopping containers and deleting volumes..." -ForegroundColor Cyan
    wsl -e bash -lc "docker compose -f $ComposeFile down -v 2>&1"
    Write-Host "✅ All containers stopped, volumes deleted." -ForegroundColor Green
} else {
    Write-Host "▶ Stopping containers (data preserved)..." -ForegroundColor Cyan
    wsl -e bash -lc "docker compose -f $ComposeFile down 2>&1"
    Write-Host "✅ All containers stopped." -ForegroundColor Green
}

Write-Host ""
