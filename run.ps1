# One-command launcher. Double-click-run (right-click > "Run with PowerShell")
# or from a terminal: .\run.ps1
#
# Brings up the whole stack (Postgres, Redis, backend API, frontend
# dashboard), runs pending DB migrations, waits for the backend to report
# healthy, then opens the dashboard in your default browser. This is the
# single entrypoint -- nothing else needs to be run by hand.

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if (-not (Test-Path ".env")) {
    Write-Host "No .env found -- copying .env.example to .env. Edit it (SECRET_KEY at minimum) before connecting real Instagram accounts." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
}

Write-Host "Starting Instagram Content Factory (docker compose up -d --build)..." -ForegroundColor Cyan
docker compose up -d --build
if (-not $?) {
    Write-Host "docker compose failed -- is Docker Desktop running?" -ForegroundColor Red
    exit 1
}

Write-Host "Waiting for the backend to become healthy..." -ForegroundColor Cyan
$maxAttempts = 60
for ($i = 0; $i -lt $maxAttempts; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 2
        if ($resp.StatusCode -eq 200) {
            Write-Host "Backend is up." -ForegroundColor Green
            break
        }
    } catch {
        Start-Sleep -Seconds 2
    }
    if ($i -eq $maxAttempts - 1) {
        Write-Host "Backend did not become healthy in time -- check logs with: docker compose logs backend" -ForegroundColor Red
        exit 1
    }
}

Write-Host "Opening dashboard at http://localhost:3000 ..." -ForegroundColor Cyan
Start-Process "http://localhost:3000"

Write-Host ""
Write-Host "Everything is running:" -ForegroundColor Green
Write-Host "  Dashboard : http://localhost:3000"
Write-Host "  API docs  : http://localhost:8000/docs"
Write-Host "  Stop with : docker compose down"
