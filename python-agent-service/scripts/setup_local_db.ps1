# Setup Local PostgreSQL for SecManus
# Prerequisites: PostgreSQL installed and in PATH
# Usage: .\scripts\setup_local_db.ps1

$ErrorActionPreference = "Stop"
$dbName = "secmanus"
$dbUser = "postgres"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$initScript = Join-Path $scriptDir "db\init_local_db.sql"

Write-Host "SecManus Local DB Setup" -ForegroundColor Cyan
Write-Host "=======================" -ForegroundColor Cyan

# Create database if not exists
Write-Host "`n1. Creating database '$dbName' (if not exists)..." -ForegroundColor Yellow
$exists = psql -U $dbUser -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$dbName'"
if ($exists -eq "1") {
    Write-Host "   Database already exists." -ForegroundColor Green
} else {
    createdb -U $dbUser $dbName 2>$null; if ($?) { Write-Host "   Created." -ForegroundColor Green } else { Write-Host "   Run: createdb -U postgres $dbName" -ForegroundColor Yellow }
}

# Run init script
Write-Host "`n2. Running init_local_db.sql..." -ForegroundColor Yellow
psql -U $dbUser -d $dbName -f $initScript
if ($LASTEXITCODE -ne 0) {
    Write-Host "   Failed. Run manually: psql -U postgres -d $dbName -f $initScript" -ForegroundColor Red
    exit 1
}
Write-Host "   Done." -ForegroundColor Green

Write-Host "`n3. Verify .env has:" -ForegroundColor Yellow
Write-Host "   DATABASE_MODE=local" -ForegroundColor White
Write-Host "   LOCAL_DB_HOST=localhost" -ForegroundColor White
Write-Host "   LOCAL_DB_PORT=5432" -ForegroundColor White
Write-Host "   LOCAL_DB_NAME=$dbName" -ForegroundColor White
Write-Host "   LOCAL_DB_USER=$dbUser" -ForegroundColor White
Write-Host "   LOCAL_DB_PASSWORD=postgres" -ForegroundColor White

Write-Host "`nSetup complete. Restart the backend and register a new user." -ForegroundColor Green
