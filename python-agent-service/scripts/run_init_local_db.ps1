# Run init_local_db.sql with configurable port and password
# Usage: .\run_init_local_db.ps1
# Or with custom password: $env:PGPASSWORD="yourpassword"; .\run_init_local_db.ps1

param(
    [int]$Port = 54320,
    [string]$User = "postgres",
    [string]$DbName = "secmanus"
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$initScript = Join-Path $scriptDir "db\init_local_db.sql"
$pgBin = "C:\Program Files\PostgreSQL\18\bin"

if (-not (Test-Path $pgBin)) {
    $pgBin = "C:\Program Files\PostgreSQL\16\bin"
}
if (-not (Test-Path $pgBin)) {
    Write-Host "PostgreSQL bin not found. Install PostgreSQL or set pgBin." -ForegroundColor Red
    exit 1
}

$createdb = Join-Path $pgBin "createdb.exe"
$psql = Join-Path $pgBin "psql.exe"

Write-Host "Creating database '$DbName' (if not exists)..." -ForegroundColor Yellow
try {
    & $createdb -h 127.0.0.1 -p $Port -U $User $DbName 2>&1 | Out-Null
} catch {}
if ($LASTEXITCODE -ne 0) {
    Write-Host "Database may already exist, continuing..." -ForegroundColor Gray
}

Write-Host "Running init_local_db.sql..." -ForegroundColor Yellow
& $psql -h 127.0.0.1 -p $Port -U $User -d $DbName -f $initScript
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed. Check PGPASSWORD if using password auth." -ForegroundColor Red
    exit 1
}
Write-Host "Done." -ForegroundColor Green
