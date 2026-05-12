# PowerShell Virtual Environment Activation Script
# Usage: .\activate.ps1
# This script bypasses PowerShell execution policy restrictions

$venvPath = Join-Path $PSScriptRoot "venv"
$pythonPath = Join-Path $venvPath "Scripts\python.exe"

if (Test-Path $pythonPath) {
    # Set environment variables directly
    $env:VIRTUAL_ENV = $venvPath
    $env:PATH = "$venvPath\Scripts;$env:PATH"
    
    Write-Host "Virtual environment activated!" -ForegroundColor Green
    Write-Host "Python: $pythonPath" -ForegroundColor Cyan
    Write-Host "Note: (venv) prefix may not show, but environment is active" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "You can now use: python, pip, etc." -ForegroundColor Green
} else {
    Write-Host "Error: Virtual environment not found!" -ForegroundColor Red
    Write-Host "Please run: python -m venv venv" -ForegroundColor Yellow
    exit 1
}
