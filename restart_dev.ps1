# Restart frontend and backend dev servers
# Usage: Right-click -> Run with PowerShell, or: .\restart_dev.ps1

$ErrorActionPreference = "Continue"
$workspaceRoot = $PSScriptRoot

Write-Host "Stopping existing Python and Node processes..." -ForegroundColor Yellow
Get-Process -Name python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Get-Process -Name node -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

Write-Host "Starting backend (port 8000)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$workspaceRoot\python-agent-service'; python -m uvicorn app.main:app --reload --port 8000"

Start-Sleep -Seconds 2

Write-Host "Starting frontend (port 8080)..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$workspaceRoot'; `$env:VITE_API_MODE='local'; npm run dev"

Write-Host "Done. Backend: http://127.0.0.1:8000 | Frontend: http://localhost:8080" -ForegroundColor Cyan
